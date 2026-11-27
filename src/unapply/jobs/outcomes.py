"""The jobs a candidate connected to, how far they got, and their success rate.

For each job the candidate connected to, they see how far they got (connected,
revealed, asked to apply, applied or declined) and their fit (`unapply.jobs.fit`).
Over all of them, a **success rate**: the share of jobs where the employer revealed
them, and where the employer asked them to apply.

For a job where they weren't revealed, they also see **skills common among the
candidates who were**, which they don't list or rated lower than most of them did.
These come from the revealed candidates' own levels only (`candidate_view`, so
nothing from the assessment), and are shown only when at least `MIN_GROUP` others
were revealed. They name skills and nothing else: never a level, a count, a weight,
a minimum level or a criterion, and never anything about one of the revealed. A
level is compared only where at least `MIN_GROUP` of the revealed rated the skill.

Everything is worked out in plain code each time it is asked for; no model is
called and nothing is stored.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from unapply.app.forms import candidate_view
from unapply.dashboard import MIN_GROUP
from unapply.jobs.board import Listing, connected, find_listing
from unapply.jobs.fit import Fit, fit
from unapply.jobs.hiring import Stage
from unapply.schemas import Profile
from unapply.taxonomy import Taxonomy, default_taxonomy

if TYPE_CHECKING:
    from unapply.db.repository import Repository

# A skill is common among the revealed when at least this share of them list it.
COMMON_SHARE = 0.5
# The most skills each list of tips names.
MAX_TIPS = 5

# The stages at or past each step.
REVEALED = {Stage.REVEALED, Stage.REQUESTED, Stage.APPLIED, Stage.DECLINED}
REQUESTED = {Stage.REQUESTED, Stage.APPLIED, Stage.DECLINED}


class RevealedSkills(BaseModel):
    """Skills common among the candidates a job revealed, which the candidate lacks.

    Parameters
    ----------
    missing : list of str
        Common skills the candidate's profile doesn't list, and that don't follow
        from its skills in the taxonomy; most common first.
    lower : list of str
        Common skills the candidate rated lower than most of the revealed who rated
        it did; most common first.
    """

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
    revealed_skills : RevealedSkills or None
        For a job where they weren't revealed, the skills common among those who
        were; None when they were revealed, or when fewer than `MIN_GROUP` others
        were.
    """

    job: str
    listing: Listing | None
    connected_at: datetime
    stage: Stage
    fit: Fit | None = None
    revealed_skills: RevealedSkills | None = None


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
        The fewest other revealed candidates skills are suggested from.
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


def revealed_profiles(repo: Repository, job: str, candidate: str) -> list[Profile]:
    """Find the profiles of the other candidates a job revealed.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.
    candidate : str
        The candidate asking, who is left out.

    Returns
    -------
    list of Profile
        Their current profiles as candidates see them (without the assessment).
        Copies of the John Doe demo never count: they are John again.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    found = []
    for p in repo.progresses(job=job):
        if p.revealed_at is None or p.candidate == candidate:
            continue
        settings = repo.settings(p.candidate)
        if settings.get("demo") and not settings.get("pool"):
            continue
        if (profile := repo.profile(p.candidate)) is not None:
            found.append(candidate_view(profile))
    return found


def revealed_skills(
    profile: Profile, revealed: list[Profile], taxonomy: Taxonomy
) -> RevealedSkills | None:
    """Find the skills common among revealed candidates that a profile lacks.

    Parameters
    ----------
    profile : Profile
        The candidate's profile; only skill names and own levels are used.
    revealed : list of Profile
        The other candidates the job revealed; only their skill names and own
        levels are used.
    taxonomy : Taxonomy
        To canonicalise names, and for the skills that follow from the candidate's.

    Returns
    -------
    RevealedSkills or None
        None for fewer than `MIN_GROUP` revealed. A skill is common when at least
        `COMMON_SHARE` of them list it. It is lower when the candidate's own level
        is below the median of the revealed who rated it, and at least
        `MIN_GROUP` of them did.
    """
    if len(revealed) < MIN_GROUP:
        return None
    listed: Counter[str] = Counter()
    levels: dict[str, list[int]] = defaultdict(list)
    for other in revealed:
        skills = {taxonomy.canonical(s.name): s.self_level for s in other.skills}
        listed.update(skills.keys())
        for skill, level in skills.items():
            if level is not None:
                levels[skill].append(int(level))
    common = sorted(
        (s for s, n in listed.items() if n >= COMMON_SHARE * len(revealed)),
        key=lambda s: (-listed[s], s),
    )

    own = {taxonomy.canonical(s.name): s.self_level for s in profile.skills}
    implied = set().union(*(taxonomy.implied(s) for s in own)) if own else set()
    missing = [s for s in common if s not in own and s not in implied]
    lower = [
        s
        for s in common
        if own.get(s) is not None
        and len(levels[s]) >= MIN_GROUP
        and int(own[s]) < median(levels[s])  # type: ignore[arg-type]
    ]
    return RevealedSkills(missing=missing[:MAX_TIPS], lower=lower[:MAX_TIPS])


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
        tips = None
        if stage not in REVEALED and profile is not None:
            tips = revealed_skills(
                profile, revealed_profiles(repo, job, candidate), taxonomy
            )
        jobs.append(
            JobOutcome(
                job=job,
                listing=listing,
                connected_at=connected_at,
                stage=stage,
                fit=fit(repo, candidate, job),
                revealed_skills=tips,
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
