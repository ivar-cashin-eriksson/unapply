"""The jobs a candidate connected to, how far they got, and their success rate.

For each job the candidate connected to, they see how far they got (connected,
revealed, asked to apply, applied or declined) and their fit (`unapply.jobs.fit`).
Over all of them, a **success rate**: the share of jobs where the employer revealed
them, and where the employer asked them to apply.

For each job they can also **compare themselves with groups** of the other
candidates on it, whatever their own stage: those the employer revealed, those it
asked to apply, and those who applied. A group is shown only when it has at least
`MIN_GROUP` others, and only as aggregates: the median of the group's own levels in
the skills it lists most, next to the candidate's own level (a spider chart), and
the skills where the candidate stands out (rated higher than most of them, or lists
what few of them do) or is behind (lacks a common skill, or rated it lower). A
group's level in a skill is used only where at least `MIN_GROUP` of them rated it.

Everything comes from the candidates' own levels (`candidate_view`, so nothing from
the assessment), names skills and never a criterion, weight or minimum level from a
rubric, nor anything about one of the others. It is worked out in plain code each
time it is asked for; no model is called and nothing is stored.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from unapply.app.forms import candidate_view
from unapply.dashboard import MIN_GROUP
from unapply.jobs.board import Listing, connected, find_listing
from unapply.jobs.fit import Fit, fit
from unapply.jobs.hiring import Stage
from unapply.schemas import Profile, SkillLevel
from unapply.taxonomy import Taxonomy, default_taxonomy

if TYPE_CHECKING:
    from unapply.db.repository import Repository

# A skill is common in a group when at least this share of them list it.
COMMON_SHARE = 0.5
# A skill is rare in a group when at most this share of them list it.
RARE_SHARE = 0.2
# The most skills each list names.
MAX_TIPS = 5
# The most skills a group's chart has, those the group lists most.
MAX_AXES = 8

# The stages at or past each step.
REVEALED = {Stage.REVEALED, Stage.REQUESTED, Stage.APPLIED, Stage.DECLINED}
REQUESTED = {Stage.REQUESTED, Stage.APPLIED, Stage.DECLINED}


class Group(StrEnum):
    """A group of other candidates on a job, by how far they got.

    The groups overlap: everyone asked to apply was revealed, and everyone who
    applied was asked to.
    """

    REVEALED = "revealed"
    REQUESTED = "requested"
    APPLIED = "applied"


# The stages each group takes in.
GROUP_STAGES = {
    Group.REVEALED: REVEALED,
    Group.REQUESTED: REQUESTED,
    Group.APPLIED: {Stage.APPLIED},
}


class GroupSkill(BaseModel):
    """One skill on a group's chart: the candidate's own level and the group's.

    Parameters
    ----------
    skill : str
        Canonical name.
    own_level : SkillLevel or None
        The candidate's own level; None when they don't list it or gave none.
    median : float
        The median of the group's own levels in it, from 1 to 5, over at least
        `MIN_GROUP` of them.
    """

    skill: str
    own_level: SkillLevel | None = None
    median: float


class GroupComparison(BaseModel):
    """The candidate next to one group of the others on a job, in aggregate.

    Parameters
    ----------
    group : Group
        Which group.
    skills : list of GroupSkill
        The chart: up to `MAX_AXES` of the skills the group lists most that at
        least `MIN_GROUP` of them rated; by name, so a skill keeps its place
        relative to the others when the candidate switches between groups.
    higher : list of str
        Skills the candidate rated above the group's median; furthest above first.
    rare : list of str
        Skills the candidate lists that at most `RARE_SHARE` of the group list;
        highest own level first.
    missing : list of str
        Skills at least `COMMON_SHARE` of the group list that the candidate's
        profile doesn't, and that don't follow from its skills in the taxonomy;
        most common first.
    lower : list of str
        Common skills the candidate rated below the group's median; most common
        first.
    """

    group: Group
    skills: list[GroupSkill] = Field(default_factory=list)
    higher: list[str] = Field(default_factory=list)
    rare: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    lower: list[str] = Field(default_factory=list)


class JobOutcome(BaseModel):
    """One job a candidate is connected to, and how far they got.

    Parameters
    ----------
    job : str
        The job's name.
    listing : Listing or None
        Its listing, or None if it is no longer on the board.
    connected_at : datetime
        When the candidate connected, local time; for a pool candidate of a demo
        job, when the job was posted.
    stage : Stage
        How far they got.
    fit : Fit or None
        Their fit, while the job is on the board.
    groups : list of GroupComparison
        The candidate next to each group of others on the job that has at least
        `MIN_GROUP` of them, in `Group` order; empty when none has.
    """

    job: str
    listing: Listing | None
    connected_at: datetime
    stage: Stage
    fit: Fit | None = None
    groups: list[GroupComparison] = Field(default_factory=list)


class CandidateJobs(BaseModel):
    """The jobs a candidate connected to, and their success rate over them.

    Parameters
    ----------
    candidate : str
        The candidate.
    jobs : list of JobOutcome
        Newest connection first.
    connected : int
        Jobs they are connected to.
    revealed : int
        Of those, jobs where the employer revealed them.
    requested : int
        Jobs where the employer asked them to apply, whatever they answered.
    applied : int
        Jobs they applied for.
    revealed_rate : float or None
        `revealed` out of `connected`, from 0 to 1; None with no connections.
    requested_rate : float or None
        `requested` out of `connected`, from 0 to 1; None with no connections.
    min_group : int
        The fewest others a group is shown with.
    """

    candidate: str
    jobs: list[JobOutcome]
    connected: int
    revealed: int
    requested: int
    applied: int
    revealed_rate: float | None
    requested_rate: float | None
    min_group: int = MIN_GROUP


def connected_jobs(repo: Repository, candidate: str) -> list[str]:
    """List the jobs a candidate is connected to.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.

    Returns
    -------
    list of str
        Job names, sorted: those they connected to, and for a pool candidate every
        demo job.
    """
    return [job for job in repo.job_names() if candidate in connected(repo, job)]


def group_profiles(
    repo: Repository, job: str, candidate: str
) -> dict[Group, list[Profile]]:
    """Find the profiles of the other candidates on a job, by group.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.
    candidate : str
        The candidate asking, who is left out of every group.

    Returns
    -------
    dict of Group to list of Profile
        Every group, empty or not, with their current profiles as candidates see
        them (without the assessment). Copies of the John Doe demo never count:
        they are John again.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    found: dict[Group, list[Profile]] = {g: [] for g in Group}
    for p in repo.progresses(job=job):
        if p.candidate == candidate or not any(
            p.stage in stages for stages in GROUP_STAGES.values()
        ):
            continue
        settings = repo.settings(p.candidate)
        if settings.get("demo") and not settings.get("pool"):
            continue
        if (profile := repo.profile(p.candidate)) is None:
            continue
        shown = candidate_view(profile)
        for group, stages in GROUP_STAGES.items():
            if p.stage in stages:
                found[group].append(shown)
    return found


def compare_group(
    profile: Profile, group: Group, others: list[Profile], taxonomy: Taxonomy
) -> GroupComparison | None:
    """Compare a candidate's own levels with a group of others'.

    Parameters
    ----------
    profile : Profile
        The candidate's profile; only skill names and own levels are used.
    group : Group
        Which group `others` is.
    others : list of Profile
        The group; only their skill names and own levels are used.
    taxonomy : Taxonomy
        To canonicalise names, and for the skills that follow from the candidate's.

    Returns
    -------
    GroupComparison or None
        None for fewer than `MIN_GROUP` others. A group's median in a skill is
        used only where at least `MIN_GROUP` of them rated it.
    """
    if len(others) < MIN_GROUP:
        return None
    listed: Counter[str] = Counter()
    levels: dict[str, list[int]] = defaultdict(list)
    for other in others:
        skills = {taxonomy.canonical(s.name): s.self_level for s in other.skills}
        listed.update(skills.keys())
        for skill, level in skills.items():
            if level is not None:
                levels[skill].append(int(level))
    medians = {s: float(median(v)) for s, v in levels.items() if len(v) >= MIN_GROUP}
    by_listed = sorted(listed, key=lambda s: (-listed[s], s))
    common = [s for s in by_listed if listed[s] >= COMMON_SHARE * len(others)]

    own = {taxonomy.canonical(s.name): s.self_level for s in profile.skills}
    rated = {s: int(v) for s, v in own.items() if v is not None}
    implied = set().union(*(taxonomy.implied(s) for s in own)) if own else set()

    axes = sorted(
        [s for s in by_listed if s in medians][:MAX_AXES],
        key=lambda s: (s.casefold(), s),
    )
    higher = sorted(
        (s for s in rated if s in medians and rated[s] > medians[s]),
        key=lambda s: (medians[s] - rated[s], s),
    )
    rare = sorted(
        (s for s in own if listed[s] <= RARE_SHARE * len(others)),
        key=lambda s: (-rated.get(s, 0), listed[s], s),
    )
    return GroupComparison(
        group=group,
        skills=[
            GroupSkill(skill=s, own_level=own.get(s), median=medians[s]) for s in axes
        ],
        higher=higher[:MAX_TIPS],
        rare=rare[:MAX_TIPS],
        missing=[s for s in common if s not in own and s not in implied][:MAX_TIPS],
        lower=[
            s for s in common if s in rated and s in medians and rated[s] < medians[s]
        ][:MAX_TIPS],
    )


def candidate_jobs(
    repo: Repository, candidate: str, taxonomy: Taxonomy | None = None
) -> CandidateJobs:
    """List a candidate's jobs with how far they got, and their success rate.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    taxonomy : Taxonomy or None, optional
        By default `default_taxonomy()`.

    Returns
    -------
    CandidateJobs
        Never anything from the assessment or a rubric, nor about one other
        candidate.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    taxonomy = taxonomy or default_taxonomy()
    repo.settings(candidate)  # NotFound for an unknown candidate.
    full = repo.profile(candidate)
    profile = candidate_view(full) if full is not None else None
    jobs = []
    for job in connected_jobs(repo, candidate):
        listing = find_listing(repo, job)
        consent = repo.consent(candidate, job)
        progress = repo.progress(candidate, job)
        stage = progress.stage if progress else Stage.CONNECTED
        if consent is not None:
            connected_at = consent.granted_at
        else:
            posted = repo.job(job)
            connected_at = (
                listing.posted_at
                if listing
                else (posted.created_at if posted else datetime.now())
            )
        groups = []
        if profile is not None:
            for group, others in group_profiles(repo, job, candidate).items():
                if found := compare_group(profile, group, others, taxonomy):
                    groups.append(found)
        jobs.append(
            JobOutcome(
                job=job,
                listing=listing,
                connected_at=connected_at,
                stage=stage,
                fit=fit(repo, candidate, job),
                groups=groups,
            )
        )
    jobs.sort(key=lambda j: (-j.connected_at.timestamp(), j.job))
    n = len(jobs)
    revealed = sum(j.stage in REVEALED for j in jobs)
    requested = sum(j.stage in REQUESTED for j in jobs)
    return CandidateJobs(
        candidate=candidate,
        jobs=jobs,
        connected=n,
        revealed=revealed,
        requested=requested,
        applied=sum(j.stage == Stage.APPLIED for j in jobs),
        revealed_rate=revealed / n if n else None,
        requested_rate=requested / n if n else None,
    )
