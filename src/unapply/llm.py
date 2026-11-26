"""The single place where unapply calls a language model.

Everything else depends on the `StructuredLLM` protocol, so tests can pass a fake and
models can be swapped without touching callers.
"""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-5-5"


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
        Output cap per request, by default 16000.
    """

    def __init__(
        self, model: str = DEFAULT_MODEL, effort: str = "high", max_tokens: int = 16000
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
        response = self._client.beta.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_type,
            output_config={"effort": self.effort},
            # On a safety refusal the API retries on a fallback model it picks.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        log.info(
            "model=%s request_id=%s stop_reason=%s input_tokens=%s output_tokens=%s",
            response.model,
            response._request_id,
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        if response.stop_reason == "refusal":
            raise LLMError(f"model refused (request {response._request_id})")
        if response.stop_reason == "max_tokens":
            raise LLMError(
                f"output hit max_tokens={self.max_tokens} "
                f"(request {response._request_id})"
            )
        if response.parsed_output is None:
            raise LLMError(f"no parsable output (request {response._request_id})")
        return response.parsed_output
