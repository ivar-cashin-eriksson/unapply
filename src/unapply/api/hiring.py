"""Hiring routes: reveal a candidate, request an application, apply or decline.

The employer's actions on a shortlisted candidate go in one order: reveal (see who
they are), then request an application, which the candidate answers by applying or
declining. Requesting is refused until the candidate is revealed. Connecting to a
job is the candidate's consent to be revealed, so there is no accept step; no
payment is taken, but where it would be, a charge intent is recorded, and each
reveal goes in the audit log.

Employer routes are under `/jobs/<job>`, the candidate's under `/candidates/<name>`.
A candidate's contact details, given by the candidate, reach an employer only once
that employer reveals them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from unapply.api.deps import Context, Ctx, download
from unapply.api.models import Connection, ContactForm, EmployerProgress
from unapply.app import demo
from unapply.evaluation.pool import DEFAULT_POOL
from unapply.jobs.board import connected, find_listing
from unapply.jobs.hiring import (
    APPLICATION_SUFFIXES,
    Answer,
    Contact,
    HiringError,
    NotOnJob,
    Progress,
    Stage,
    answer,
    candidate_on_job,
    contact_from_cv,
    request_application,
    reveal,
)

MAX_APPLICATION_BYTES = 10 * 1024 * 1024
MAX_APPLICATION_FILES = 5

router = APIRouter(tags=["hiring"])


@router.post("/jobs/{job}/candidates/{profile_id}/reveal")
def reveal_candidate(
    job: str, profile_id: UUID, ctx: Ctx, response: Response
) -> EmployerProgress:
    """Reveal a connected candidate: their name, contact details and quotes.

    Anyone connected to the job can be revealed: connecting was their consent. No
    payment is taken; a charge intent is recorded where it would be, and the reveal
    goes in the audit log. Limited by the job's reveal quota (409 when used up).
    Revealing again changes nothing (200 instead of 201).
    """
    try:
        progress, new = reveal(ctx.repo, job, profile_id)
    except NotOnJob as e:
        raise _not_on_job() from e
    except HiringError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    response.status_code = status.HTTP_201_CREATED if new else status.HTTP_200_OK
    return employer_progress(progress, profile_id)


@router.post("/jobs/{job}/candidates/{profile_id}/request-application")
def request_candidate_application(
    job: str, profile_id: UUID, ctx: Ctx, response: Response
) -> EmployerProgress:
    """Ask a revealed candidate to apply. Refused (409) before they are revealed.

    The candidate sees the request in their app and applies or declines. Asking
    again changes nothing (200 instead of 201).
    """
    try:
        progress, new = request_application(ctx.repo, job, profile_id)
    except NotOnJob as e:
        raise _not_on_job() from e
    except HiringError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    response.status_code = status.HTTP_201_CREATED if new else status.HTTP_200_OK
    return employer_progress(progress, profile_id)


@router.get("/jobs/{job}/candidates/{profile_id}/files/{file_id}")
def application_file(job: str, profile_id: UUID, file_id: int, ctx: Ctx) -> Response:
    """Download a file a candidate sent with their application.

    Only once they applied; 404 otherwise, as for a file that isn't theirs.
    """
    try:
        candidate = candidate_on_job(ctx.repo, job, profile_id)
    except NotOnJob as e:
        raise _not_on_job() from e
    progress = ctx.repo.progress(candidate, job)
    found = ctx.repo.application_file(candidate, job, file_id)
    if progress is None or progress.answer != "applied" or found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such application file.")
    return download(*found)


@router.get("/candidates/{name}/contact", tags=["candidates"])
def get_contact(name: str, ctx: Ctx) -> Contact:
    """Read the name and contact details an employer sees once they reveal you."""
    return contact(ctx, name)


@router.put("/candidates/{name}/contact", tags=["candidates"])
def save_contact(name: str, body: ContactForm, ctx: Ctx) -> Contact:
    """Set the name and contact details an employer sees once they reveal you.

    Refused (409) for demo candidates, whose details come from their CV.
    """
    settings = ctx.repo.settings(name)
    if settings.get("demo"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A demo candidate's details come from their CV."
        )
    given = Contact(
        name=body.name.strip(),
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
    )
    ctx.repo.save_settings(name, {**settings, "contact": given.model_dump()})
    return contact(ctx, name)


@router.post("/candidates/{name}/applications/{job}", tags=["candidates"])
def apply(
    name: str,
    job: str,
    ctx: Ctx,
    letter: Annotated[str, Form(description="A cover letter or other text.")] = "",
    files: Annotated[
        list[UploadFile] | None, File(description="A CV, a cover letter, ...")
    ] = None,
) -> Connection:
    """Apply for a job whose employer asked you to: a letter, files, or both.

    Refused (409) if the employer hasn't asked, or you already answered. Files are
    PDF, Markdown, text or word processor documents, up to 10 MB and 5 files.
    """
    checked = _checked(files or [])
    _answer(ctx, name, job, "applied", letter, checked)
    return connection(ctx, name, job)


@router.post("/candidates/{name}/applications/{job}/decline", tags=["candidates"])
def decline(name: str, job: str, ctx: Ctx) -> Connection:
    """Decline the employer's request to apply. Refused (409) once answered."""
    _answer(ctx, name, job, "declined")
    return connection(ctx, name, job)


@router.get(
    "/candidates/{name}/applications/{job}/files/{file_id}", tags=["candidates"]
)
def own_application_file(name: str, job: str, file_id: int, ctx: Ctx) -> Response:
    """Download a file you sent with your application."""
    found = ctx.repo.application_file(name, job, file_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such application file.")
    return download(*found)


def employer_progress(progress: Progress | None, profile_id: UUID) -> EmployerProgress:
    """Describe a candidate's progress as the employer sees it: no names.

    Parameters
    ----------
    progress : Progress or None
        The candidate's progress on the job, or None before a reveal.
    profile_id : UUID
        The candidate, as the shortlist shows them.

    Returns
    -------
    EmployerProgress
        The stage and its times, and the application once sent.
    """
    if progress is None:
        return EmployerProgress(profile_id=profile_id)
    applied = progress.answer == "applied"
    return EmployerProgress(
        profile_id=profile_id,
        stage=progress.stage,
        revealed_at=progress.revealed_at,
        requested_at=progress.requested_at,
        answered_at=progress.answered_at,
        letter=progress.letter if applied else "",
        files=progress.files if applied else [],
    )


def contact(ctx: Context, name: str) -> Contact:
    """Find a candidate's name and contact details.

    Parameters
    ----------
    ctx : Context
        The app's context.
    name : str
        The candidate.

    Returns
    -------
    Contact
        What the candidate gave; for demo candidates, what their CV says; else
        their name in the database alone.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    settings = ctx.repo.settings(name)
    if settings.get("contact"):
        return Contact.model_validate(settings["contact"])
    cv = None
    if settings.get("pool"):
        cv = DEFAULT_POOL / settings["pool"] / "material" / "cv.md"
    elif settings.get("demo"):
        cv = demo.FIXTURE / "material" / "cv.md"
    if cv is not None and cv.is_file():
        return contact_from_cv(cv.read_text(encoding="utf-8"), name)
    return Contact(name=name)


def connection(ctx: Context, name: str, job: str) -> Connection:
    """Describe a candidate's connection to a job, with how far they got.

    Parameters
    ----------
    ctx : Context
        The app's context.
    name : str
        The candidate.
    job : str
        The job.

    Returns
    -------
    Connection
        The connection; for a pool candidate of a demo job, who is connected
        without having connected, the time the job was posted.

    Raises
    ------
    NotFound
        If there is no such candidate or job.
    HTTPException
        404 if the candidate isn't connected to the job.
    """
    consent = ctx.repo.consent(name, job)
    if consent is None and name not in connected(ctx.repo, job):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Not connected to {job!r}.")
    progress = ctx.repo.progress(name, job)
    listing = find_listing(ctx.repo, job)
    connected_at = (
        consent.granted_at
        if consent
        else (listing.posted_at if listing else datetime.now())
    )
    return Connection(
        job=job,
        connected_at=connected_at,
        listing=listing,
        stage=progress.stage if progress else Stage.CONNECTED,
        progress=progress,
    )


def _answer(
    ctx: Context,
    name: str,
    job: str,
    choice: Answer,
    letter: str = "",
    files: list[tuple[str, bytes]] | None = None,
) -> None:
    try:
        answer(ctx.repo, name, job, choice, letter, files or [])
    except HiringError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


def _checked(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Check uploaded application files; nothing is stored if one is refused."""
    files = [f for f in files if f.filename]
    if len(files) > MAX_APPLICATION_FILES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"at most {MAX_APPLICATION_FILES} files",
        )
    checked = []
    for f in files:
        filename = Path(f.filename or "").name
        if not filename or filename.startswith("."):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no file name")
        if Path(filename).suffix.lower() not in APPLICATION_SUFFIXES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{filename}: use one of {', '.join(sorted(APPLICATION_SUFFIXES))}",
            )
        content = f.file.read(MAX_APPLICATION_BYTES + 1)
        if len(content) > MAX_APPLICATION_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{filename} is over {MAX_APPLICATION_BYTES // 1024 // 1024} MB",
            )
        checked.append((filename, content))
    return checked


def _not_on_job() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, "No such candidate connected to this job."
    )
