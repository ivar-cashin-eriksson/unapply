"""What the API's routes share: the database, the uploads folder and the models.

Paid model calls are refused unless the request allows them (`?allow_api=true`), as
`--allow-api` does for the command line, or the `UNAPPLY_ALLOW_API_CALLS` switch is
on. Demo candidates and jobs replay recorded answers, which are free.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status

from unapply.app import demo
from unapply.db.repository import Repository
from unapply.llm import (
    API_SWITCH,
    DEFAULT_MODEL,
    QUESTION_MODEL,
    AnthropicLLM,
    APICallsDisabled,
    StructuredLLM,
    api_calls_allowed,
)
from unapply.schemas import Profile

# Makes the client for a purpose ("extract", "estimate", "questions" or "rubric"),
# allowed to call or not. Tests pass a fake.
LLMFactory = Callable[[str, bool], StructuredLLM]


def claude(purpose: str, allow: bool) -> StructuredLLM:
    """Make the Claude client for a purpose, as the app and command line do.

    Parameters
    ----------
    purpose : str
        "extract", "estimate", "questions" or "rubric".
    allow : bool
        Whether the client may make paid calls.

    Returns
    -------
    StructuredLLM
        Sonnet 5.5 at medium effort to word questions, Opus 5.5 at high effort for
        everything else.
    """
    if purpose == "questions":
        return AnthropicLLM(QUESTION_MODEL, "medium", allow=allow)
    return AnthropicLLM(DEFAULT_MODEL, "high", allow=allow)


@dataclass(frozen=True)
class Context:
    """Everything a route needs besides its input.

    Parameters
    ----------
    repo : Repository
        The database.
    uploads : Path
        Folder of uploaded material, one subfolder per candidate.
    llm_factory : LLMFactory
        Makes the model client for non-demo calls.
    """

    repo: Repository
    uploads: Path
    llm_factory: LLMFactory

    def material(self, name: str) -> Path:
        """Return a candidate's material folder, which may not exist yet.

        Parameters
        ----------
        name : str
            The candidate. Names are checked when created, so they are safe as
            folder names.

        Returns
        -------
        Path
            The folder.
        """
        return self.uploads / name

    def model(
        self,
        settings: dict[str, Any],
        purpose: str,
        allow: bool,
        profile: Profile | None = None,
    ) -> StructuredLLM:
        """Pick the model for a call: a replay for demos, else Claude if allowed.

        Parameters
        ----------
        settings : dict
            The candidate's or job's settings; `demo` marks a demo.
        purpose : str
            "extract", "estimate", "questions" or "rubric".
        allow : bool
            Whether the request allows paid calls.
        profile : Profile or None, optional
            For "estimate" in the candidate demo: picks the recording after the
            interview.

        Returns
        -------
        StructuredLLM
            The model to call.

        Raises
        ------
        APICallsDisabled
            If the call would be paid and isn't allowed. Raised before anything
            is done, so a refused request changes nothing.
        HTTPException
            409 for a candidate from the synthetic pool, whose profile is fixed.
        """
        if settings.get("pool"):
            # Pool candidates have recordings only for their finished journey.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This candidate is from the synthetic pool: their profile is fixed.",
            )
        if settings.get("demo"):
            return demo.demo_llm(purpose, profile)
        if not may_call(settings, allow):
            raise APICallsDisabled(
                "this would make a paid API call, which is off. Add ?allow_api=true "
                f"to the request to allow it, or set {API_SWITCH}=1."
            )
        return self.llm_factory(purpose, True)


def may_call(settings: dict[str, Any], allow: bool) -> bool:
    """Tell whether a model call may be made for a candidate or job.

    Parameters
    ----------
    settings : dict
        The candidate's or job's settings; `demo` marks a demo.
    allow : bool
        Whether the request allows paid calls.

    Returns
    -------
    bool
        True for demos (they replay), when the request allows paid calls, or when
        the `UNAPPLY_ALLOW_API_CALLS` switch is on.
    """
    return bool(settings.get("demo")) or allow or api_calls_allowed()


def context(request: Request) -> Context:
    """Return the app's `Context`, for `Depends`.

    Parameters
    ----------
    request : Request
        The request.

    Returns
    -------
    Context
        Set by `unapply.api.app.create_app`.
    """
    return request.app.state.context


Ctx = Annotated[Context, Depends(context)]
AllowAPI = Annotated[
    bool,
    Query(
        description=(
            "Allow this request to make paid model calls. Off by default; demos "
            "never need it."
        )
    ),
]
