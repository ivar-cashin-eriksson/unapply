"""Job board routes: browse and read listings, and connect a profile to a job.

Candidate routes. A listing is the ad, its vacancies and what it can be filtered by,
never the rubric. A candidate's fit for each job is a coarse band from their own
levels and the hard filters they miss, and after connecting their place in the
ranking. Connecting is the candidate's consent for that job: it lets the
job match and rank their profile anonymously, and the employer reveal it later. It
can be withdrawn until the employer reveals the candidate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from unapply.api.candidates import demos
from unapply.api.deps import Context, Ctx
from unapply.api.models import BoardDemo, Connection
from unapply.app import demo
from unapply.evaluation.pool import load_pool, store_board
from unapply.jobs.board import (
    Board,
    ConnectError,
    Listing,
    Seniority,
    connect,
    find_listing,
    listings,
    search,
    withdraw,
)
from unapply.jobs.fit import Fit, fit, fits
from unapply.schemas import WorkMode

router = APIRouter(tags=["job board"])


@router.get("/board")
def board(
    ctx: Ctx,
    q: Annotated[
        str, Query(description="Words to find in the title, company or ad.")
    ] = "",
    location: Annotated[
        str | None, Query(description="Jobs in this place, and remote jobs.")
    ] = None,
    work_mode: Annotated[
        WorkMode | None, Query(description="Jobs offering this work mode.")
    ] = None,
    seniority: Annotated[
        Seniority | None, Query(description="Jobs at this seniority.")
    ] = None,
) -> Board:
    """Browse and search the job board: jobs whose rubric is approved, newest first.

    Each listing has the ad, vacancies, place, work modes and seniority, never the
    rubric.
    """
    return search(listings(ctx.repo), q, location, work_mode, seniority)


@router.get("/board/{job}")
def read_listing(job: str, ctx: Ctx) -> Listing:
    """Read one listing in full: the ad and the vacancies, not the rubric."""
    return _listing(ctx, job)


@router.get("/candidates/{name}/connections", tags=["candidates"])
def list_connections(name: str, ctx: Ctx) -> list[Connection]:
    """List the jobs a candidate connected their profile to, newest first."""
    ctx.repo.settings(name)  # 404 if there is no such candidate.
    found = []
    for job in ctx.repo.job_names():
        consent = ctx.repo.consent(name, job)
        if consent is not None:
            found.append(_connection(ctx, consent.job, consent.granted_at))
    return sorted(found, key=lambda c: c.connected_at, reverse=True)


@router.get("/candidates/{name}/fit", tags=["candidates"])
def list_fits(name: str, ctx: Ctx) -> list[Fit]:
    """How well the candidate fits each job on the board, in board order.

    A coarse band from their own levels only, the hard filters they don't meet as
    the ad names them, and once connected their place in the job's latest
    ranking. Never a score, criterion, weight or minimum level, and nothing from
    the assessment. Free, and nothing is stored.
    """
    return fits(ctx.repo, name)


@router.get("/candidates/{name}/fit/{job}", tags=["candidates"])
def read_fit(name: str, job: str, ctx: Ctx) -> Fit:
    """How well the candidate fits one job on the board (see `GET .../fit`)."""
    found = fit(ctx.repo, name, job)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job!r} on the board.")
    return found


@router.put("/candidates/{name}/connections/{job}", tags=["candidates"])
def connect_profile(name: str, job: str, ctx: Ctx) -> Connection:
    """Connect the candidate's approved profile to a job on the board.

    This is the candidate's consent for that job, recorded with its time: the job
    may match and rank the profile anonymously, and the employer may reveal it.
    Connecting again changes nothing. Refused (409) if the profile isn't approved.
    """
    try:
        consent = connect(ctx.repo, name, job)
    except ConnectError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return _connection(ctx, job, consent.granted_at)


@router.delete(
    "/candidates/{name}/connections/{job}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["candidates"],
)
def withdraw_profile(name: str, job: str, ctx: Ctx) -> None:
    """Withdraw the connection: the job's next ranking leaves the candidate out.

    Earlier audit entries stay. Refused (409) once the employer has revealed the
    candidate, and if they aren't connected.
    """
    try:
        withdraw(ctx.repo, name, job)
    except ConnectError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@demos.post("/board", status_code=status.HTTP_201_CREATED, tags=["demos"])
def create_board_demo(ctx: Ctx) -> BoardDemo:
    """Put the demo jobs on the board, with the synthetic pool connected to each.

    Eleven invented jobs from `tests/fixtures/jobs` (Fjord Grocery and ten more),
    each with its rubric approved, so they can be browsed, connected to and matched
    with the baseline scorer for free. Calling again keeps the jobs already there.
    """
    if not demo.available():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo isn't installed.")
    try:
        names = store_board(ctx.repo, load_pool())
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return BoardDemo(jobs=names)


def _listing(ctx: Context, job: str) -> Listing:
    found = find_listing(ctx.repo, job)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job!r} on the board.")
    return found


def _connection(ctx: Context, job: str, connected_at: datetime) -> Connection:
    return Connection(
        job=job, connected_at=connected_at, listing=find_listing(ctx.repo, job)
    )
