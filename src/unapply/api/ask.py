"""Ask routes: an employer asks a model about a candidate they revealed.

Employer routes, under `/jobs/<job>/candidates/<profile_id>`, so an employer only
reaches the candidates connected to their own job. Before the reveal, asking is
refused (409), checked before any model is picked, and the list of demo questions
isn't there (404), as for messages. A model answers from the
candidate's own material only, citing their quotes (see `unapply.jobs.ask`).

Each question is one paid call, refused (403) unless the request allows it
(`?allow_api=true`) or the `UNAPPLY_ALLOW_API_CALLS` switch is on. Candidates from
the synthetic pool have hand-written stand-in answers to a few demo questions,
listed by `GET .../ask`, which replay for free. Nothing is stored: the page keeps
the conversation and sends it with each question.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from unapply.api.deps import AllowAPI, Context, Ctx
from unapply.api.models import AskOptions, QuestionForm
from unapply.jobs.ask import (
    BadQuestion,
    CandidateAnswer,
    NotRevealed,
    ask_candidate,
    check_question,
    demo_questions,
    demo_recording,
    revealed_candidate,
)
from unapply.jobs.hiring import NotOnJob
from unapply.llm import (
    API_SWITCH,
    APICallsDisabled,
    ReplayLLM,
    StructuredLLM,
    api_calls_allowed,
)

router = APIRouter(tags=["ask"])


@router.get("/jobs/{job}/candidates/{profile_id}/ask")
def ask_options(job: str, profile_id: UUID, ctx: Ctx) -> AskOptions:
    """List the free demo questions for a revealed candidate. 404 before the reveal."""
    candidate = _revealed(ctx, job, profile_id, status.HTTP_404_NOT_FOUND)
    pool = ctx.repo.settings(candidate).get("pool")
    return AskOptions(suggested=list(demo_questions(pool)))


@router.post("/jobs/{job}/candidates/{profile_id}/ask")
def ask(
    job: str,
    profile_id: UUID,
    body: QuestionForm,
    ctx: Ctx,
    allow_api: AllowAPI = False,
) -> CandidateAnswer:
    """Ask about a revealed candidate; a model answers from their material only.

    The answer cites the candidate's quotes, and says when their material doesn't
    answer the question. Refused before the reveal (409), for an empty or too long
    question (422), and, unless allowed, when it would be a paid call (403). Nothing
    is stored.
    """
    candidate = _revealed(ctx, job, profile_id)
    try:
        question = check_question(body.question, body.history)
    except BadQuestion as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    settings = ctx.repo.settings(candidate)
    llm = _model(ctx, settings.get("pool"), question, allow_api)
    names = [settings["github"]] if settings.get("github") else []
    return ask_candidate(
        ctx.repo.profile(candidate), question, llm, body.history, names
    )


def _revealed(
    ctx: Context, job: str, profile_id: UUID, before: int = status.HTTP_409_CONFLICT
) -> str:
    """Find the revealed candidate; `before` is the status code before the reveal."""
    try:
        return revealed_candidate(ctx.repo, job, profile_id)
    except NotOnJob as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such candidate connected to this job."
        ) from e
    except NotRevealed as e:
        raise HTTPException(before, str(e)) from e


def _model(ctx: Context, pool: str | None, question: str, allow: bool) -> StructuredLLM:
    """Replay a demo question's stand-in, else Claude if paid calls are allowed."""
    recording = demo_recording(pool, question)
    if recording is not None:
        return ReplayLLM(recording)
    if not (allow or api_calls_allowed()):
        hint = (
            " Pick one of the suggested demo questions to ask for free."
            if (demo_questions(pool))
            else ""
        )
        raise APICallsDisabled(
            "answering this question would make a paid API call, which is off. Add "
            f"?allow_api=true to the request to allow it, or set {API_SWITCH}=1." + hint
        )
    return ctx.llm_factory("ask", True)
