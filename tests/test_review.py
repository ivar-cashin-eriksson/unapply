"""Review sheet tests. Synthetic data only."""

from datetime import date

import pytest
import yaml

from unapply.review import ReviewError, apply_review_sheet, export_review_sheet
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


@pytest.fixture
def profile():
    cv = Source(kind=SourceKind.CV)
    kafka = Evidence(source_id=cv.id, quote="Built Kafka pipelines:\n5M events/day")
    lang = Evidence(source_id=cv.id, quote="Danish (fluent)")
    return Profile(
        headline="Data engineer",
        # The notes file backs nothing, but is kept as a record of what was used.
        sources=[cv, Source(kind=SourceKind.FREE_TEXT, uri="notes.md")],
        evidence=[kafka, lang],
        experiences=[
            Experience(
                title="Data Engineer",
                organisation="Acme",
                start=date(2021, 3, 1),
                end=date(2024, 1, 1),
                summary='Pipelines with "quotes": and colons',
                evidence_ids=[kafka.id],
            )
        ],
        # Sorted by name, as extraction and review keep them.
        skills=[
            Skill(
                name="danish",
                category=SkillCategory.LANGUAGE,
                self_level=SkillLevel.ADVANCED,
                evidence_ids=[lang.id],
            ),
            Skill(
                name="kafka", category=SkillCategory.TECHNOLOGY, evidence_ids=[kafka.id]
            ),
        ],
    )


def _edit(sheet: str, change) -> str:
    data = yaml.safe_load(sheet)
    change(data)
    return yaml.safe_dump(data, allow_unicode=True)


def test_unedited_sheet_round_trips_without_approval(profile):
    sheet = export_review_sheet(profile)
    assert "# cv: Built Kafka pipelines: 5M events/day" in sheet
    assert 'start: "2021-03"' in sheet
    # A bare year, which YAML reads back as a number.
    assert "    end: 2024\n" in sheet
    reviewed = apply_review_sheet(profile, sheet)
    assert reviewed.model_dump(
        exclude={"approved_by_candidate_at"}
    ) == profile.model_dump(exclude={"approved_by_candidate_at"})
    assert reviewed.approved_by_candidate_at is None


def test_levels_removals_corrections_additions_and_approval(profile):
    def change(d):
        d["approve"] = True
        d["skills"][1]["level"] = 4  # kafka
        d["skills"][0]["keep"] = False  # danish
        d["experiences"][0]["end"] = "2024-06"
        d["add_skills"] = [
            {
                "name": " Matlab ",
                "category": "technology",
                "level": 2,
                "note": "Coursework at university, 2016.",
            }
        ]

    reviewed = apply_review_sheet(profile, _edit(export_review_sheet(profile), change))
    assert reviewed.approved_by_candidate_at is not None
    assert [s.name for s in reviewed.skills] == ["kafka", "matlab"]
    assert reviewed.skill("kafka").self_level == SkillLevel.ADVANCED
    assert reviewed.experiences[0].end == date(2024, 6, 1)
    [note] = [
        e for e in reviewed.evidence if e.id in reviewed.skill("matlab").evidence_ids
    ]
    kinds = {s.id: s.kind for s in reviewed.sources}
    assert kinds[note.source_id] == SourceKind.INTERVIEW
    # Danish's evidence is no longer used by anything, so it is dropped.
    assert "Danish (fluent)" not in [e.quote for e in reviewed.evidence]


def test_deleting_a_row_removes_the_item(profile):
    def change(d):
        d["skills"] = [s for s in d["skills"] if s["name"] != "danish"]
        d["experiences"] = []

    reviewed = apply_review_sheet(profile, _edit(export_review_sheet(profile), change))
    assert [s.name for s in reviewed.skills] == ["kafka"]
    assert reviewed.experiences == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda d: d.update(profile="00000000-0000-0000-0000-000000000000"),
            "is for profile",
        ),
        (lambda d: d["skills"][0].update(level=7), 'skills "danish" level'),
        (lambda d: d["skills"][0].update(name="rust"), "unknown skills"),
        (lambda d: d["skills"].append(dict(d["skills"][0])), "more than once"),
        (lambda d: d["experiences"][0].update(start="March 2021"), "isn't YYYY"),
        (
            lambda d: d.update(
                add_skills=[{"name": "go", "category": "technology", "note": " "}]
            ),
            "where you used",
        ),
        (
            lambda d: d.update(
                add_skills=[{"name": "Kafka", "category": "technology", "note": "x"}]
            ),
            "already in skills",
        ),
        (lambda d: d.update(colour="blue"), "colour"),
    ],
)
def test_invalid_sheets_are_rejected_with_a_reason(profile, change, message):
    with pytest.raises(ReviewError, match=message):
        apply_review_sheet(profile, _edit(export_review_sheet(profile), change))


def test_broken_yaml_is_rejected(profile):
    with pytest.raises(ReviewError, match="valid YAML"):
        apply_review_sheet(profile, "skills: [unclosed")
