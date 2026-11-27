"""The job board: listings candidates browse, and connecting a profile to a job.

A listing is what a candidate may read about a job: the ad as posted, its vacancies,
how many candidates connected, were revealed, were asked to apply and applied, and
the place, work modes and seniority to filter by. Never the rubric's criteria,
weights or minimum levels. Place and work modes come from the approved rubric's hard
filters, which are copied from the ad ("Copenhagen, hybrid"), so they say nothing the
ad doesn't; seniority is read from the title.

Connecting is the candidate's one way in to a job: it grants the job consent
(`unapply.consent`) with its time, so the job can match and rank the profile
anonymously and the employer can reveal it later. Only approved profiles can
connect; a connection can be withdrawn until the employer reveals the candidate.
Synthetic pool candidates (`unapply.evaluation.pool`) count as connected to every
demo job, so the demos always have people to rank.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from unapply.consent import Consent
from unapply.matching.filters import same_place
from unapply.schemas import Job, WorkMode

if TYPE_CHECKING:
    from unapply.db.repository import Repository


class Seniority(StrEnum):
    """How senior a job is, read from its title."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


# Title words for each level; a title with none of them is mid-level. Checked in
# this order, so "Senior Lead" is lead and "Junior" wins over everything.
_SENIORITY = [
    (Seniority.JUNIOR, re.compile(r"\b(junior|graduate|trainee|intern|entry)\b", re.I)),
    (
        Seniority.LEAD,
        re.compile(r"\b(lead|principal|head|staff|chief|director)\b", re.I),
    ),
    (Seniority.SENIOR, re.compile(r"\b(senior|sr)\b", re.I)),
]


def seniority(title: str) -> Seniority:
    """Read a job's seniority from its title.

    Parameters
    ----------
    title : str
        The job title, such as "Senior Data Scientist".

    Returns
    -------
    Seniority
        Junior, senior or lead if the title says so (such as "Graduate", "Sr." or
        "Head of"), otherwise mid.
    """
    for level, pattern in _SENIORITY:
        if pattern.search(title):
            return level
    return Seniority.MID


class ListingCounts(BaseModel):
    """How far a job's candidates got: shown on its listing and to the employer.

    Parameters
    ----------
    connected : int
        Candidates connected to the job (for a demo job, the pool too).
    revealed : int
        Candidates the employer revealed.
    requested : int
        Candidates asked to apply, whatever they answered.
    applied : int
        Applications received.
    """

    connected: int = 0
    revealed: int = 0
    requested: int = 0
    applied: int = 0


class Listing(BaseModel):
    """A job as candidates see it on the board.

    Parameters
    ----------
    name : str
        The job's name in the database, for its address.
    company : str
        The company.
    title : str
        The job title.
    ad : str
        The job ad as posted, in Markdown.
    vacancies : int
        How many people the job hires.
    locations : list of str
        Where the job is, as the ad says. Empty means anywhere.
    work_modes : list of WorkMode
        The work modes it offers. Empty means any.
    seniority : Seniority
        Read from the title.
    posted_at : datetime
        When the job was posted, local time.
    demo : bool
        Whether it is a demo job, with an invented company.
    counts : ListingCounts or None
        How many candidates connected, were revealed, were asked to apply and
        applied. None where they weren't counted.
    """

    name: str
    company: str
    title: str
    ad: str
    vacancies: int
    locations: list[str]
    work_modes: list[WorkMode]
    seniority: Seniority
    posted_at: datetime
    demo: bool = False
    counts: ListingCounts | None = None


class Board(BaseModel):
    """The listings found, and what the board can be filtered by.

    Parameters
    ----------
    listings : list of Listing
        The listings that match, newest first.
    total : int
        How many listings the board has, before filtering.
    locations : list of str
        Every location on the board, sorted, for the location filter.
    work_modes : list of WorkMode
        Every work mode on the board, in `WorkMode` order.
    seniorities : list of Seniority
        Every seniority on the board, junior first.
    """

    listings: list[Listing]
    total: int
    locations: list[str]
    work_modes: list[WorkMode]
    seniorities: list[Seniority]


class ConnectError(ValueError):
    """A candidate can't connect to or withdraw from a job. The message says why."""


def listing(
    name: str, job: Job, demo: bool = False, counts: ListingCounts | None = None
) -> Listing:
    """Make a job's listing: what candidates may read about it.

    Parameters
    ----------
    name : str
        The job's name in the database.
    job : Job
        The job, with its current rubric; only the rubric's place and work modes
        are used.
    demo : bool, optional
        Whether it is a demo job.
    counts : ListingCounts or None, optional
        How far its candidates got, if counted.

    Returns
    -------
    Listing
        The listing, without the rubric.
    """
    filters = job.rubric.hard_filters
    return Listing(
        name=name,
        company=job.company,
        title=job.title,
        ad=job.ad_text,
        vacancies=job.vacancies,
        locations=filters.locations,
        work_modes=filters.work_modes,
        seniority=seniority(job.title),
        posted_at=job.created_at,
        demo=demo,
        counts=counts,
    )


def listings(repo: Repository) -> list[Listing]:
    """List every job on the board: those whose current rubric is approved.

    A job whose rubric is still a draft isn't ready to match anyone, so it isn't
    listed.

    Parameters
    ----------
    repo : Repository
        The database.

    Returns
    -------
    list of Listing
        Newest first, then by name.
    """
    found = []
    for name in repo.job_names():
        job = repo.job(name)
        if job is not None and job.rubric.approved_at is not None:
            demo = bool(repo.job_settings(name).get("demo"))
            found.append(listing(name, job, demo, count(repo, name)))
    return sorted(found, key=lambda x: (-x.posted_at.timestamp(), x.name))


def find_listing(repo: Repository, name: str) -> Listing | None:
    """Read one job's listing, if it is on the board.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The job.

    Returns
    -------
    Listing or None
        The listing, or None if there is no such job or it isn't on the board.
    """
    if name not in repo.job_names():
        return None
    job = repo.job(name)
    if job is None or job.rubric.approved_at is None:
        return None
    demo = bool(repo.job_settings(name).get("demo"))
    return listing(name, job, demo, count(repo, name))


def search(
    found: list[Listing],
    query: str = "",
    location: str | None = None,
    work_mode: WorkMode | None = None,
    level: Seniority | None = None,
) -> Board:
    """Filter the board's listings.

    Parameters
    ----------
    found : list of Listing
        Every listing on the board.
    query : str, optional
        Free text. A listing matches if each word is in its title, company or ad,
        ignoring case.
    location : str or None, optional
        Only jobs in this place (see `same_place`), and jobs offering remote work.
    work_mode : WorkMode or None, optional
        Only jobs offering this work mode, and jobs that leave it open.
    level : Seniority or None, optional
        Only jobs at this seniority.

    Returns
    -------
    Board
        The listings that match, in the order given, and the filter options.
    """
    words = query.casefold().split()

    def matches(x: Listing) -> bool:
        text = f"{x.title}\n{x.company}\n{x.ad}".casefold()
        if any(w not in text for w in words):
            return False
        if location and not (
            WorkMode.REMOTE in x.work_modes
            or not x.locations
            or any(same_place(location, place) for place in x.locations)
        ):
            return False
        if work_mode and x.work_modes and work_mode not in x.work_modes:
            return False
        return level is None or x.seniority == level

    return Board(
        listings=[x for x in found if matches(x)],
        total=len(found),
        locations=sorted({p for x in found for p in x.locations}),
        work_modes=[m for m in WorkMode if any(m in x.work_modes for x in found)],
        seniorities=[s for s in Seniority if any(x.seniority == s for x in found)],
    )


def connected(repo: Repository, job: str) -> list[str]:
    """List the candidates connected to a job: the ones it may match and rank.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.

    Returns
    -------
    list of str
        Candidate names, sorted: everyone who connected, and for a demo job every
        synthetic pool candidate too.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    names = {c.candidate for c in repo.consents(job)}
    if repo.job_settings(job).get("demo"):
        names |= {n for n in repo.candidate_names() if repo.settings(n).get("pool")}
    return sorted(names)


def count(repo: Repository, job: str) -> ListingCounts:
    """Count how far a job's candidates got.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.

    Returns
    -------
    ListingCounts
        Connected, revealed, asked to apply and applied.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    progress = repo.progresses(job=job)
    return ListingCounts(
        connected=len(connected(repo, job)),
        revealed=sum(p.revealed_at is not None for p in progress),
        requested=sum(p.requested_at is not None for p in progress),
        applied=sum(p.answer == "applied" for p in progress),
    )


def connected_profiles(repo: Repository, job: str) -> set[UUID]:
    """Find every profile id of the candidates connected to a job.

    Matches keep the profile id they scored, which changes when a candidate's
    material is extracted again, so all of each candidate's ids are included.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.

    Returns
    -------
    set of UUID
        Current and earlier profile ids.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    return {pid for name in connected(repo, job) for pid in repo.profile_ids(name)}


def revealed(repo: Repository, candidate: str, job: str) -> bool:
    """Tell whether the employer has revealed a candidate on a job.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.

    Returns
    -------
    bool
        True once the employer revealed them (see `unapply.jobs.hiring.reveal`).
        The early reveal intents, kept as history, revealed no one and don't
        count.

    Raises
    ------
    NotFound
        If there is no such candidate or job.
    """
    progress = repo.progress(candidate, job)
    return progress is not None and progress.revealed_at is not None


def connect(repo: Repository, candidate: str, job: str) -> Consent:
    """Connect a candidate's profile to a job: their consent to be matched.

    Connecting again keeps the first time and what the candidate shares.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job; it must be on the board.

    Returns
    -------
    Consent
        The consent, with when it was given.

    Raises
    ------
    NotFound
        If there is no such candidate or job.
    ConnectError
        If the candidate's profile isn't approved, or the job isn't on the board.
    """
    profile = repo.profile(candidate)
    if profile is None or profile.approved_by_candidate_at is None:
        raise ConnectError("approve your profile first; only approved profiles connect")
    if find_listing(repo, job) is None:
        repo.job_settings(job)  # NotFound if there is no such job.
        raise ConnectError(f"job {job!r} isn't on the board yet")
    existing = repo.consent(candidate, job)
    return existing or repo.grant_consent(candidate, job)


def withdraw(repo: Repository, candidate: str, job: str) -> None:
    """Withdraw a candidate's connection to a job.

    The job's next ranking leaves them out; earlier audit entries stay as they
    are.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.

    Raises
    ------
    NotFound
        If there is no such candidate or job.
    ConnectError
        If they aren't connected, or the employer has revealed them: their
        identity is shared, so the connection can't be undone.
    """
    if repo.consent(candidate, job) is None:
        raise ConnectError(f"you aren't connected to {job!r}")
    if revealed(repo, candidate, job):
        raise ConnectError(
            "the employer has revealed you for this job, so the connection can't "
            "be withdrawn"
        )
    repo.withdraw_consent(candidate, job)
