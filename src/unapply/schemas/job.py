"""Jobs, their (hidden) rubrics and match results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from unapply.schemas.profile import SkillLevel, WorkMode


class CriterionKind(StrEnum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class Criterion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: CriterionKind
    description: str = Field(description="E.g. 'Has run Kafka in production'.")
    skill: str | None = Field(default=None, description="Canonical skill name, if it maps to one.")
    min_level: SkillLevel | None = None
    weight: float = Field(default=1.0, gt=0.0)


class HardFilters(BaseModel):
    """Checked deterministically, before any LLM scoring."""

    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    required_work_permits: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    """Extracted from the job ad and edited by the recruiter. Never shown to candidates."""

    version: int = 1
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    criteria: list[Criterion] = Field(default_factory=list)


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company: str
    title: str
    ad_text: str
    rubric: Rubric = Field(default_factory=Rubric)
    reveal_quota: int = Field(default=10, ge=1, description="Top-k the company pays to reveal.")
    created_at: datetime = Field(default_factory=datetime.now)


class CriterionScore(BaseModel):
    criterion_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_ids: list[UUID] = Field(
        default_factory=list, description="Empty means no evidence found."
    )


class Match(BaseModel):
    """One candidate scored against one job. Stored with enough detail to audit later."""

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    profile_id: UUID
    rubric_version: int
    passed_hard_filters: bool
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    model: str
    scored_at: datetime = Field(default_factory=datetime.now)

    def total(self, rubric: Rubric) -> float:
        """Weighted mean of criterion scores; 0 if hard filters failed."""
        if not self.passed_hard_filters:
            return 0.0
        weights = {c.id: c.weight for c in rubric.criteria}
        scored = [
            (weights[s.criterion_id], s.score)
            for s in self.criterion_scores
            if s.criterion_id in weights
        ]
        total_weight = sum(w for w, _ in scored)
        return sum(w * s for w, s in scored) / total_weight if total_weight else 0.0
