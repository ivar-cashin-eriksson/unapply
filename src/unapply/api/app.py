"""The FastAPI app: routes over the database, and how errors become responses."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from unapply.api import board, candidates, hiring, internal, jobs, matching, messages
from unapply.api.deps import Context, LLMFactory, claude
from unapply.db.engine import init_db
from unapply.db.repository import NotFound, Repository, RubricLocked
from unapply.interview.sheet import InterviewError
from unapply.jobs.sheet import RubricError
from unapply.llm import APICallsDisabled, LLMError
from unapply.review import ReviewError
from unapply.workspace import data_dir

DESCRIPTION = """\
Candidates upload material once, review the profile extracted from it and answer a
few questions, then browse the job board and connect their profile to the jobs they
want. Employers turn a job ad into a rubric, edit it, and match and rank the
candidates connected to it, anonymised. From the shortlist, an employer reveals a
candidate (no payment is taken yet) and then asks them to apply; the candidate
applies with a letter or files, or declines.

**Paid model calls are refused** unless the request adds `?allow_api=true` (or the
server runs with `UNAPPLY_ALLOW_API_CALLS=1`). Demo candidates and jobs, created
under `/demos`, replay recorded answers and cost nothing.

Candidate routes never return the assessment (estimated levels, claim support).
"""

# Errors from the package, as status codes. Their messages say what to fix.
ERRORS: list[tuple[type[Exception], int]] = [
    (NotFound, status.HTTP_404_NOT_FOUND),
    (APICallsDisabled, status.HTTP_403_FORBIDDEN),
    (RubricLocked, status.HTTP_409_CONFLICT),
    (ReviewError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (RubricError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (InterviewError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    # APICallsDisabled is a kind of LLMError; the more specific handler wins.
    (LLMError, status.HTTP_502_BAD_GATEWAY),
]


def create_app(
    repo: Repository | None = None,
    uploads: Path | None = None,
    llm_factory: LLMFactory | None = None,
    internal_routes: bool = False,
) -> FastAPI:
    """Create the API.

    Parameters
    ----------
    repo : Repository or None, optional
        The database. By default the one at `$UNAPPLY_DATABASE_URL` (see
        `unapply.db.engine.database_url`), created or migrated first.
    uploads : Path or None, optional
        Folder for uploaded material, one subfolder per candidate. By default
        `uploads/` in the data folder.
    llm_factory : callable or None, optional
        Makes the model client for paid calls, given the purpose and whether calls
        are allowed. By default Claude, as in the app and command line. Only called
        once a call is allowed.
    internal_routes : bool, optional
        Add the internal assessment routes (`/internal/...`), by default False.
        Never on for a server candidates use.

    Returns
    -------
    FastAPI
        The app, with OpenAPI docs at `/docs`.
    """
    if repo is None:
        init_db()
        repo = Repository.from_url()
    app = FastAPI(title="unapply", description=DESCRIPTION, version="0.1.0")
    app.state.context = Context(
        repo=repo,
        uploads=uploads or data_dir() / "uploads",
        llm_factory=llm_factory or claude,
    )
    for router in (
        candidates.router,
        candidates.demos,
        jobs.router,
        matching.router,
        board.router,
        hiring.router,
        messages.router,
    ):
        app.include_router(router)
    if internal_routes:
        app.include_router(internal.router)
    for error, code in ERRORS:
        app.add_exception_handler(error, _handler(code))

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Tell that the API is up."""
        return {"status": "ok"}

    return app


def _handler(code: int):  # noqa: ANN202 (a Starlette exception handler)
    """Answer an error from the package with `code` and its message."""

    async def handle(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    return handle
