import pytest
from pydantic import ValidationError

from unapply.schemas import (
    Criterion,
    CriterionKind,
    CriterionScore,
    Evidence,
    Match,
    Profile,
    Rubric,
    Skill,
    SkillEstimate,
    SkillLevel,
    Source,
    SourceKind,
)


def _profile_with_python(self_level: SkillLevel, estimated: SkillLevel) -> Profile:
    src = Source(kind=SourceKind.CV)
    ev = Evidence(
        source_id=src.id, quote="Built a Python ETL service processing 2M rows/day"
    )
    return Profile(
        sources=[src],
        evidence=[ev],
        skills=[
            Skill(
                name="python",
                self_level=self_level,
                evidence_ids=[ev.id],
                estimate=SkillEstimate(
                    level=estimated,
                    confidence=0.7,
                    rationale="One production service",
                    evidence_ids=[ev.id],
                    model="test",
                ),
            )
        ],
    )


def test_skill_gap_is_self_minus_estimate():
    p = _profile_with_python(SkillLevel.EXPERT, SkillLevel.WORKING)
    assert p.skill("python").gap == 2


def test_unknown_evidence_reference_is_rejected():
    src = Source(kind=SourceKind.CV)
    with pytest.raises(ValidationError, match="unknown evidence"):
        Profile(
            sources=[src],
            skills=[Skill(name="python", evidence_ids=[Source(kind=SourceKind.CV).id])],
        )


def test_evidence_must_point_to_known_source():
    with pytest.raises(ValidationError, match="unknown source"):
        Profile(evidence=[Evidence(source_id=Source(kind=SourceKind.CV).id, quote="x")])


def test_match_total_is_weighted_and_zero_when_filtered_out():
    must = Criterion(kind=CriterionKind.MUST_HAVE, description="Python", weight=3)
    nice = Criterion(kind=CriterionKind.NICE_TO_HAVE, description="Kafka", weight=1)
    rubric = Rubric(criteria=[must, nice])
    scores = [
        CriterionScore(criterion_id=must.id, score=1.0, rationale=""),
        CriterionScore(criterion_id=nice.id, score=0.0, rationale=""),
    ]
    p = _profile_with_python(SkillLevel.WORKING, SkillLevel.WORKING)
    kw = {
        "job_id": p.id,
        "profile_id": p.id,
        "rubric_version": 1,
        "criterion_scores": scores,
        "model": "test",
    }
    assert Match(passed_hard_filters=True, **kw).total(rubric) == pytest.approx(0.75)
    assert Match(passed_hard_filters=False, **kw).total(rubric) == 0.0
