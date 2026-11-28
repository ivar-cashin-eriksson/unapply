"""How well a candidate fits a job on the board, as the candidate sees it.

Before connecting, a candidate sees a coarse **band** ("Strong fit", "Good fit",
"Partial fit", "Low fit") and any hard filter they don't meet, named as the ad
states it ("Work permit: EU required"). After connecting, they also see their
**place** among the job's connected candidates ("You're #4 of 37"), from the job's
latest ranking in the audit log.

The band comes from the baseline scorer on the candidate's own levels only, on the
profile as the candidate sees it (`candidate_view`: no estimates, no claim
support), so it says nothing about the assessment. Only the band is given, never
the score, a criterion, a weight or a minimum level, so the rubric stays hidden.
It is free and deterministic, and nothing is stored: a fit is worked out each time
it is asked for.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

from unapply.app.forms import candidate_view
from unapply.jobs.board import Listing, connected, find_listing, listings
from unapply.matching.audit import AuditKind
from unapply.matching.baseline import own_total
from unapply.matching.filters import Outcome, check_hard_filters
from unapply.schemas import HardFilters, Profile, Rubric

if TYPE_CHECKING:
    from unapply.db.repository import Repository


class FitBand(StrEnum):
    """How well a candidate fits a job on their own levels, coarsely."""

    STRONG = "strong"
    GOOD = "good"
    PARTIAL = "partial"
    LOW = "low"


# The lowest own-level total for each band, best first; anything lower is LOW.
BANDS = ((FitBand.STRONG, 0.8), (FitBand.GOOD, 0.6), (FitBand.PARTIAL, 0.3))


class MissedFilter(BaseModel):
    """A hard filter the candidate doesn't meet, named as the job ad states it.

    Parameters
    ----------
    filter : str
        "location", "work_mode", "work_permit" or "min_years_experience".
    label : str
        What the job asks for, such as "Work permit: EU required".
    """

    filter: str
    label: str


class Place(BaseModel):
    """A candidate's place in a job's latest ranking.

    Parameters
    ----------
    rank : int
        Their rank, from 1; candidates with the same total share a rank.
    of : int
        How many connected candidates were ranked.
    ranked_at : datetime
        When the ranking was made, local time.
    """

    rank: int
    of: int
    ranked_at: datetime


class Fit(BaseModel):
    """How well a candidate fits a job on the board.

    Parameters
    ----------
    job : str
        The job's name.
    band : FitBand or None
        The band on the candidate's own levels; None if they have no profile yet.
    missed : list of MissedFilter
        The hard filters they don't meet. Filters their profile says nothing about
        aren't listed: they don't exclude anyone.
    connected : bool
        Whether the candidate is connected to the job.
    place : Place or None
        Their place in the job's latest ranking, once connected and ranked; None
        before.
    """

    job: str
    band: FitBand | None
    missed: list[MissedFilter]
    connected: bool
    place: Place | None = None


def band(total: float) -> FitBand:
    """Put an own-level total into a band.

    Parameters
    ----------
    total : float
        The baseline's total on own levels, from 0 to 1.

    Returns
    -------
    FitBand
        Strong from 0.8, good from 0.6, partial from 0.3, otherwise low.
    """
    for found, lowest in BANDS:
        if total >= lowest:
            return found
    return FitBand.LOW


def filter_label(name: str, filters: HardFilters) -> str:
    """Name a hard filter as the job ad states it.

    Parameters
    ----------
    name : str
        The filter, as in `FilterCheck.name`.
    filters : HardFilters
        The job's hard filters, copied from its ad.

    Returns
    -------
    str
        Such as "Location: Copenhagen" or "Work permit: EU required".
    """
    if name == "location":
        return f"Location: {', '.join(filters.locations)}"
    if name == "work_mode":
        return f"Work mode: {' or '.join(m.value for m in filters.work_modes)}"
    if name == "work_permit":
        return f"Work permit: {', '.join(filters.required_work_permits)} required"
    if name == "min_years_experience":
        n = filters.min_years_experience
        return f"Experience: at least {n} year{'s' if n != 1 else ''}"
    raise ValueError(f"unknown hard filter {name!r}")


def missed_filters(
    profile: Profile, filters: HardFilters, today: date | None = None
) -> list[MissedFilter]:
    """List the hard filters a profile doesn't meet, as the ad names them.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    filters : HardFilters
        The job's hard filters.
    today : date or None, optional
        The date current roles run to, by default today.

    Returns
    -------
    list of MissedFilter
        The failed filters, in the order they are checked.
    """
    return [
        MissedFilter(filter=c.name, label=filter_label(c.name, filters))
        for c in check_hard_filters(profile, filters, today).checks
        if c.outcome == Outcome.FAIL
    ]


def own_band(profile: Profile, rubric: Rubric) -> FitBand:
    """Band a profile against a rubric on the candidate's own levels only.

    Parameters
    ----------
    profile : Profile
        The candidate's profile; its estimates and claim support are dropped first.
    rubric : Rubric
        The job's rubric.

    Returns
    -------
    FitBand
        The band of the baseline's own-level total.
    """
    return band(own_total(candidate_view(profile), rubric))


def place(repo: Repository, candidate: str, job: str) -> Place | None:
    """Find a candidate's place in a job's latest ranking.

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
    Place or None
        Their place, or None if the job hasn't been ranked or the latest ranking
        doesn't include them (they connected after it).

    Raises
    ------
    NotFound
        If there is no such candidate or job.
    """
    current = repo.job(job)
    if current is None:
        return None
    rankings = repo.audit_log(current.id, AuditKind.RANKING)
    if not rankings:
        return None
    entry = rankings[-1]
    ids = {str(i) for i in repo.profile_ids(candidate)}
    ranked = entry.payload["ranking"]
    for r in ranked:
        if r["match"]["profile_id"] in ids:
            return Place(rank=r["rank"], of=len(ranked), ranked_at=entry.recorded_at)
    return None


def fit(repo: Repository, candidate: str, job: str) -> Fit | None:
    """Work out how well a candidate fits a job on the board. Nothing is stored.

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
    Fit or None
        The fit, or None if the job isn't on the board.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    repo.settings(candidate)  # NotFound if there is no such candidate.
    if find_listing(repo, job) is None:
        return None
    current = repo.job(job)
    assert current is not None  # A listed job has an approved rubric.
    profile = repo.profile(candidate)
    today = repo.job_settings(job).get("today")
    is_connected = candidate in connected(repo, job)
    return Fit(
        job=job,
        band=own_band(profile, current.rubric) if profile is not None else None,
        missed=(
            missed_filters(
                profile,
                current.rubric.hard_filters,
                date.fromisoformat(today) if today else None,
            )
            if profile is not None
            else []
        ),
        connected=is_connected,
        place=place(repo, candidate, job) if is_connected else None,
    )


def fits(repo: Repository, candidate: str) -> list[Fit]:
    """Work out how well a candidate fits every job on the board.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.

    Returns
    -------
    list of Fit
        One per listing, in board order.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    found = [fit(repo, candidate, x.name) for x in listings(repo)]
    return [f for f in found if f is not None]


class FitFilter(StrEnum):
    """What the board's fit filter keeps: one band, or jobs whose requirements fail.

    A band keeps the jobs where the candidate's band is that band, whatever the hard
    filters say, so the filter keeps what each card's fit badge says. `NOT_MET`
    keeps the jobs with at least one hard filter the candidate doesn't meet.
    """

    STRONG = "strong"
    GOOD = "good"
    PARTIAL = "partial"
    LOW = "low"
    NOT_MET = "not_met"


class BoardSort(StrEnum):
    """The order of the board's listings: newest first, or best fit first."""

    NEWEST = "newest"
    FIT = "fit"


# Best band first; a job without a band (no profile yet) sorts after every band.
_BAND_ORDER = {b: i for i, b in enumerate(FitBand)}


def keeps(found: Fit | None, wanted: FitFilter) -> bool:
    """Whether a job's fit passes the board's fit filter.

    Parameters
    ----------
    found : Fit or None
        The candidate's fit for the job; None if it couldn't be worked out, which
        no fit filter keeps.
    wanted : FitFilter
        The filter.

    Returns
    -------
    bool
        True if the job is kept.
    """
    if found is None:
        return False
    if wanted is FitFilter.NOT_MET:
        return bool(found.missed)
    return found.band is not None and found.band.value == wanted.value


def arrange(
    found: list[Listing],
    by_job: dict[str, Fit],
    wanted: FitFilter | None = None,
    order: BoardSort = BoardSort.NEWEST,
) -> list[Listing]:
    """Filter listings by the candidate's fit and sort them by it.

    Parameters
    ----------
    found : list of Listing
        Listings in board order: newest first, then by name.
    by_job : dict of str to Fit
        The candidate's fit for each job, by job name.
    wanted : FitFilter or None, optional
        Keep only the jobs that pass this filter; None keeps every job.
    order : BoardSort, optional
        `NEWEST` keeps board order; `FIT` puts the best band first, ties (and jobs
        without a band, last) in board order, so ties are newest first.

    Returns
    -------
    list of Listing
        The listings kept, in the order asked for.
    """
    kept = [x for x in found if wanted is None or keeps(by_job.get(x.name), wanted)]
    if order is BoardSort.FIT:
        # A stable sort keeps board order (newest first) within each band.
        return sorted(kept, key=lambda x: _rank(by_job.get(x.name)))
    return kept


def _rank(found: Fit | None) -> int:
    """Where a fit's band sorts: 0 for strong, and after every band for none."""
    if found is None or found.band is None:
        return len(_BAND_ORDER)
    return _BAND_ORDER[found.band]
