"""Message routes: a thread per revealed candidate and job, in both apps.

Once an employer reveals a candidate, the two can write to each other. Before the
reveal there is no thread: reading one (or marking it read) gives 404, as for
anything that doesn't exist, and writing one is refused (409). An empty or too long
message is refused with 422. The employer's routes are under
`/jobs/<job>/candidates/<profile_id>`, so an employer only reaches the candidates
connected to their own job; the candidate's are under `/candidates/<name>/messages`.
Reading a thread doesn't mark it read: the app does that with `POST .../read` once
it shows the messages. No email or notification is sent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from unapply.api.deps import Context, Ctx
from unapply.api.models import CandidateThread, MessageForm, Thread
from unapply.jobs.board import find_listing
from unapply.jobs.hiring import NotOnJob, candidate_on_job
from unapply.jobs.messages import (
    BadMessage,
    Message,
    MessageError,
    Sender,
    mark_read,
    send,
    thread,
    unread,
)

router = APIRouter(tags=["messages"])


@router.get("/jobs/{job}/candidates/{profile_id}/messages")
def employer_thread(job: str, profile_id: UUID, ctx: Ctx) -> Thread:
    """Read the thread with a revealed candidate. 404 before the reveal."""
    candidate = _on_job(ctx, job, profile_id)
    return _thread(lambda: thread(ctx.repo, candidate, job), "employer")


@router.post(
    "/jobs/{job}/candidates/{profile_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
def employer_send(job: str, profile_id: UUID, body: MessageForm, ctx: Ctx) -> Message:
    """Write to a revealed candidate. Refused (409) before the reveal."""
    candidate = _on_job(ctx, job, profile_id)
    return _send(ctx, candidate, job, "employer", body.text)


@router.post("/jobs/{job}/candidates/{profile_id}/messages/read")
def employer_read(job: str, profile_id: UUID, ctx: Ctx) -> Thread:
    """Mark the candidate's messages as read by the employer."""
    candidate = _on_job(ctx, job, profile_id)
    return _thread(lambda: mark_read(ctx.repo, candidate, job, "employer"), "employer")


@router.get("/candidates/{name}/messages", tags=["candidates"])
def candidate_threads(name: str, ctx: Ctx) -> list[CandidateThread]:
    """List every thread the candidate has, with all their messages, newest first.

    One per job whose employer revealed them, even before anyone wrote. This is
    also how a candidate exports their messages.
    """
    ctx.repo.settings(name)  # 404 if there is no such candidate.
    found = []
    for progress in ctx.repo.progresses(candidate=name):
        if progress.revealed_at is None:
            continue
        messages = ctx.repo.messages(name, progress.job)
        listing = find_listing(ctx.repo, progress.job)
        found.append(
            CandidateThread(
                job=progress.job,
                company=listing.company if listing else None,
                title=listing.title if listing else None,
                revealed_at=progress.revealed_at,
                messages=messages,
                unread=unread(messages, "candidate"),
            )
        )
    return sorted(found, key=_latest, reverse=True)


@router.get("/candidates/{name}/messages/{job}", tags=["candidates"])
def candidate_thread(name: str, job: str, ctx: Ctx) -> Thread:
    """Read the thread with a job's employer. 404 before they reveal you."""
    return _thread(lambda: thread(ctx.repo, name, job), "candidate")


@router.post(
    "/candidates/{name}/messages/{job}",
    status_code=status.HTTP_201_CREATED,
    tags=["candidates"],
)
def candidate_send(name: str, job: str, body: MessageForm, ctx: Ctx) -> Message:
    """Write to a job's employer. Refused (409) before they reveal you."""
    return _send(ctx, name, job, "candidate", body.text)


@router.post("/candidates/{name}/messages/{job}/read", tags=["candidates"])
def candidate_read(name: str, job: str, ctx: Ctx) -> Thread:
    """Mark the employer's messages as read by the candidate."""
    return _thread(lambda: mark_read(ctx.repo, name, job, "candidate"), "candidate")


def _on_job(ctx: Context, job: str, profile_id: UUID) -> str:
    try:
        return candidate_on_job(ctx.repo, job, profile_id)
    except NotOnJob as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such candidate connected to this job."
        ) from e


def _thread(load: Callable[[], list[Message]], reader: Sender) -> Thread:
    """Call `load` for a thread, turning a missing one into a 404."""
    try:
        messages = load()
    except MessageError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    return Thread(messages=messages, unread=unread(messages, reader))


def _send(ctx: Context, candidate: str, job: str, sender: Sender, text: str) -> Message:
    try:
        return send(ctx.repo, candidate, job, sender, text)
    except BadMessage as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    except MessageError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


def _latest(t: CandidateThread) -> datetime:
    """Sort key: the last message's time, or the reveal for an empty thread."""
    return t.messages[-1].sent_at if t.messages else t.revealed_at
