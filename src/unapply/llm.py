"""The single place where unapply calls a language model.

Everything else depends on the `StructuredLLM` protocol, so tests can pass a fake and
models can be swapped without touching callers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"
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


class AnthropicLLM:
    """`StructuredLLM` backed by the Claude API.

    Credentials are read from the environment (`ANTHROPIC_API_KEY`, or a profile
    from `ant auth login`).

    Parameters
    ----------
    model : str, optional
        Claude model id, by default "claude-opus-5-5".
    effort : str, optional
        Thinking effort: "low", "medium", "high", "xhigh" or "max", by default
        "high".
    max_tokens : int, optional
        Output cap per request, thinking included, by default 64000.
    """

    def __init__(
        self, model: str = DEFAULT_MODEL, effort: str = "high", max_tokens: int = 64000
    ) -> None:
        # Imported here so the package and its tests work without the SDK configured.
        import anthropic

        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

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
        # Streamed, because large outputs time out as plain requests.
        with self._client.beta.messages.stream(
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
