"""The single place where unapply calls a language model.

Everything else depends on the `StructuredLLM` protocol, so tests can pass a fake and
models can be swapped without touching callers.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"
# Environment switch that allows paid API calls; off unless set to "1".
API_SWITCH = "UNAPPLY_ALLOW_API_CALLS"
# US dollars per million input and output tokens, for the call log's estimates.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
# For light tasks such as wording interview questions.
QUESTION_MODEL = "claude-sonnet-5-5"


class LLMError(RuntimeError):
    """The model returned no usable output."""


class StructuredLLM(Protocol):
    """A model that answers a prompt with an instance of a Pydantic model.

    Attributes
    ----------
    model : str
        Model identifier, recorded on everything the model produces for auditing.
    """

    model: str

    def parse(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Answer `prompt` with a validated instance of `output_type`.

        Parameters
        ----------
        system : str
            System prompt.
        prompt : str
            User message.
        output_type : type of BaseModel
            The schema the answer must follow.

        Returns
        -------
        BaseModel
            An instance of `output_type`.

        Raises
        ------
        LLMError
            If the model refuses, runs out of tokens or returns invalid output.
        """
        ...


class APICallsDisabled(LLMError):
    """A paid API call was attempted without being allowed."""


def api_calls_allowed() -> bool:
    """Whether paid API calls are switched on for this process.

    They are only when the environment variable `UNAPPLY_ALLOW_API_CALLS` is "1",
    for example in `.env`. Off by default, so nothing calls the API by accident.

    Returns
    -------
    bool
        True if the switch is on.
    """
    return os.environ.get(API_SWITCH) == "1"


def call_log_path() -> Path:
    """Where real API calls are logged: `api_calls.jsonl` in the data folder.

    Returns
    -------
    Path
        `$UNAPPLY_DATA/api_calls.jsonl`, by default `data/api_calls.jsonl`.
    """
    return Path(os.environ.get("UNAPPLY_DATA", "data")) / "api_calls.jsonl"


def logged_spend() -> tuple[int, float]:
    """Count the calls in the call log and add up their estimated cost.

    Returns
    -------
    int
        Number of logged calls.
    float
        Estimated total cost in US dollars.
    """
    path = call_log_path()
    if not path.exists():
        return 0, 0.0
    entries = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return len(entries), sum(e.get("cost_usd", 0.0) for e in entries)


class AnthropicLLM:
    """`StructuredLLM` backed by the Claude API. Every call costs money.

    Calls are refused unless allowed: by `allow=True`, which callers set only after
    an explicit choice (`--allow-api`, or the app's toggle), or by the
    `UNAPPLY_ALLOW_API_CALLS` switch. Each call is logged to `call_log_path()`.
    Credentials are read from the environment (`ANTHROPIC_API_KEY`).

    Parameters
    ----------
    model : str, optional
        Claude model id, by default "claude-opus-5-5".
    effort : str, optional
        Thinking effort: "low", "medium", "high", "xhigh" or "max", by default
        "high".
    max_tokens : int, optional
        Output cap per request, thinking included, by default 64000.
    allow : bool, optional
        Allow calls for this client even if the switch is off, by default False.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "high",
        max_tokens: int = 64000,
        allow: bool = False,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.allow = allow
        self._client = None

    @property
    def allowed(self) -> bool:
        """Whether this client may make calls."""
        return self.allow or api_calls_allowed()

    def _connect(self) -> Any:  # noqa: ANN401 (the SDK's client)
        if not self.allowed:
            raise APICallsDisabled(
                "paid API calls are off. Allow them for one command with --allow-api, "
                f"with the app's toggle, or set {API_SWITCH}=1 in .env."
            )
        if self._client is None:
            # Imported and created only once allowed, so nothing else can call.
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def parse(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Answer `prompt` with a validated instance of `output_type`.

        Parameters
        ----------
        system : str
            System prompt.
        prompt : str
            User message.
        output_type : type of BaseModel
            The schema the answer must follow.

        Returns
        -------
        BaseModel
            An instance of `output_type`.

        Raises
        ------
        LLMError
            If the model refuses, runs out of tokens or returns invalid output.
        """
        client = self._connect()
        # Streamed, because large outputs time out as plain requests.
        with client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_type,
            output_config={"effort": self.effort},
            # On a safety refusal the API retries on a fallback model it picks.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            request = stream.request_id
            try:
                response = stream.get_final_message()
            except ValidationError as e:
                # The SDK parses the JSON when the text block ends, before the stop
                # reason arrives, so truncated output surfaces here.
                usage = stream.current_message_snapshot.usage
                if usage.output_tokens >= self.max_tokens:
                    raise LLMError(
                        f"output hit max_tokens={self.max_tokens} (request {request})"
                    ) from e
                raise LLMError(f"output didn't match schema (request {request})") from e
            finally:
                # Failed calls are billed too, so log whatever was used.
                self._log_call(stream, request, output_type.__name__)
        log.info(
            "model=%s request_id=%s stop_reason=%s input_tokens=%s output_tokens=%s",
            response.model,
            request,
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        if response.stop_reason == "refusal":
            raise LLMError(f"model refused (request {request})")
        if response.stop_reason == "max_tokens":
            raise LLMError(
                f"output hit max_tokens={self.max_tokens} (request {request})"
            )
        if response.parsed_output is None:
            raise LLMError(f"no parsable output (request {request})")
        return response.parsed_output

    def _log_call(self, stream: Any, request: str | None, purpose: str) -> None:  # noqa: ANN401
        try:
            snapshot = stream.current_message_snapshot
        except Exception:  # noqa: BLE001 (nothing arrived; nothing to log)
            return
        usage = snapshot.usage
        price_in, price_out = PRICES_PER_MTOK.get(
            snapshot.model, PRICES_PER_MTOK[DEFAULT_MODEL]
        )
        cost = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1e6
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "model": snapshot.model,
            "purpose": purpose,
            "request_id": request,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost, 4),
        }
        path = call_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


class RecordingLLM:
    """Pass calls to another model and save its answer to a file.

    The saved answer can be replayed with `ReplayLLM`, so tests and repeated runs
    don't call the API.

    Parameters
    ----------
    inner : StructuredLLM
        The model that answers.
    path : Path
        JSON file to write the answer to. Overwritten on each call.
    """

    def __init__(self, inner: StructuredLLM, path: Path) -> None:
        self.model = inner.model
        self._inner = inner
        self._path = path

    def parse(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Answer with the inner model and save the answer.

        Parameters
        ----------
        system : str
            System prompt.
        prompt : str
            User message.
        output_type : type of BaseModel
            The schema the answer must follow.

        Returns
        -------
        BaseModel
            The inner model's answer.
        """
        answer = self._inner.parse(
            system=system, prompt=prompt, output_type=output_type
        )
        record = {"model": self.model, "answer": answer.model_dump(mode="json")}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return answer


class ReplayLLM:
    """Answer with an answer saved by `RecordingLLM`, without calling any model.

    Parameters
    ----------
    path : Path
        JSON file written by `RecordingLLM`.
    """

    def __init__(self, path: Path) -> None:
        self._record = json.loads(path.read_text(encoding="utf-8"))
        self.model = f"replay:{self._record['model']}"

    def parse(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        """Return the saved answer, validated against `output_type`.

        Parameters
        ----------
        system : str
            System prompt. Ignored.
        prompt : str
            User message. Ignored.
        output_type : type of BaseModel
            The schema the saved answer must follow.

        Returns
        -------
        BaseModel
            The saved answer.

        Raises
        ------
        LLMError
            If the saved answer doesn't match `output_type`.
        """
        try:
            return output_type.model_validate(self._record["answer"])
        except ValidationError as e:
            raise LLMError(
                f"recorded answer doesn't match {output_type.__name__}"
            ) from e
