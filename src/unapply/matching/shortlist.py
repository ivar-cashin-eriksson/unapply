"""What an employer sees of a ranked candidate, and what they ask for next.

The shortlist is anonymised: a candidate is shown by an alias made from their
profile id (an adjective and an animal or object, such as "Cobalt Otter", unique
within the job) and an abstract avatar drawn from it, never by name, and every text from the profile goes through
`anonymise.redact`, as it does on the way to the LLM scorer. The employer sees what
the scorer saw: the headline, the roles, the quotes (once the employer reveals the
candidate) and, for each skill the rubric asks for, the candidate's own level and
the estimated level, so candidates can be compared on both.

From the shortlist, the employer reveals a candidate and then asks them to apply
(see `unapply.jobs.hiring`). Before that existed, both only recorded an `Intent`;
those are kept as history.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from unapply.matching.anonymise import redact
from unapply.matching.baseline import level
from unapply.schemas import DatePrecision, Profile, Rubric, SkillLevel, SourceKind
from unapply.taxonomy import Taxonomy, default_taxonomy


class IntentKind(StrEnum):
    """What an employer asks for about a shortlisted candidate."""

    REVEAL = "reveal"
    REQUEST_APPLICATION = "request_application"


class Intent(BaseModel):
    """An early employer request about a candidate on a job's shortlist: history.

    Only the intent was recorded, before revealing and requesting applications
    were built (`unapply.jobs.hiring`), which replaced it. Kept as history; no
    longer made.

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
    start_precision : DatePrecision
        Whether `start` is known to the month or only to the year.
    end_precision : DatePrecision
        The same for `end`.
    summary : str
        What the candidate did.
    """

    title: str
    organisation: str
    start: date | None = None
    end: date | None = None
    start_precision: DatePrecision = DatePrecision.MONTH
    end_precision: DatePrecision = DatePrecision.MONTH
    summary: str = ""


class AnonymousCandidate(BaseModel):
    """A candidate as an employer sees them on a shortlist, before any reveal.

    Parameters
    ----------
    profile_id : UUID
        The candidate's profile, as in the ranking.
    alias : str
        What to call them, such as "Cobalt Otter", from the profile id.
    avatar : int
        The alias's number, for the frontend to draw their avatar from.
    headline : str
        One-line summary, redacted.
    experiences : list of AnonymousExperience
        Their roles, in profile order.
    evidence : list of AnonymousEvidence
        Every quote, so cited evidence can be shown; empty where quotes are
        hidden (on the shortlist, until the candidate is revealed). Role
        summaries are empty there too.
    skills : list of SkillLevels
        Levels in each skill the rubric asks for, in rubric order.
    """

    profile_id: UUID
    alias: str
    avatar: int
    headline: str
    experiences: list[AnonymousExperience]
    evidence: list[AnonymousEvidence]
    skills: list[SkillLevels]


# Words for aliases: neutral colours, textures, weather and patterns, then animals and
# everyday objects. None is a person's name (so "Amber", "Robin" or "Jade" are left
# out), none judges the person ("Swift", "Clever") or hints at a body, age, gender or
# skin colour ("Tiny", "Old", "Ivory", "Walrus"). 48 x 40 = 1920 aliases.
ADJECTIVES = (
    "Azure", "Cobalt", "Cinnabar", "Crimson", "Cyan", "Inky", "Lilac", "Teal",
    "Mustard", "Cerulean", "Magenta", "Minty", "Navy", "Plum", "Turquoise",
    "Vermilion", "Chartreuse", "Aqua", "Cloudy", "Foggy", "Frosty", "Breezy",
    "Starry", "Lunar", "Solar", "Polar", "Mossy", "Leafy", "Pebbled", "Velvet",
    "Woolly", "Glassy", "Marble", "Granite", "Quartz", "Cedar", "Birch", "Spruce",
    "Striped", "Spotted", "Dotted", "Checkered", "Spiral", "Zigzag", "Wavy",
    "Tidal", "Rainy", "Snowy",
)  # fmt: skip
NOUNS = (
    "Otter", "Heron", "Badger", "Puffin", "Lynx", "Kestrel", "Gecko", "Ibis",
    "Marmot", "Narwhal", "Pelican", "Tapir", "Toucan", "Wombat", "Yak", "Zebra",
    "Beaver", "Bison", "Dolphin", "Falcon", "Ferret", "Koala", "Lemur", "Moose",
    "Newt", "Octopus", "Panda", "Quokka", "Salmon", "Seal", "Kettle", "Lantern",
    "Compass", "Anchor", "Comet", "Pebble", "Acorn", "Teapot", "Kite", "Glacier",
)  # fmt: skip
ALIASES = len(ADJECTIVES) * len(NOUNS)


class Identity(BaseModel):
    """What an employer knows a candidate by before a reveal.

    Parameters
    ----------
    alias : str
        An adjective and an animal or object, such as "Cobalt Otter".
    avatar : int
        The alias's number, from 0 to `ALIASES` - 1, from which the frontend draws
        the candidate's abstract avatar, so two aliases never share one.
    """

    alias: str
    avatar: int


def _identity(index: int) -> Identity:
    """Name the alias with a number."""
    adjective, noun = divmod(index, len(NOUNS))
    return Identity(alias=f"{ADJECTIVES[adjective]} {NOUNS[noun]}", avatar=index)


def _index(profile_id: UUID) -> int:
    """Pick a candidate's preferred alias number from their profile id."""
    digest = hashlib.sha256(profile_id.bytes).digest()
    return int.from_bytes(digest[:8], "big") % ALIASES


def identity(profile_id: UUID) -> Identity:
    """Make a candidate's alias and avatar from their profile id alone.

    Parameters
    ----------
    profile_id : UUID
        The candidate's profile.

    Returns
    -------
    Identity
        The same for as long as the profile is. Two candidates can share it; use
        `identities` for everyone on a job, which never gives one twice.
    """
    return _identity(_index(profile_id))


def identities(profile_ids: Iterable[UUID]) -> dict[UUID, Identity]:
    """Give each of a job's candidates an alias and avatar no one else on it has.

    Parameters
    ----------
    profile_ids : iterable of UUID
        The job's candidates. Up to `ALIASES` of them.

    Returns
    -------
    dict of UUID to Identity
        Each candidate's `identity`, unless a candidate with a lower profile id
        already has it; then the next free alias number after it. Each depends only
        on the profile ids, not on their order.

    Raises
    ------
    ValueError
        If there are more candidates than aliases.
    """
    ids = sorted(set(profile_ids))
    if len(ids) > ALIASES:
        raise ValueError(f"only {ALIASES} aliases for {len(ids)} candidates")
    taken: set[int] = set()
    found: dict[UUID, Identity] = {}
    for profile_id in ids:
        index = _index(profile_id)
        while index in taken:
            index = (index + 1) % ALIASES
        taken.add(index)
        found[profile_id] = _identity(index)
    return found


def alias(profile_id: UUID) -> str:
    """Make the name an employer knows a candidate by before a reveal.

    Parameters
    ----------
    profile_id : UUID
        The candidate's profile.

    Returns
    -------
    str
        `identity(profile_id).alias`, such as "Cobalt Otter". It says nothing about
        the person, and stays the same for as long as the profile does.
    """
    return identity(profile_id).alias


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
    known_as: Identity | None = None,
    quotes: bool = True,
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
    known_as : Identity or None, optional
        Their alias and avatar on this job (see `identities`), by default
        `identity(profile.id)`.
    quotes : bool, optional
        Whether to include their quotes and the summaries of their roles, which
        often repeat the material word for word; by default True. The shortlist
        leaves both out until the employer reveals the candidate.

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

    known_as = known_as or identity(profile.id)
    return AnonymousCandidate(
        profile_id=profile.id,
        alias=known_as.alias,
        avatar=known_as.avatar,
        headline=text(profile.headline),
        experiences=[
            AnonymousExperience(
                title=text(x.title),
                organisation=text(x.organisation),
                start=x.start,
                end=x.end,
                start_precision=x.start_precision,
                end_precision=x.end_precision,
                summary=text(x.summary) if quotes else "",
            )
            for x in profile.experiences
        ],
        evidence=[
            AnonymousEvidence(id=e.id, source=source(e.source_id), quote=text(e.quote))
            for e in profile.evidence
        ]
        if quotes
        else [],
        skills=[
            skill_levels(profile, s, taxonomy) for s in rubric_skills(rubric, taxonomy)
        ],
    )
