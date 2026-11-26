"""The app's tables, as edited in the browser, become valid review sheets."""

import math
from datetime import date

import pandas as pd

from unapply.app.forms import experience_rows, finding_rows, review_sheet, skill_rows
from unapply.review import apply_review_sheet
from unapply.schemas import (
    Evidence,
    Experience,
    Profile,
    Skill,
    SkillCategory,
    SkillLevel,
    Source,
    SourceKind,
)
from unapply.workspace import Workspace


def _profile():
    cv = Source(kind=SourceKind.CV)
    e = Evidence(source_id=cv.id, quote="Built Kafka\npipelines")
    return Profile(
        headline="Engineer",
        sources=[cv],
        evidence=[e],
        experiences=[
            Experience(
                title="Engineer",
                organisation="Acme",
                start=date(2021, 3, 1),
                evidence_ids=[e.id],
            )
        ],
        skills=[
            Skill(name="kafka", category=SkillCategory.TECHNOLOGY, evidence_ids=[e.id]),
            Skill(name="sql", category=SkillCategory.TECHNOLOGY, evidence_ids=[e.id]),
        ],
    )


def _through_pandas(rows):
    """Round-trip rows through a DataFrame, as st.data_editor does (NaN for blanks)."""
    return pd.DataFrame(rows).to_dict("records")


def test_rows_show_evidence_and_dates():
    p = _profile()
    assert skill_rows(p)[0]["evidence"] == "cv: Built Kafka pipelines"
    assert experience_rows(p)[0]["start"] == "2021-03"


def test_edited_tables_make_a_valid_sheet():
    p = _profile()
    skills = _through_pandas(skill_rows(p))
    skills[0]["level"] = "4 · advanced"  # As chosen in the level column.
    skills[1]["keep"] = False
    experiences = _through_pandas(experience_rows(p))
    experiences[0]["end"] = "2024-06"
    added = _through_pandas(
        [
            {
                "name": "looker",
                "category": "technology",
                "level": math.nan,
                "note": "Daily for two years.",
            },
            {
                "name": None,
                "category": None,
                "level": math.nan,
                "note": None,
            },  # empty row
        ]
    )
    sheet = review_sheet(
        p,
        headline="Data engineer",
        preferences={
            "locations": ["Copenhagen"],
            "work_modes": ["hybrid"],
            "work_permits": [],
            "salary_min": None,
            "salary_currency": None,
            "dealbreakers": [],
        },
        experiences=experiences,
        skills=skills,
        added=added,
        approve=True,
    )
    reviewed = apply_review_sheet(p, sheet)
    assert reviewed.headline == "Data engineer"
    assert [s.name for s in reviewed.skills] == ["kafka", "looker"]
    assert reviewed.skill("kafka").self_level == SkillLevel.ADVANCED
    assert reviewed.skill("looker").self_level is None
    assert reviewed.experiences[0].end == date(2024, 6, 1)
    assert reviewed.approved_by_candidate_at is not None


def test_finding_rows_before_estimation():
    rows = finding_rows(_profile())
    assert rows[0]["estimate"] is None and rows[0]["reason"] == "not estimated yet"


def test_workspace_keeps_a_numbered_history(tmp_path):
    ws = Workspace.create("jane", tmp_path, github="jane")
    assert Workspace.names(tmp_path) == ["jane"]
    assert ws.profile() is None and ws.settings() == {"github": "jane"}
    ws.save_profile(_profile(), "extracted")
    ws.save_profile(_profile(), "reviewed")
    assert ws.history() == ["extracted", "reviewed"]
    assert (ws.root / "history" / "002_reviewed.json").exists()
    ws.save_pending_questions([{"skill": "sql", "reason": "unverified", "text": "?"}])
    assert ws.pending_questions()[0]["skill"] == "sql"
    ws.save_pending_questions(None)
    assert ws.pending_questions() is None


def test_candidate_view_hides_the_assessment():
    from unapply.app.forms import candidate_view
    from unapply.schemas import ClaimSupport, SkillEstimate

    p = _profile()
    est = SkillEstimate(level=SkillLevel(2), confidence=0.8, rationale="r", model="m")
    p = p.model_copy(
        update={
            "skills": [s.model_copy(update={"estimate": est}) for s in p.skills],
            "claim_support": ClaimSupport(rated=1, overclaims=["kafka"]),
        }
    )
    shown = candidate_view(p).model_dump_json()
    assert "overclaims" not in shown and '"estimate":null' in shown.replace(" ", "")
    assert p.skill("kafka").estimate is not None  # The original is untouched.


def test_edited_rubric_table_makes_a_valid_sheet():
    from unapply.app.forms import criterion_rows, rubric_sheet
    from unapply.jobs.sheet import apply_rubric_sheet
    from unapply.schemas import Criterion, CriterionKind, Job, Rubric

    job = Job(
        company="Acme",
        title="Engineer",
        ad_text="Strong Python. Rust is a plus.",
        rubric=Rubric(
            criteria=[
                Criterion(
                    kind=CriterionKind.MUST_HAVE,
                    description="Strong Python",
                    skill="python",
                    weight=5,
                    source_quote="Strong Python.",
                ),
                Criterion(
                    kind=CriterionKind.NICE_TO_HAVE,
                    description="Rust",
                    skill="rust",
                    weight=1,
                    source_quote="Rust is a plus.",
                ),
            ]
        ),
    )
    rows = _through_pandas(criterion_rows(job))
    assert rows[0]["kind"] == "Must have" and rows[0]["level"] == "—"
    rows[0]["level"] = "4 · advanced"
    rows = rows[:1] + [  # Rust deleted, one criterion added, one empty row
        {
            "id": None,
            "kind": "Nice to have",
            "description": "Kubernetes",
            "skill": "Kubernetes",
            "level": "—",
            "weight": math.nan,
            "quote": None,
        },
        {
            "id": None,
            "kind": None,
            "description": None,
            "skill": None,
            "level": None,
            "weight": math.nan,
            "quote": None,
        },
    ]
    sheet = rubric_sheet(
        job,
        company="Acme",
        title="Engineer",
        filters={
            "locations": ["Aarhus"],
            "work_modes": ["onsite"],
            "required_work_permits": [],
            "min_years_experience": None,
        },
        rows=rows,
        approve=True,
    )
    updated = apply_rubric_sheet(job, sheet)
    r = updated.rubric
    assert [c.description for c in r.criteria] == ["Strong Python", "Kubernetes"]
    assert r.criteria[0].min_level == SkillLevel.ADVANCED
    assert r.criteria[0].source_quote == "Strong Python."
    assert (r.criteria[1].skill, r.criteria[1].weight) == ("kubernetes", 3.0)
    assert r.version == 2 and r.approved_at is not None
