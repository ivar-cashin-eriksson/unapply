"""Job, rubric and match schemas.

A job's rubric is hidden from candidates, so they can't tailor their profile to it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from unapply.schemas.profile import SkillLevel, WorkMode


class CriterionKind(StrEnum):
    """How much a criterion matters."""

    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class Criterion(BaseModel):
    """One thing the job asks for.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    kind : CriterionKind
        Must-have or nice-to-have.
    description : str
        What is asked for, such as "Has run Kafka in production".
    skill : str or None
        Canonical skill name, if the criterion maps to one skill.
    min_level : SkillLevel or None
        Lowest acceptable level of `skill`.
    weight : float
        Relative weight in the total score. Must be positive.
    """

    id: UUID = Field(default_factory=uuid4)
    kind: CriterionKind
    description: str
    skill: str | None = None
    min_level: SkillLevel | None = None
    weight: float = Field(default=1.0, gt=0.0)


class HardFilters(BaseModel):
    """Requirements checked deterministically, before any LLM scoring.

    Parameters
    ----------
    locations : list of str
        Where the job is. Empty means anywhere.
    work_modes : list of WorkMode
        Work modes the job offers. Empty means any.
    required_work_permits : list of str
        ISO country codes, or "EU", the candidate must be allowed to work in.
    """

    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    required_work_permits: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    """What a job is scored on. Never shown to candidates.

    Extracted from the job ad and edited by the recruiter.

    Parameters
    ----------
    version : int
        Increases with every edit, so matches can say which version they used.
    hard_filters : HardFilters
        Pass/fail requirements.
    criteria : list of Criterion
        Scored requirements.
    """

    version: int = 1
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    criteria: list[Criterion] = Field(default_factory=list)


class Job(BaseModel):
    """A job posted by a company.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    company : str
        Company name.
    title : str
        Job title.
    ad_text : str
        The job ad as posted.
    rubric : Rubric
        What candidates are scored on.
    reveal_quota : int
        How many of the top candidates the company pays to reveal.
    created_at : datetime
        When the job was posted, local time.
    """

    id: UUID = Field(default_factory=uuid4)
    company: str
    title: str
    ad_text: str
    rubric: Rubric = Field(default_factory=Rubric)
    reveal_quota: int = Field(default=10, ge=1)
    created_at: datetime = Field(default_factory=datetime.now)


class CriterionScore(BaseModel):
    """How well a candidate meets one criterion.

    Parameters
    ----------
    criterion_id : UUID
        The `Criterion` scored.
    score : float
        From 0 (not met) to 1 (fully met).
    rationale : str
        Why, in plain language.
    evidence_ids : list of UUID
        `Evidence` the score is based on. Empty means no evidence was found.
    """

    criterion_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)


class Match(BaseModel):
    """One candidate scored against one job, with enough detail to audit later.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    job_id : UUID
        The `Job`.
    profile_id : UUID
        The candidate's `Profile`.
    rubric_version : int
        The `Rubric.version` used.
    passed_hard_filters : bool
        Whether the candidate passed the hard filters.
    criterion_scores : list of CriterionScore
        One score per criterion.
    model : str
        Model or method that produced the scores.
    scored_at : datetime
        When the match was scored, local time.
    """

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    profile_id: UUID
    rubric_version: int
    passed_hard_filters: bool
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    model: str
    scored_at: datetime = Field(default_factory=datetime.now)

    def total(self, rubric: Rubric) -> float:
        """Compute the weighted mean of the criterion scores.

        Parameters
        ----------
        rubric : Rubric
            The rubric the scores refer to, for the criterion weights. Scores for
            criteria not in it are ignored.

        Returns
        -------
        float
            From 0 to 1. 0 if the candidate failed the hard filters or nothing was
            scored.
        """
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
