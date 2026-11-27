"""A candidate's dashboard: an overview of their own profile, without the assessment.

It shows the candidate's skills by area (the taxonomy's categories), each with their
own level and how many quotes from their material mention it; how their own levels
compare with other candidates' own levels; and tips on skills to develop. Everything
is worked out in plain code from candidate views of the profiles
(`unapply.app.forms.candidate_view`), so no estimate or claim support can reach it,
and no model is called.

Comparisons are aggregates over at least `MIN_GROUP` other candidates, never one of
them: a skill fewer of them rated isn't compared. A demo candidate is compared with
the synthetic pool, a real candidate with the other real candidates whose profile is
approved. Tips name skills only: the skills the jobs on the board ask for most that
the candidate doesn't list, and the skills the taxonomy says follow from theirs. They
never say which job asks for a skill, nor anything else from a rubric.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from pydantic import BaseModel, Field

from unapply.app.forms import candidate_view
from unapply.db.repository import Repository
from unapply.jobs.board import listings
from unapply.matching.shortlist import rubric_skills
from unapply.schemas import Profile, SkillCategory, SkillLevel, SourceKind
from unapply.taxonomy import Taxonomy, default_taxonomy

# The fewest other candidates an aggregate is shown over.
MIN_GROUP = 5
# How many skills the jobs on the board ask for are suggested.
IN_DEMAND = 5


class Comparison(BaseModel):
    """Other candidates' own levels in a skill, in aggregate.

    Parameters
    ----------
    candidates : int
        Other candidates who rated themselves in the skill; at least `MIN_GROUP`.
    levels : list of int
        How many of them gave each level: `levels[0]` counts level 1 (aware), up to
        `levels[4]` for level 5 (expert).
    median : float
        The median of their levels, from 1 to 5.
    """

    candidates: int
    levels: list[int]
    median: float


class DashboardSkill(BaseModel):
    """One of the candidate's skills on their dashboard.

    Parameters
    ----------
    name : str
        Canonical name.
    self_level : SkillLevel or None
        The candidate's own level, None if they gave none.
    documents : int
        Quotes from their documents (CV, LinkedIn, GitHub, other files) that mention
        it. A count of their own material, not a judgement of it.
    statements : int
        Their own statements about it: answers and notes from the review.
    comparison : Comparison or None
        Other candidates' own levels in it; None when fewer than `MIN_GROUP` rated
        it.
    """

    name: str
    self_level: SkillLevel | None = None
    documents: int = 0
    statements: int = 0
    comparison: Comparison | None = None


class Area(BaseModel):
    """The candidate's skills in one area.

    Parameters
    ----------
    category : SkillCategory or None
        The area, from the taxonomy, or the profile where the taxonomy doesn't know
        the skill; None for skills in no area.
    skills : list of DashboardSkill
        Highest own level first, then by name.
    """

    category: SkillCategory | None
    skills: list[DashboardSkill]


class FollowingSkill(BaseModel):
    """A skill the taxonomy says follows from skills the candidate has.

    Parameters
    ----------
    skill : str
        Canonical name of the skill, which the profile doesn't list.
    because : list of str
        The candidate's skills it follows from, sorted.
    """

    skill: str
    because: list[str]


class Dashboard(BaseModel):
    """A candidate's overview of their own profile.

    Parameters
    ----------
    candidate : str
        The candidate.
    approved : bool
        Whether the profile is approved.
    skills : int
        How many skills the profile lists.
    rated : int
        How many of them the candidate gave a level.
    documents : int
        Quotes from their documents in the profile.
    statements : int
        Their own statements in the profile.
    areas : list of Area
        The skills by area, in `SkillCategory` order, skills in no area last.
    compared_with : int
        How many other candidates the levels are compared with; 0 when fewer than
        `MIN_GROUP`, and then nothing is compared.
    min_group : int
        The fewest other candidates a comparison is shown over.
    in_demand : list of str
        Skills the jobs on the board ask for that the profile doesn't list and that
        don't follow from its skills, most asked for first.
    following : list of FollowingSkill
        Skills that follow from the candidate's, which the profile doesn't list;
        those following from most of their skills first.
    """

    candidate: str
    approved: bool
    skills: int
    rated: int
    documents: int
    statements: int
    areas: list[Area]
    compared_with: int
    min_group: int = MIN_GROUP
    in_demand: list[str] = Field(default_factory=list)
    following: list[FollowingSkill] = Field(default_factory=list)


def comparison_group(repo: Repository, name: str) -> list[Profile]:
    """Find the other candidates a candidate's levels are compared with.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The candidate.

    Returns
    -------
    list of Profile
        Approved profiles, as candidates see them (without the assessment): the
        synthetic pool's for a demo candidate, so copies of the demo never count;
        other real candidates' otherwise.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    demo = bool(repo.settings(name).get("demo"))
    group = []
    for other in repo.candidate_names():
        if other == name:
            continue
        settings = repo.settings(other)
        if (bool(settings.get("pool")) if demo else not settings.get("demo")) and (
            profile := repo.profile(other)
        ):
            if profile.approved_by_candidate_at is not None:
                group.append(candidate_view(profile))
    return group


def compare(levels: list[SkillLevel]) -> Comparison | None:
    """Sum up other candidates' own levels in a skill.

    Parameters
    ----------
    levels : list of SkillLevel
        One level per other candidate who rated themselves in the skill.

    Returns
    -------
    Comparison or None
        None for fewer than `MIN_GROUP` levels.
    """
    if len(levels) < MIN_GROUP:
        return None
    counts = Counter(int(v) for v in levels)
    return Comparison(
        candidates=len(levels),
        levels=[counts[v] for v in range(1, 6)],
        median=float(median(int(v) for v in levels)),
    )


def demand(repo: Repository, taxonomy: Taxonomy) -> Counter[str]:
    """Count how many jobs on the board ask for each skill.

    Parameters
    ----------
    repo : Repository
        The database.
    taxonomy : Taxonomy
        To canonicalise the names.

    Returns
    -------
    Counter of str
        Canonical skill name to the number of jobs whose current, approved rubric
        has a criterion on it.
    """
    counts: Counter[str] = Counter()
    for x in listings(repo):
        job = repo.job(x.name)
        if job is not None:
            counts.update(rubric_skills(job.rubric, taxonomy))
    return counts


def dashboard(
    repo: Repository, name: str, taxonomy: Taxonomy | None = None
) -> Dashboard:
    """Build a candidate's dashboard from their profile, the others' and the board.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The candidate; they must have a profile, approved or not.
    taxonomy : Taxonomy or None, optional
        By default `default_taxonomy()`.

    Returns
    -------
    Dashboard
        Never anything from the assessment, nor about one other candidate.

    Raises
    ------
    NotFound
        If there is no such candidate.
    ValueError
        If the candidate has no profile yet.
    """
    taxonomy = taxonomy or default_taxonomy()
    repo.settings(name)  # NotFound for an unknown candidate.
    full = repo.profile(name)
    if full is None:
        raise ValueError("No profile yet.")
    profile = candidate_view(full)

    group = comparison_group(repo, name)
    others: dict[str, list[SkillLevel]] = defaultdict(list)
    for other in group:
        rated = {
            taxonomy.canonical(s.name): s.self_level
            for s in other.skills
            if s.self_level is not None
        }
        for skill, level in rated.items():
            others[skill].append(level)
    compared = len(group) >= MIN_GROUP

    kinds = {s.id: s.kind for s in profile.sources}
    kind_of = {e.id: kinds[e.source_id] for e in profile.evidence}
    by_area: dict[SkillCategory | None, list[DashboardSkill]] = defaultdict(list)
    for s in profile.skills:
        known = taxonomy.get(s.name)
        area = known.category if known and known.category else s.category
        statements = sum(kind_of[i] == SourceKind.INTERVIEW for i in s.evidence_ids)
        by_area[area].append(
            DashboardSkill(
                name=s.name,
                self_level=s.self_level,
                documents=len(s.evidence_ids) - statements,
                statements=statements,
                comparison=compare(others[taxonomy.canonical(s.name)])
                if compared
                else None,
            )
        )
    areas = [
        Area(
            category=c,
            skills=sorted(by_area[c], key=lambda s: (-(s.self_level or 0), s.name)),
        )
        for c in [*SkillCategory, None]
        if by_area.get(c)
    ]

    own = {taxonomy.canonical(s.name) for s in profile.skills}
    follows: dict[str, set[str]] = defaultdict(set)
    for skill in own:
        for implied in taxonomy.implied(skill) - own:
            follows[implied].add(skill)
    following = sorted(
        (FollowingSkill(skill=k, because=sorted(v)) for k, v in follows.items()),
        key=lambda f: (-len(f.because), f.skill),
    )
    wanted = demand(repo, taxonomy)
    in_demand = sorted(
        (s for s in wanted if s not in own and s not in follows),
        key=lambda s: (-wanted[s], s),
    )[:IN_DEMAND]

    statements = sum(k == SourceKind.INTERVIEW for k in kind_of.values())
    return Dashboard(
        candidate=name,
        approved=profile.approved_by_candidate_at is not None,
        skills=len(profile.skills),
        rated=sum(s.self_level is not None for s in profile.skills),
        documents=len(profile.evidence) - statements,
        statements=statements,
        areas=areas,
        compared_with=len(group) if compared else 0,
        in_demand=in_demand,
        following=following,
    )
