"""Candidate profile schemas.

A profile holds a candidate's experiences, skills and preferences. Every claim points to
evidence, and every skill has a self-reported and an estimated level.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class SourceKind(StrEnum):
    """Kind of material a candidate can upload or link."""

    CV = "cv"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    FREE_TEXT = "free_text"
    INTERVIEW = "interview"


class Source(BaseModel):
    """A piece of material the candidate uploaded or linked.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    kind : SourceKind
        What the material is.
    uri : str or None
        Where the material is stored or lives online, if anywhere.
    uploaded_at : datetime
        When it was added, local time.
    """

    id: UUID = Field(default_factory=uuid4)
    kind: SourceKind
    uri: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.now)


class Evidence(BaseModel):
    """A snippet from a source that supports a claim or an estimate.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    source_id : UUID
        The `Source` the snippet comes from. Must be in the same profile.
    quote : str
        Verbatim text from the source, or a description of a non-text signal such as
        a GitHub repository.
    locator : str or None
        Where in the source: page, section, URL or line range.
    """

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    quote: str
    locator: str | None = None


class SkillLevel(IntEnum):
    """Scale shared by self-reported and estimated skill levels."""

    AWARE = 1  # Knows what it is, has tried it
    BASIC = 2  # Has used it on small tasks with guidance
    WORKING = 3  # Uses it on own work without help
    ADVANCED = 4  # Designs non-trivial systems with it, helps others
    EXPERT = 5  # Deep, recognised expertise


class SkillCategory(StrEnum):
    """What kind of skill it is. Also the axes employers can group skills by."""

    TECHNOLOGY = "technology"  # Languages, libraries, tools, platforms
    METHOD = "method"  # Techniques, such as Gaussian processes or A/B testing
    DOMAIN = "domain"  # Industries and problem areas, such as pharmaceuticals
    SOFT_SKILL = "soft_skill"  # Leadership, mentoring, communication
    LANGUAGE = "language"  # Spoken languages
    CERTIFICATION = "certification"


class SkillEstimate(BaseModel):
    """The skill level the evidence supports.

    Not shown in the candidate app, but part of the candidate's data: provided on a
    data access request.

    Parameters
    ----------
    level : SkillLevel
        Estimated level.
    confidence : float
        How sure the estimate is, from 0 (guess) to 1 (certain).
    rationale : str
        Why the evidence supports this level, in plain language.
    evidence_ids : list of UUID
        The `Evidence` the estimate is based on.
    model : str
        Model or method that produced the estimate, kept for auditing.
    estimated_at : datetime
        When the estimate was made, local time.
    """

    level: SkillLevel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    model: str
    estimated_at: datetime = Field(default_factory=datetime.now)


class Skill(BaseModel):
    """A skill with the candidate's own level and the estimated level.

    Parameters
    ----------
    name : str
        Canonical lowercase name, such as "python" or "kafka".
    category : SkillCategory or None
        What kind of skill it is, if known.
    self_level : SkillLevel or None
        The level the candidate reports, if they gave one.
    estimate : SkillEstimate or None
        The level the evidence supports, once it has been estimated.
    evidence_ids : list of UUID
        `Evidence` that mentions the skill.
    """

    name: str
    category: SkillCategory | None = None
    self_level: SkillLevel | None = None
    estimate: SkillEstimate | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)

    @property
    def gap(self) -> int | None:
        """Self-reported level minus estimated level.

        Returns
        -------
        int or None
            Positive when the self-report is higher than the estimate. None if either
            level is missing.
        """
        if self.self_level is None or self.estimate is None:
            return None
        return int(self.self_level) - int(self.estimate.level)


class Experience(BaseModel):
    """A job, project or education entry.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    title : str
        Role or programme title.
    organisation : str
        Employer, client or institution.
    start : date or None
        First day, if known.
    end : date or None
        Last day. None means it is current or unknown.
    summary : str
        What the candidate did.
    skills : list of str
        Canonical names of the skills used.
    evidence_ids : list of UUID
        `Evidence` for the entry.

    Raises
    ------
    ValueError
        If `end` is before `start`.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str
    organisation: str
    start: date | None = None
    end: date | None = None
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dates_in_order(self) -> Experience:
        if self.start and self.end and self.end < self.start:
            raise ValueError("experience ends before it starts")
        return self


class WorkMode(StrEnum):
    """Where the work happens."""

    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class Preferences(BaseModel):
    """What the candidate wants from a job.

    Parameters
    ----------
    locations : list of str
        Acceptable cities or regions.
    work_modes : list of WorkMode
        Acceptable work modes. Empty means any.
    salary_min : int or None
        Minimum yearly gross salary, in `salary_currency`.
    salary_currency : str or None
        ISO 4217 code, such as "DKK".
    work_permits : list of str
        Where the candidate may work: ISO country codes, or "EU".
    dealbreakers : list of str
        Things the candidate won't accept, in their own words.
    """

    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    salary_min: int | None = None
    salary_currency: str | None = None
    work_permits: list[str] = Field(default_factory=list)
    dealbreakers: list[str] = Field(default_factory=list)


class ClaimSupport(BaseModel):
    """How well self-reports are backed by evidence and agree across sources.

    This is deliberately not an "honesty" score: it measures evidence, not character,
    and it is explained by the estimates behind it. Not shown in the candidate app,
    but part of the candidate's data. It is shown (internally, and later to employers)
    as counts of each kind of finding rather than one number, which hides too much; how
    findings should combine into a score is still open (see `penalty_score`).

    Parameters
    ----------
    rated : int
        How many skills the candidate gave a level.
    overclaims : list of str
        Skills the candidate rates clearly higher than the evidence supports.
    underclaims : list of str
        Skills the candidate rates clearly lower than the evidence supports.
    unverified : list of str
        Skills the candidate rates clearly higher than the evidence shows, where the
        evidence says little either way. The candidate is asked about them.
    unsupported_claims : list of str
        Skills backed only by the candidate's own statements.
    inconsistencies : list of str
        Disagreements between sources, such as different dates for the same job.
    score : float or None
        Optional single score from 0 to 1, for experiments. Not set by default.
    computed_at : datetime
        When this was computed, local time.
    """

    rated: int = Field(default=0, ge=0)
    overclaims: list[str] = Field(default_factory=list)
    underclaims: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    computed_at: datetime = Field(default_factory=datetime.now)


class Profile(BaseModel):
    """A candidate's structured profile.

    Parameters
    ----------
    id : UUID
        Generated if not given.
    headline : str
        One-line summary of the candidate.
    sources : list of Source
        Everything the profile was built from.
    evidence : list of Evidence
        Snippets from `sources` that back the claims.
    experiences : list of Experience
        Jobs, projects and education.
    skills : list of Skill
        Skills with self-reported and estimated levels.
    preferences : Preferences
        What the candidate wants from a job.
    claim_support : ClaimSupport or None
        How well the claims are supported, once computed.
    approved_by_candidate_at : datetime or None
        When the candidate approved the profile. None means it is still a draft.

    Raises
    ------
    ValueError
        If evidence points to an unknown source, or anything points to unknown
        evidence.
    """

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
                raise ValueError(
                    f"evidence {e.id} points to unknown source {e.source_id}"
                )
        referenced = [i for x in self.experiences for i in x.evidence_ids]
        referenced += [i for s in self.skills for i in s.evidence_ids]
        referenced += [
            i for s in self.skills if s.estimate for i in s.estimate.evidence_ids
        ]
        missing = set(referenced) - evidence_ids
        if missing:
            raise ValueError(f"unknown evidence ids: {sorted(map(str, missing))}")
        return self

    def skill(self, name: str) -> Skill | None:
        """Look up a skill by canonical name.

        Parameters
        ----------
        name : str
            Canonical skill name, such as "python".

        Returns
        -------
        Skill or None
            The skill, or None if the profile doesn't list it.
        """
        return next((s for s in self.skills if s.name == name), None)
