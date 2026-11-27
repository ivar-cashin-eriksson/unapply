"""What an employer sees of a ranked candidate, and what they ask for next.

The shortlist is anonymised: a candidate is shown by an alias made from their
profile id, never by name, and every text from the profile goes through
`anonymise.redact`, as it does on the way to the LLM scorer. The employer sees what
the scorer saw: the headline, the roles, the quotes and, for each skill the rubric
asks for, the candidate's own level and the estimated level, so candidates can be
compared on both.

From the shortlist, the employer can ask to reveal a candidate (see who they are)
or to request an application from them. Both only record the intent for now: no
payment is taken and nobody's identity is shown (see `Intent`).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from unapply.matching.anonymise import redact
from unapply.matching.baseline import level
from unapply.schemas import Profile, Rubric, SkillLevel, SourceKind
from unapply.taxonomy import Taxonomy, default_taxonomy


class IntentKind(StrEnum):
    """What an employer asks for about a shortlisted candidate."""

    REVEAL = "reveal"
    REQUEST_APPLICATION = "request_application"


class Intent(BaseModel):
    """An employer's request about a candidate on a job's shortlist.

    Only the intent is recorded: revealing will need payment and the candidate's
    consent, and requesting an application will ask the candidate, neither of
    which exists yet.

    Parameters
    ----------
    id : int or None
        Set by the database; None before it is stored.
    job_id : UUID
        The `Job.id` the candidate was shortlisted for.
    profile_id : UUID
        The candidate's profile, as the shortlist shows it.
    kind : IntentKind
        "reveal" or "request_application".
    recorded_at : datetime
        When it was asked for, local time.
    """

    id: int | None = None
    job_id: UUID
    profile_id: UUID
    kind: IntentKind
    recorded_at: datetime = Field(default_factory=datetime.now)


class SkillLevels(BaseModel):
    """A candidate's levels in one skill the rubric asks for.

    Parameters
    ----------
    skill : str
        The rubric's skill, canonical.
    own_level : SkillLevel or None
        The candidate's own level, if they gave one.
    estimated_level : SkillLevel or None
        The level their evidence supports, once estimated.
    confidence : float or None
        How sure the estimate is, from 0 to 1; None without an estimate.
    via : str or None
        The candidate's skill the levels come from when it isn't `skill` itself
        but one whose evidence counts for it through the taxonomy, such as "dbt"
        for "sql". None when the candidate has the skill itself, or no skill
        that counts for it (then both levels are None).
    """

    skill: str
    own_level: SkillLevel | None = None
    estimated_level: SkillLevel | None = None
    confidence: float | None = None
    via: str | None = None


class AnonymousEvidence(BaseModel):
    """A quote from the candidate's material, with names and contacts removed.

    Parameters
    ----------
    id : UUID
        The `Evidence.id`, as cited by criterion scores.
    source : str
        Where it is from: "cv", "linkedin", "github", "free_text", or "candidate
        statement" for an interview answer.
    quote : str
        The quote, redacted.
    """

    id: UUID
    source: str
    quote: str


class AnonymousExperience(BaseModel):
    """A role, project or education, with names and contacts removed.

    Parameters
    ----------
    title : str
        Role or programme title.
    organisation : str
        Employer, client or institution.
    start : date or None
        When it started, if known.
    end : date or None
        When it ended; None means now or unknown.
    summary : str
        What the candidate did.
    """

    title: str
    organisation: str
    start: date | None = None
    end: date | None = None
    summary: str = ""


class AnonymousCandidate(BaseModel):
    """A candidate as an employer sees them on a shortlist, before any reveal.

    Parameters
    ----------
    profile_id : UUID
        The candidate's profile, as in the ranking.
    alias : str
        What to call them, such as "Candidate 3F2A", from the profile id.
    headline : str
        One-line summary, redacted.
    experiences : list of AnonymousExperience
        Their roles, in profile order.
    evidence : list of AnonymousEvidence
        Every quote, so cited evidence can be shown.
    skills : list of SkillLevels
        Levels in each skill the rubric asks for, in rubric order.
    """

    profile_id: UUID
    alias: str
    headline: str
    experiences: list[AnonymousExperience]
    evidence: list[AnonymousEvidence]
    skills: list[SkillLevels]


def alias(profile_id: UUID) -> str:
    """Make the name an employer knows a candidate by before a reveal.

    Parameters
    ----------
    profile_id : UUID
        The candidate's profile.

    Returns
    -------
    str
        "Candidate " and the first four hex digits of the id, such as "Candidate
        3F2A". It says nothing about the person, and stays the same for as long as
        the profile does.
    """
    return f"Candidate {profile_id.hex[:4].upper()}"


def rubric_skills(rubric: Rubric, taxonomy: Taxonomy | None = None) -> list[str]:
    """List the skills a rubric's criteria ask for, once each.

    Parameters
    ----------
    rubric : Rubric
        The rubric.
    taxonomy : Taxonomy or None, optional
        To canonicalise the names, by default `default_taxonomy()`.

    Returns
    -------
    list of str
        Canonical names, in the order of the criteria; criteria without a skill
        are skipped.
    """
    taxonomy = taxonomy or default_taxonomy()
    skills: list[str] = []
    for c in rubric.criteria:
        if c.skill and (name := taxonomy.canonical(c.skill)) not in skills:
            skills.append(name)
    return skills


def skill_levels(
    profile: Profile, skill: str, taxonomy: Taxonomy | None = None
) -> SkillLevels:
    """Find a candidate's own and estimated level in a skill.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    skill : str
        The skill asked for, canonical or a synonym.
    taxonomy : Taxonomy or None, optional
        For synonyms and related skills, by default `default_taxonomy()`.

    Returns
    -------
    SkillLevels
        From the candidate's skill itself if they have it; otherwise from the skill
        whose evidence counts for it with the highest level (as the baseline scorer
        weighs own and estimated levels), named in `via`; otherwise no levels.
    """
    taxonomy = taxonomy or default_taxonomy()
    wanted = taxonomy.canonical(skill)
    related = taxonomy.supporting(wanted)
    direct = [s for s in profile.skills if taxonomy.canonical(s.name) == wanted]
    others = [s for s in profile.skills if taxonomy.canonical(s.name) in related]
    found = direct[0] if direct else max(others, key=level, default=None)
    if found is None:
        return SkillLevels(skill=wanted)
    return SkillLevels(
        skill=wanted,
        own_level=found.self_level,
        estimated_level=found.estimate.level if found.estimate else None,
        confidence=found.estimate.confidence if found.estimate else None,
        via=None if direct else taxonomy.canonical(found.name),
    )


def anonymous_candidate(
    profile: Profile,
    rubric: Rubric,
    names: list[str] | None = None,
    taxonomy: Taxonomy | None = None,
) -> AnonymousCandidate:
    """Build the employer's view of a candidate on a job's shortlist.

    Parameters
    ----------
    profile : Profile
        The candidate's profile, with estimates.
    rubric : Rubric
        The rubric they were ranked against; its skills are the ones compared.
    names : list of str or None, optional
        Names to remove from every text, such as the candidate's GitHub username.
    taxonomy : Taxonomy or None, optional
        For synonyms and related skills, by default `default_taxonomy()`.

    Returns
    -------
    AnonymousCandidate
        No name, no contact details, no source file names, and no claim support.
    """
    taxonomy = taxonomy or default_taxonomy()
    kinds = {s.id: s.kind for s in profile.sources}

    def text(value: str) -> str:
        return redact(value, names)

    def source(evidence_source: UUID) -> str:
        kind = kinds.get(evidence_source)
        if kind is None:
            return "unknown"
        return "candidate statement" if kind == SourceKind.INTERVIEW else kind.value

    return AnonymousCandidate(
        profile_id=profile.id,
        alias=alias(profile.id),
        headline=text(profile.headline),
        experiences=[
            AnonymousExperience(
                title=text(x.title),
                organisation=text(x.organisation),
                start=x.start,
                end=x.end,
                summary=text(x.summary),
            )
            for x in profile.experiences
        ],
        evidence=[
            AnonymousEvidence(id=e.id, source=source(e.source_id), quote=text(e.quote))
            for e in profile.evidence
        ],
        skills=[
            skill_levels(profile, s, taxonomy) for s in rubric_skills(rubric, taxonomy)
        ],
    )
