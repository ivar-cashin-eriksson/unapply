"""Matching: hard filters, the baseline and LLM scorers, ranking and `unapply match`.

John Doe against Fjord Grocery is scored by both scorers: the baseline in plain code,
the LLM scorer by replaying a hand-written stand-in answer
(`tests/fixtures/jobs/fjord_grocery/match_john_doe.json`, listed in
`docs/to-record.md`). Everything runs offline.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from unapply.app import demo, forms
from unapply.cli import main
from unapply.db.engine import database_url, init_db
from unapply.db.models import AuditEntryRow
from unapply.db.repository import Repository, RubricLocked
from unapply.estimation.claims import claim_support
from unapply.estimation.skills import estimate_skills, skills_without_estimate
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.interview.questions import select_topics, write_questions
from unapply.interview.sheet import apply_interview_sheet
from unapply.jobs.extract import extract_job
from unapply.jobs.sheet import apply_rubric_sheet, export_rubric_sheet
from unapply.llm import ReplayLLM
from unapply.matching import (
    BASELINE_MODEL,
    BaselineScorer,
    LLMScorer,
    check_hard_filters,
    latest,
    match_candidate,
    rank,
)
from unapply.matching.anonymise import REDACTED, redact
from unapply.matching.audit import (
    AuditKind,
    check_ranking,
    content_hash,
    match_entry,
    reproduce_ranking,
)
from unapply.matching.baseline import RELATED_FACTOR, level
from unapply.matching.filters import (
    Outcome,
    counts_as_work,
    permit_covers,
    same_place,
    years_of_experience,
)
from unapply.matching.llm_scorer import (
    CriterionScores,
    ScoredCriterion,
    apply_scores,
    render_match_prompt,
)
from unapply.matching.run import match_job
from unapply.schemas import (
    Criterion,
    CriterionKind,
    CriterionScore,
    Evidence,
    Experience,
    HardFilters,
    Job,
    Match,
    Preferences,
    Profile,
    Rubric,
    Skill,
    SkillEstimate,
    SkillLevel,
    Source,
    SourceKind,
    WorkMode,
)

FIXTURES = Path(__file__).parent / "fixtures"
JOHN = FIXTURES / "john_doe"
FJORD = FIXTURES / "jobs" / "fjord_grocery"
STAND_IN = FJORD / "match_john_doe.json"
TODAY = date(2026, 11, 26)


def _estimated(profile: Profile, recording: str) -> Profile:
    names = skills_without_estimate(profile)
    result = estimate_skills(profile, ReplayLLM(JOHN / recording), names)
    return result.profile.model_copy(
        update={"claim_support": claim_support(result.profile)}
    )


@pytest.fixture(scope="module")
def john() -> Profile:
    """John's approved, interviewed and re-estimated profile, from his recordings."""
    draft = extract_profile(
        load_path(JOHN / "material"), ReplayLLM(JOHN / "extraction.json")
    ).profile
    from unapply.review import apply_review_sheet

    estimated = _estimated(
        apply_review_sheet(draft, demo.john_review_sheet(draft)), "estimation.json"
    )
    questions = write_questions(
        estimated, select_topics(estimated), ReplayLLM(JOHN / "questions.json")
    )
    asked = [
        {"skill": q.skill, "reason": q.reason.value, "text": q.text} for q in questions
    ]
    sheet = forms.interview_sheet(estimated, asked, demo.john_answers())
    interviewed, _ = apply_interview_sheet(estimated, sheet)
    return _estimated(interviewed, "estimation_after_interview.json")


@pytest.fixture
def fjord() -> Job:
    """Fjord Grocery with its extracted rubric, approved (version 1)."""
    ad = (FJORD / "ad.md").read_text(encoding="utf-8")
    job = extract_job(ad, ReplayLLM(FJORD / "extraction.json")).job
    sheet = export_rubric_sheet(job).replace("approve: false", "approve: true")
    return apply_rubric_sheet(job, sheet)


def _scores(result, job: Job) -> dict[str, float]:
    by_id = {c.id: c.description for c in job.rubric.criteria}
    return {by_id[s.criterion_id]: s.score for s in result.match.criterion_scores}


def _profile(
    experiences=(), skills=(), preferences=None, quotes=("Used it at work.",)
) -> Profile:
    """A small synthetic profile: one CV source, its quotes and the given parts."""
    cv = Source(kind=SourceKind.CV, uri="uploads/jane-roe-cv.pdf")
    evidence = [Evidence(source_id=cv.id, quote=q) for q in quotes]
    return Profile(
        sources=[cv],
        evidence=evidence,
        experiences=list(experiences),
        skills=list(skills),
        preferences=preferences or Preferences(),
    )


def _role(start, end, title="Data Scientist", organisation="Acme"):
    return Experience(title=title, organisation=organisation, start=start, end=end)


# Hard filters


def test_john_passes_fjord_groceries_hard_filters(john, fjord):
    report = check_hard_filters(john, fjord.rubric.hard_filters, TODAY)
    assert [(c.name, c.outcome) for c in report.checks] == [
        ("work_mode", Outcome.PASS),
        ("location", Outcome.PASS),
        ("work_permit", Outcome.PASS),
        ("min_years_experience", Outcome.PASS),
    ]
    assert report.passed
    # Student job 2018-01 to now, without the MSc and BSc: 107 months.
    assert years_of_experience(john, TODAY) == pytest.approx(107 / 12)


def test_a_rubric_without_filters_passes_everyone():
    report = check_hard_filters(_profile(), HardFilters(), TODAY)
    assert report.checks == [] and report.passed


@pytest.mark.parametrize(
    ("wanted", "offered", "outcome"),
    [
        ([], [WorkMode.ONSITE], Outcome.PASS),  # No preference means any.
        ([WorkMode.HYBRID, WorkMode.REMOTE], [WorkMode.HYBRID], Outcome.PASS),
        ([WorkMode.REMOTE], [WorkMode.HYBRID, WorkMode.ONSITE], Outcome.FAIL),
    ],
)
def test_work_mode(wanted, offered, outcome):
    profile = _profile(preferences=Preferences(work_modes=wanted))
    report = check_hard_filters(profile, HardFilters(work_modes=offered))
    assert report.checks[0].outcome == outcome


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Copenhagen", "copenhagen", True),
        ("Copenhagen, Denmark", "Copenhagen", True),
        ("Greater Copenhagen", "Copenhagen", True),
        ("Aarhus", "Copenhagen", False),
        ("Denmark", "Copenhagen", False),  # No geography: a known limit.
        ("", "Copenhagen", False),
    ],
)
def test_same_place(a, b, same):
    assert same_place(a, b) is same


def test_location():
    copenhagen = HardFilters(locations=["Copenhagen"], work_modes=[WorkMode.HYBRID])

    def outcome(preferences, filters=copenhagen):
        report = check_hard_filters(_profile(preferences=preferences), filters)
        return next(c.outcome for c in report.checks if c.name == "location")

    assert outcome(Preferences(locations=["Copenhagen, Denmark"])) == Outcome.PASS
    assert outcome(Preferences(locations=["Aarhus", "Odense"])) == Outcome.FAIL
    # No locations given: not excluded, but reported.
    assert outcome(Preferences()) == Outcome.UNKNOWN
    # Remote work, if both accept it, makes the location irrelevant.
    remote = HardFilters(locations=["Copenhagen"], work_modes=[WorkMode.REMOTE])
    assert outcome(Preferences(locations=["Lisbon"]), remote) == Outcome.PASS
    only_onsite = Preferences(locations=["Lisbon"], work_modes=[WorkMode.ONSITE])
    assert outcome(only_onsite, remote) == Outcome.FAIL


@pytest.mark.parametrize(
    ("held", "required", "covers"),
    [
        ("EU", "EU", True),
        ("EU", "DK", True),
        ("DK", "EU", True),
        ("DK", "DK", True),
        ("SE", "DK", False),
        ("US", "EU", False),
        ("NO", "EU", False),  # EEA, not EU.
        ("EU", "US", False),
        ("GR", "EU", True),
    ],
)
def test_permit_covers(held, required, covers):
    assert permit_covers(held, required) is covers


def test_work_permit():
    eu = HardFilters(required_work_permits=["EU"])

    def check(permits, filters=eu):
        profile = _profile(preferences=Preferences(work_permits=permits))
        return check_hard_filters(profile, filters).checks[0]

    assert check(["eu"]).outcome == Outcome.PASS
    assert check(["US", "CA"]).outcome == Outcome.FAIL
    assert "job requires EU" in check(["US"]).reason
    assert check([]).outcome == Outcome.UNKNOWN
    both = HardFilters(required_work_permits=["DK", "US"])
    assert check(["EU"], both).outcome == Outcome.FAIL
    assert check(["EU", "US"], both).outcome == Outcome.PASS


def test_years_count_overlapping_roles_once():
    profile = _profile(
        experiences=[
            _role(date(2018, 1, 1), date(2020, 12, 1)),  # 36 months
            _role(date(2020, 1, 1), date(2021, 12, 1)),  # 12 more after the overlap
            _role(date(2023, 1, 1), date(2023, 12, 1)),  # a gap, then 12
            _role(date(2019, 3, 1), date(2019, 4, 1)),  # inside the first
        ]
    )
    assert years_of_experience(profile, TODAY) == 5.0


def test_years_skip_education_projects_and_undated_roles():
    profile = _profile(
        experiences=[
            _role(date(2015, 1, 1), date(2018, 1, 1), "MSc in Statistics", "DTU"),
            _role(date(2016, 1, 1), date(2017, 1, 1), "Bachelor's degree", "KU"),
            _role(date(2017, 1, 1), date(2019, 1, 1), "App", "Personal project"),
            _role(None, date(2020, 1, 1)),
            _role(date(2020, 1, 1), date(2020, 12, 1), "Data Analyst (student job)"),
        ]
    )
    assert years_of_experience(profile, TODAY) == 1.0
    assert counts_as_work(_role(None, None, "Data Analyst (student job)"))
    assert not counts_as_work(_role(None, None, "PhD in Physics"))
    assert years_of_experience(_profile(), TODAY) is None


def test_a_current_role_runs_to_today():
    profile = _profile(experiences=[_role(date(2025, 12, 1), None)])
    assert years_of_experience(profile, TODAY) == 1.0  # December 2025 to November 2026


@pytest.mark.parametrize(
    ("months", "outcome"), [(47, Outcome.FAIL), (48, Outcome.PASS)]
)
def test_min_years_at_the_edge(months, outcome):
    start = date(2020, 1, 1)
    end_month = start.month - 1 + months - 1
    end = date(start.year + end_month // 12, end_month % 12 + 1, 1)
    profile = _profile(experiences=[_role(start, end)])
    report = check_hard_filters(profile, HardFilters(min_years_experience=4), TODAY)
    assert report.checks[0].outcome == outcome
    assert report.passed is (outcome == Outcome.PASS)


def test_no_dated_work_is_unknown_not_a_failure():
    report = check_hard_filters(_profile(), HardFilters(min_years_experience=3), TODAY)
    assert report.checks[0].outcome == Outcome.UNKNOWN
    assert report.passed


# The baseline scorer


def test_baseline_scores_john_against_fjord_grocery(john, fjord):
    result = match_candidate(john, fjord, BaselineScorer(), TODAY)
    assert result.match.model == BASELINE_MODEL
    assert result.match.passed_hard_filters
    assert _scores(result, fjord) == {
        "Strong Python skills": 1.0,
        # He rates SQL 2, the estimate is 3: below the 4 asked for.
        "Strong SQL skills": 0.46,
        "Hands-on experience with time series forecasting in production": 1.0,
        # Only in his skills list: his own 4 counts, as the estimate is unsure.
        "Solid understanding of statistics": 0.9,
        "Solid understanding of A/B testing": 1.0,
        "Communicates clearly with non-technical stakeholders": 1.0,
        # Overclaims: "familiar with" and a course, estimated 1 with confidence.
        "Experience with Spark or other tools for large datasets": 0.31,
        "Experience with deep learning for forecasting": 0.31,
        "Speaks Danish": 0.9,
    }
    assert result.problems == [
        "Experience in retail or e-commerce: names no skill, so the baseline "
        "doesn't score it"
    ]
    assert result.match.total(fjord.rubric) == pytest.approx(0.81, abs=0.005)
    evidence = {e.id for e in john.evidence}
    for s in result.match.criterion_scores:
        assert s.evidence_ids and set(s.evidence_ids) <= evidence
        assert s.rationale


def test_baseline_is_deterministic(john, fjord):
    first = match_candidate(john, fjord, BaselineScorer(), TODAY).match
    second = match_candidate(john, fjord, BaselineScorer(), TODAY).match
    assert first.criterion_scores == second.criterion_scores


def _criterion(skill, min_level=None):
    return Criterion(
        kind=CriterionKind.MUST_HAVE,
        description=f"{skill} wanted",
        skill=skill,
        min_level=min_level,
    )


def _with_skills(*skills, quotes=("Used it at work.", "Used it again.")):
    profile = _profile(quotes=quotes)
    ids = [e.id for e in profile.evidence]
    built = []
    for name, own, estimated, confidence in skills:
        estimate = (
            SkillEstimate(
                level=SkillLevel(estimated),
                confidence=confidence,
                rationale="From the quotes.",
                evidence_ids=ids,
                model="test",
            )
            if estimated
            else None
        )
        built.append(
            Skill(
                name=name,
                self_level=SkillLevel(own) if own else None,
                estimate=estimate,
                evidence_ids=ids,
            )
        )
    return profile.model_copy(update={"skills": built})


def test_level_blends_own_and_estimated_by_confidence():
    profile = _with_skills(
        ("a", 5, 3, 0.5), ("b", None, 3, 0.5), ("c", 4, None, 0.0), ("d", None, None, 0)
    )
    assert [level(s) for s in profile.skills] == [4.0, 3.0, 4.0, 1.0]


def test_baseline_level_fit_and_evidence():
    scorer = BaselineScorer()
    profile = _with_skills(("python", 3, 3, 1.0))
    assert scorer.score_criterion(profile, _criterion("python", 3)).score == 1.0
    # One level short of 4: (3/4) ** 2.
    assert scorer.score_criterion(profile, _criterion("python", 4)).score == 0.56
    # No min_level means working (3).
    assert scorer.score_criterion(profile, _criterion("python")).score == 1.0
    one_quote = _with_skills(("python", 3, 3, 1.0), quotes=("Used it.",))
    assert scorer.score_criterion(one_quote, _criterion("python", 3)).score == 0.9
    missing = scorer.score_criterion(profile, _criterion("kafka", 3))
    assert (missing.score, missing.evidence_ids) == (0.0, [])
    assert "No kafka" in missing.rationale


def test_baseline_discounts_own_statements():
    profile = _with_skills(("kubernetes", 3, None, 0))
    statement = Source(kind=SourceKind.INTERVIEW, uri="interview")
    profile = Profile.model_validate(
        {
            **profile.model_dump(),
            "sources": [statement.model_dump()],
            "evidence": [
                {**e.model_dump(), "source_id": statement.id} for e in profile.evidence
            ],
        }
    )
    score = BaselineScorer().score_criterion(profile, _criterion("kubernetes", 3))
    assert score.score == 0.5


def test_baseline_counts_related_skills_through_the_taxonomy():
    scorer = BaselineScorer()
    profile = _with_skills(("dbt", 4, 4, 1.0))
    sql = scorer.score_criterion(profile, _criterion("sql", 4))
    assert sql.score == RELATED_FACTOR
    assert "dbt (counts for sql, discounted)" in sql.rationale
    # Not the other way round: SQL isn't evidence of dbt.
    reverse = _with_skills(("sql", 4, 4, 1.0))
    assert scorer.score_criterion(reverse, _criterion("dbt", 4)).score == 0.0
    # The skill itself wins when it scores higher.
    both = _with_skills(("dbt", 4, 4, 1.0), ("sql", 4, 4, 1.0))
    assert scorer.score_criterion(both, _criterion("sql", 4)).score == 1.0


def test_baseline_matches_synonyms():
    profile = _with_skills(("scikit learn", 4, 4, 1.0))
    score = BaselineScorer().score_criterion(profile, _criterion("scikit-learn", 4))
    assert score.score == 1.0


# The LLM scorer


def test_llm_scorer_scores_john_against_fjord_grocery(john, fjord):
    result = match_candidate(john, fjord, LLMScorer(ReplayLLM(STAND_IN)), TODAY)
    assert result.problems == []
    assert result.match.model.startswith("replay:hand-written placeholder")
    scores = _scores(result, fjord)
    assert len(scores) == len(fjord.rubric.criteria) == 10
    assert (
        scores["Hands-on experience with time series forecasting in production"] > 0.8
    )
    assert scores["Experience in retail or e-commerce"] == 1.0
    assert scores["Experience with deep learning for forecasting"] <= 0.2
    assert result.match.total(fjord.rubric) == pytest.approx(0.71, abs=0.005)
    evidence = {e.id: e for e in john.evidence}
    for s in result.match.criterion_scores:
        assert s.evidence_ids and set(s.evidence_ids) <= set(evidence)
    # The stand-in cites the quotes it describes.
    spark = next(
        s
        for s in result.match.criterion_scores
        if s.criterion_id == fjord.rubric.criteria[6].id
    )
    assert evidence[spark.evidence_ids[0]].quote == "Familiar with Spark."


def test_both_scorers_agree_on_johns_strengths_and_gaps(john, fjord):
    baseline = _scores(match_candidate(john, fjord, BaselineScorer(), TODAY), fjord)
    llm = _scores(
        match_candidate(john, fjord, LLMScorer(ReplayLLM(STAND_IN)), TODAY), fjord
    )
    strong = "Hands-on experience with time series forecasting in production"
    for scores in (baseline, llm):
        assert scores[strong] > scores["Strong SQL skills"]
        assert (
            scores["Strong SQL skills"]
            > scores["Experience with Spark or other tools for large datasets"]
        )


class CapturingLLM:
    """Answers every criterion with 0.5 and keeps the prompt it was sent."""

    model = "capturing"

    def __init__(self):
        self.prompts: list[str] = []

    def parse(self, *, system, prompt, output_type):
        self.prompts.append(system + prompt)
        ids = [
            line.split('"')[1] for line in prompt.splitlines() if "<criterion " in line
        ]
        return output_type(
            criteria=[
                ScoredCriterion(criterion=i, score=0.5, rationale="Half.", evidence=[])
                for i in ids
            ]
        )


def test_the_llm_never_sees_names_or_contact_details(fjord):
    profile = _profile(
        experiences=[_role(date(2019, 8, 1), None)],
        quotes=(
            "Jane Roe, jane.roe@example.com, +45 12 34 56 78, github.com/janeroe",
            "Maintained the forecasting service from 2019-08 to 2022-02 (@janeroe).",
        ),
    )
    profile = profile.model_copy(update={"headline": "Jane Roe, data scientist"})
    llm = CapturingLLM()
    result = LLMScorer(llm, names=["Jane Roe", "janeroe"]).score(profile, fjord.rubric)
    assert len(result.scores) == 10
    (sent,) = llm.prompts
    for private in (
        "Jane",
        "Roe",
        "jane.roe",
        "@",
        "12 34 56 78",
        "github.com",
        "cv.pdf",
    ):
        assert private not in sent
    assert "2019-08 to 2022-02" in sent  # Dates aren't phone numbers.
    assert "Maintained the forecasting service" in sent


def test_johns_prompt_has_no_name_or_contacts(john, fjord):
    prompt, evidence, criteria = render_match_prompt(john, fjord.rubric)
    for private in ("John", "Doe", "example.com", "+45"):
        assert private not in prompt
    assert len(evidence) == len(john.evidence)
    assert list(criteria) == [f"C{i}" for i in range(1, 11)]
    # Hard filters are checked in code and never sent.
    assert "Copenhagen" not in prompt.split("<candidate>")[0]


def test_the_scorers_answer_is_checked(fjord):
    rubric = fjord.rubric
    evidence = {"E1": uuid4(), "E2": uuid4()}
    criteria = {f"C{i}": c.id for i, c in enumerate(rubric.criteria, 1)}
    answer = CriterionScores(
        criteria=[
            ScoredCriterion(
                criterion="C1",
                score=0.8,
                rationale=" Good. ",
                evidence=["E1", "E9", "E1"],
            ),
            ScoredCriterion(criterion="C1", score=0.1, rationale="Again.", evidence=[]),
            ScoredCriterion(
                criterion="C2", score=1.4, rationale="Too high.", evidence=["E2"]
            ),
            ScoredCriterion(
                criterion="C99", score=0.5, rationale="Unknown.", evidence=[]
            ),
            *[
                ScoredCriterion(
                    criterion=f"C{i}", score=0.5, rationale="Half.", evidence=[]
                )
                for i in range(4, 11)
            ],
        ]
    )
    result = apply_scores(rubric, answer, evidence, criteria)
    assert result.problems == [
        "C1: scored twice; kept the first",
        "C99: not a criterion; ignored",
        "C1: cited ['E9'], which aren't the candidate's",
        "C2: score 1.4 is outside 0-1; clipped",
        f"C3 ({rubric.criteria[2].description}): not scored",
    ]
    first, second = result.scores[:2]
    assert (first.score, first.rationale, first.evidence_ids) == (
        0.8,
        "Good.",
        [evidence["E1"]],
    )
    assert second.score == 1.0
    assert [s.criterion_id for s in result.scores] == [
        c.id for i, c in enumerate(rubric.criteria) if i != 2
    ]


# Anonymisation


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Write to jane.roe+jobs@mail.example.dk.", f"Write to {REDACTED}."),
        ("Call +45 12 34 56 78 today", f"Call {REDACTED} today"),
        ("Phone: 12345678", f"Phone: {REDACTED}"),
        ("Mobile 20 12 15 10.", f"Mobile {REDACTED}."),
        (
            "See https://janeroe.dev/cv and www.example.com",
            f"See {REDACTED} and {REDACTED}",
        ),
        ("Code at github.com/janeroe.", f"Code at {REDACTED}"),
        ("Follow @janeroe", f"Follow {REDACTED}"),
        (
            "From 2019-08 to 2022-02, 2017 to 2019",
            "From 2019-08 to 2022-02, 2017 to 2019",
        ),
        ("Dates 2019-08-01 and 2022 01 31", "Dates 2019-08-01 and 2022 01 31"),
        (
            "4,000 products across 120 stores, 18%",
            "4,000 products across 120 stores, 18%",
        ),
        ("A/B tests and scikit-learn", "A/B tests and scikit-learn"),
    ],
)
def test_redact(text, expected):
    assert redact(text) == expected


def test_redact_names():
    assert redact("Jane Roe built it; jane roe again", ["Jane Roe"]) == (
        f"{REDACTED} built it; {REDACTED} again"
    )
    # Whole words only, and very short names are ignored.
    assert redact("Janet and Al", ["Jane", "Al"]) == "Janet and Al"


# Matching and ranking


class RefusingScorer:
    model = "refusing"

    def score(self, profile, rubric):
        raise AssertionError("a candidate who failed a hard filter was scored")


def test_a_candidate_failing_a_hard_filter_isnt_scored(john, fjord):
    abroad = john.model_copy(
        update={
            "preferences": john.preferences.model_copy(update={"work_permits": ["US"]})
        }
    )
    result = match_candidate(abroad, fjord, RefusingScorer(), TODAY)
    assert not result.match.passed_hard_filters
    assert result.match.criterion_scores == []
    assert result.match.total(fjord.rubric) == 0.0
    assert [c.name for c in result.filters.failed] == ["work_permit"]


def _scored(rubric, score, passed=True, scored_at=None, model="m"):
    return Match(
        job_id=uuid4(),
        profile_id=uuid4(),
        rubric_version=rubric.version,
        passed_hard_filters=passed,
        criterion_scores=[
            CriterionScore(criterion_id=c.id, score=score, rationale="r")
            for c in rubric.criteria
        ],
        model=model,
        scored_at=scored_at or datetime(2026, 11, 26),
    )


def test_rank_orders_by_total_and_shares_ties():
    rubric = Rubric(criteria=[_criterion("python", 3)])
    low, high, tie, failed = (
        _scored(rubric, 0.2),
        _scored(rubric, 0.9),
        _scored(rubric, 0.9),
        _scored(rubric, 1.0, passed=False),
    )
    ranked = rank([low, failed, tie, high], rubric)
    assert [r.rank for r in ranked] == [1, 1, 3, 4]
    assert [r.total for r in ranked] == [0.9, 0.9, 0.2, 0.0]
    assert {r.match.id for r in ranked[:2]} == {high.id, tie.id}
    assert ranked[-1].match is failed
    # Ties are in a reproducible order.
    assert rank([tie, high], rubric) == rank([high, tie], rubric)


def test_latest_keeps_each_candidates_newest_match():
    rubric = Rubric(criteria=[_criterion("python", 3)])
    old = _scored(rubric, 0.2, scored_at=datetime(2026, 1, 1))
    new = old.model_copy(update={"id": uuid4(), "scored_at": datetime(2026, 2, 1)})
    other = _scored(rubric, 0.5, model="other")
    assert {m.id for m in latest([new, old, other])} == {new.id, other.id}
    assert [m.id for m in latest([new, old, other], model="m")] == [new.id]


def test_match_total_uses_the_scored_criteria_only(john, fjord):
    result = match_candidate(john, fjord, BaselineScorer(), TODAY)
    weights = {c.id: c.weight for c in fjord.rubric.criteria}
    scores = result.match.criterion_scores
    expected = sum(weights[s.criterion_id] * s.score for s in scores) / sum(
        weights[s.criterion_id] for s in scores
    )
    assert result.match.total(fjord.rubric) == pytest.approx(expected)


# unapply match


@pytest.fixture
def db(john, fjord):
    """A database with John (approved) and Fjord Grocery (approved rubric)."""
    init_db()
    repo = Repository.from_url(database_url())
    repo.create_candidate("john", demo=True)
    repo.save_profile("john", john, "assessed")
    repo.create_candidate("draft")  # No profile yet: not matched.
    repo.create_job("fjord")
    repo.save_job("fjord", fjord, "rubric")
    yield repo
    repo.engine.dispose()


def test_match_command_with_the_baseline(db, fjord, capsys):
    assert main(["match", "fjord", "--today", "2026-11-26"]) == 0
    out = capsys.readouterr().out
    assert "rubric version 1: 1 candidates, scored by baseline-v1" in out
    assert "#1  john  total 0.81" in out
    assert "[pass] min_years_experience: 8.9 years of work; job requires 4." in out
    assert "1.00  must_have w5  Strong Python skills" in out
    assert "names no skill" in out
    (stored,) = db.matches(fjord.id)
    assert (stored.model, stored.profile_id) == (BASELINE_MODEL, db.profile("john").id)
    # Matching locked the rubric version.
    fewer = fjord.rubric.model_copy(update={"criteria": fjord.rubric.criteria[:1]})
    with pytest.raises(RubricLocked):
        db.save_job("fjord", fjord.model_copy(update={"rubric": fewer}), "rubric")


def test_match_command_with_the_llm_scorer(db, fjord, tmp_path, capsys):
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "john.json").write_text(
        STAND_IN.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert main(["match", "fjord", "--scorer", "llm", "--replay", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "#1  john  total 0.71" in out
    assert "1.00  nice_to_have w2  Experience in retail or e-commerce" in out
    assert main(["match", "fjord", "--scorer", "llm", "--replay", str(STAND_IN)]) == 0
    assert len(db.matches(fjord.id)) == 2


def test_match_command_refuses_paid_calls_and_saves_nothing(db, fjord, capsys):
    assert main(["match", "fjord", "--scorer", "llm"]) == 3
    assert "paid API call" in capsys.readouterr().err
    missing = main(["match", "fjord", "--scorer", "llm", "--replay", "nowhere"])
    assert missing == 2
    assert db.matches(fjord.id) == []


def test_match_command_needs_an_approved_rubric_and_profiles(db, fjord, capsys):
    db.create_job("draft-job")
    draft = fjord.model_copy(
        update={
            "id": uuid4(),
            "rubric": fjord.rubric.model_copy(update={"approved_at": None}),
        }
    )
    db.save_job("draft-job", draft, "extracted")
    assert main(["match", "draft-job"]) == 2
    assert "isn't approved" in capsys.readouterr().err
    assert main(["match", "nothing"]) == 2
    assert main(["match", "fjord", "--candidates", "draft"]) == 2
    assert "no approved profile" in capsys.readouterr().err
    assert db.matches(draft.id) == db.matches(fjord.id) == []


def test_the_stand_in_is_marked_and_listed():
    record = json.loads(STAND_IN.read_text(encoding="utf-8"))
    assert record["model"] == (
        "hand-written placeholder, not a model answer: re-record with --record"
    )
    listed = (Path(__file__).parents[1] / "docs" / "to-record.md").read_text(
        encoding="utf-8"
    )
    assert "match_john_doe.json" in listed


def test_today_defaults_to_now(john, fjord):
    soon = date.today() + timedelta(days=1)
    assert years_of_experience(john) <= years_of_experience(john, soon)


# The audit log


@pytest.fixture
def pool(db, john):
    """`db` with two more approved candidates: one weaker, one failing a filter."""
    weaker = john.model_copy(update={"id": uuid4(), "skills": john.skills[:3]})
    abroad = john.model_copy(
        update={
            "id": uuid4(),
            "preferences": john.preferences.model_copy(update={"work_permits": ["US"]}),
        }
    )
    for name, profile in (("weaker", weaker), ("abroad", abroad)):
        db.create_candidate(name)
        db.save_profile(name, profile, "assessed")
    return db


def _baseline(name, settings):
    return BaselineScorer()


def test_hashes_survive_the_database_and_see_changes(db, john, fjord):
    assert content_hash(db.profile("john")) == content_hash(john)
    assert content_hash(db.job("fjord").rubric) == content_hash(fjord.rubric)
    assert content_hash(john).startswith("sha256:")
    changed = john.model_copy(update={"headline": john.headline + "!"})
    assert content_hash(changed) != content_hash(john)


def test_matching_records_every_match_and_the_ranking(pool, fjord):
    matching = match_job(pool, "fjord", _baseline, today=TODAY)
    log = pool.audit_log(fjord.id)
    assert [e.kind for e in log] == [AuditKind.MATCH] * 3 + [AuditKind.RANKING]
    assert log[-1] == matching.audit
    for entry in log[:-1]:
        name = next(
            n for n, r in matching.results.items() if r.match.id == entry.match_id
        )
        profile = pool.profile(name)
        assert (entry.profile_id, entry.profile_hash) == (
            profile.id,
            content_hash(profile),
        )
        assert (entry.rubric_version, entry.rubric_hash) == (
            1,
            content_hash(fjord.rubric),
        )
        assert (entry.scorer, entry.model) == ("baseline", BASELINE_MODEL)
        assert Match.model_validate(entry.payload["match"]) == (
            matching.results[name].match
        )
        assert isinstance(entry.recorded_at, datetime)
    abroad = next(e for e in log if e.profile_id == pool.profile("abroad").id)
    outcomes = {f["name"]: f["outcome"] for f in abroad.payload["hard_filters"]}
    assert outcomes["work_permit"] == "fail"
    john_entry = next(e for e in log if e.profile_id == pool.profile("john").id)
    assert "names no skill" in john_entry.payload["problems"][0]
    ranked = log[-1].payload["ranking"]
    assert [r["match"]["id"] for r in ranked] == [
        str(r.match.id) for r in matching.ranking
    ]
    assert [r["rank"] for r in ranked] == [1, 2, 3]
    assert ranked[0]["total"] > ranked[1]["total"] > ranked[2]["total"] == 0.0
    assert log[-1].profile_id is log[-1].profile_hash is None


def test_a_ranking_is_reproduced_from_the_log(pool, john, fjord):
    matching = match_job(pool, "fjord", _baseline, today=TODAY)
    # Later changes elsewhere in the database don't matter: the log is enough.
    pool.save_profile("john", john.model_copy(update={"id": uuid4()}), "assessed")
    (stored,) = pool.audit_log(fjord.id, AuditKind.RANKING)
    again = reproduce_ranking(stored)
    assert [(r.rank, r.total, r.match) for r in again] == [
        (r.rank, r.total, r.match) for r in matching.ranking
    ]
    assert check_ranking(stored, pool.audit_log(fjord.id)) == []
    # Scoring the logged profile versions again gives the logged scores: the
    # baseline is deterministic, and the hash finds the profile that was scored.
    by_hash = {
        content_hash(p): p
        for p in (john, pool.profile("weaker"), pool.profile("abroad"))
    }
    for entry in pool.audit_log(fjord.id, AuditKind.MATCH):
        profile = by_hash[entry.profile_hash]
        rescored = match_candidate(profile, fjord, BaselineScorer(), TODAY).match
        logged = Match.model_validate(entry.payload["match"])
        assert rescored.criterion_scores == logged.criterion_scores
        assert rescored.passed_hard_filters == logged.passed_hard_filters


def test_a_changed_ranking_doesnt_reproduce(pool, fjord):
    entry = match_job(pool, "fjord", _baseline, today=TODAY).audit
    log = pool.audit_log(fjord.id)
    swapped = entry.model_copy(deep=True)
    ranking = swapped.payload["ranking"]
    ranking[0]["match"], ranking[1]["match"] = ranking[1]["match"], ranking[0]["match"]
    problems = check_ranking(swapped, log)
    assert problems and problems[0].startswith("ranking again gives")
    lowered = entry.model_copy(deep=True)
    lowered.payload["ranking"][0]["match"]["criterion_scores"][0]["score"] = 0.0
    assert any("differs from its match entry" in p for p in check_ranking(lowered, log))
    reweighted = entry.model_copy(deep=True)
    reweighted.payload["rubric"]["criteria"][0]["weight"] = 0.5
    assert "the recorded rubric doesn't match its version or hash" in (
        check_ranking(reweighted, log)
    )
    with pytest.raises(ValueError, match="not a ranking"):
        reproduce_ranking(log[0])


def test_the_audit_log_is_append_only(pool, fjord):
    match_job(pool, "fjord", _baseline, today=TODAY)
    first = pool.audit_log(fjord.id)[0]
    with pytest.raises(ValueError, match="already stored"):
        pool.append_audit(first)
    with Session(pool.engine) as s:
        s.get(AuditEntryRow, first.id).model = "changed"
        with pytest.raises(ValueError, match="can't be changed or deleted"):
            s.flush()
        s.rollback()
        s.delete(s.get(AuditEntryRow, first.id))
        with pytest.raises(ValueError, match="can't be changed or deleted"):
            s.flush()
        s.rollback()
    assert pool.audit_log(fjord.id)[0] == first
    assert len(pool.audit_log()) == 4


def test_a_match_and_its_entry_are_saved_together(pool, john, fjord):
    result = match_candidate(john, fjord, BaselineScorer(), TODAY)
    other = match_candidate(john, fjord, BaselineScorer(), TODAY)
    with pytest.raises(ValueError, match="isn't for match"):
        pool.save_match(
            result.match, audit=match_entry(other, john, fjord.rubric, "baseline")
        )
    with pytest.raises(ValueError, match="isn't the one"):
        match_entry(result, pool.profile("weaker"), fjord.rubric, "baseline")
    assert pool.matches(fjord.id) == pool.audit_log() == []


def test_a_refused_match_records_nothing(pool):
    assert main(["match", "fjord", "--scorer", "llm"]) == 3
    assert pool.audit_log() == []


def test_audit_command_lists_and_checks_rankings(pool, capsys):
    assert main(["match", "fjord", "--today", "2026-11-26"]) == 0
    assert main(["match", "fjord", "--scorer", "llm", "--replay", str(STAND_IN)]) == 0
    capsys.readouterr()
    assert main(["audit", "fjord"]) == 0
    out = capsys.readouterr().out
    assert "2 rankings and 6 matches in the audit log" in out
    assert "rubric version 1  baseline (baseline-v1)  3 candidates  reproduced" in out
    assert "llm (replay:hand-written placeholder" in out
    assert "NOT REPRODUCED" not in out
    # Changed behind the repository's back, the log no longer checks out.
    with pool.engine.begin() as connection:
        entry = pool.audit_log(kind=AuditKind.RANKING)[0]
        entry.payload["ranking"][0]["total"] = 1.0
        connection.execute(
            update(AuditEntryRow)
            .where(AuditEntryRow.id == entry.id)
            .values(payload=entry.payload)
        )
    assert main(["audit", "fjord"]) == 1
    assert "NOT REPRODUCED" in capsys.readouterr().out
    assert main(["audit", "nothing"]) == 2
