"""Candidate profile: experiences, skills with self-reported and estimated levels, all backed by evidence."""

from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class SourceKind(StrEnum):
    CV = "cv"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    FREE_TEXT = "free_text"
    INTERVIEW = "interview"


class Source(BaseModel):
    """A piece of material the candidate uploaded or linked."""

    id: UUID = Field(default_factory=uuid4)
    kind: SourceKind
    uri: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.now)


class Evidence(BaseModel):
    """A snippet from a source that supports a claim or an estimate."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    quote: str = Field(description="Verbatim text, or a description of the signal (e.g. a repo).")
    locator: str | None = Field(default=None, description="Page, section, URL or line range.")


class SkillLevel(IntEnum):
    """Common scale for self-reported and estimated levels."""

    AWARE = 1  # Knows what it is, has tried it
    BASIC = 2  # Has used it on small tasks with guidance
    WORKING = 3  # Uses it on own work without help
    ADVANCED = 4  # Designs non-trivial systems with it, helps others
    EXPERT = 5  # Deep, recognised expertise


class SkillEstimate(BaseModel):
    """What the evidence supports. The candidate can see this, along with the reasons."""

    level: SkillLevel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    model: str = Field(description="Model or method that produced the estimate, for auditing.")
    estimated_at: datetime = Field(default_factory=datetime.now)


class Skill(BaseModel):
    name: str = Field(description="Canonical name, e.g. 'python', 'kafka'.")
    self_level: SkillLevel | None = None
    estimate: SkillEstimate | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)

    @property
    def gap(self) -> int | None:
        """Self-reported minus estimated level (positive means the self-report is higher)."""
        if self.self_level is None or self.estimate is None:
            return None
        return int(self.self_level) - int(self.estimate.level)


class Experience(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    organisation: str
    start: date | None = None
    end: date | None = Field(default=None, description="None means current.")
    summary: str = ""
    skills: list[str] = Field(default_factory=list, description="Canonical skill names.")
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Experience:
        if self.start and self.end and self.end < self.start:
            raise ValueError("experience ends before it starts")
        return self


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class Preferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    salary_min: int | None = None
    salary_currency: str | None = None
    work_permits: list[str] = Field(
        default_factory=list, description="Country codes, e.g. 'DK', 'EU'."
    )
    dealbreakers: list[str] = Field(default_factory=list)


class ClaimSupport(BaseModel):
    """How well self-reports are backed by evidence and agree across sources.

    This is deliberately not an 'honesty' score: it measures evidence, not character, and the
    candidate can always see it, together with the reasons.
    """

    score: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list)
    inconsistencies: list[str] = Field(
        default_factory=list, description="E.g. dates differing between sources."
    )
    computed_at: datetime = Field(default_factory=datetime.now)


class Profile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    headline: str = ""
    sources: list[Source] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    claim_support: ClaimSupport | None = None
    approved_by_candidate_at: datetime | None = None

    @model_validator(mode="after")
    def _evidence_references_resolve(self) -> Profile:
        source_ids = {s.id for s in self.sources}
        evidence_ids = {e.id for e in self.evidence}
        for e in self.evidence:
            if e.source_id not in source_ids:
                raise ValueError(f"evidence {e.id} points to unknown source {e.source_id}")
        referenced = [i for x in self.experiences for i in x.evidence_ids]
        referenced += [i for s in self.skills for i in s.evidence_ids]
        referenced += [i for s in self.skills if s.estimate for i in s.estimate.evidence_ids]
        missing = set(referenced) - evidence_ids
        if missing:
            raise ValueError(f"unknown evidence ids: {sorted(map(str, missing))}")
        return self

    def skill(self, name: str) -> Skill | None:
        return next((s for s in self.skills if s.name == name), None)
