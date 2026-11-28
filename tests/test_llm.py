"""The model client's error handling, call log and recordings, all with fakes."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from unapply.llm import (
    AnthropicLLM,
    LLMError,
    RecordingLLM,
    ReplayLLM,
    call_log_path,
    logged_spend,
)


class Answer(BaseModel):
    text: str


def _invalid() -> ValidationError:
    try:
        Answer.model_validate({})
    except ValidationError as e:
        return e
    raise AssertionError("expected a validation error")


class FakeStream:
    """Stands in for the SDK's message stream."""

    def __init__(
        self,
        *,
        stop_reason: str = "end_turn",
        parsed: Answer | None = None,
        raises: Exception | None = None,
        output_tokens: int = 50,
        model: str = "claude-opus-5-5",
        snapshot: bool = True,
    ) -> None:
        self.request_id = "req_test"
        self._raises = raises
        self._snapshot = snapshot
        usage = SimpleNamespace(input_tokens=1000, output_tokens=output_tokens)
        self._message = SimpleNamespace(
            model=model, usage=usage, stop_reason=stop_reason, parsed_output=parsed
        )

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def current_message_snapshot(self) -> SimpleNamespace:
        if not self._snapshot:
            raise RuntimeError("nothing arrived")
        return self._message

    def get_final_message(self) -> SimpleNamespace:
        if self._raises is not None:
            raise self._raises
        return self._message


def _llm(stream: FakeStream, max_tokens: int = 64000) -> tuple[AnthropicLLM, dict]:
    """An allowed client whose SDK client is a fake, so nothing is called."""
    sent: dict = {}

    def open_stream(**kwargs: object) -> FakeStream:
        sent.update(kwargs)
        return stream

    llm = AnthropicLLM(max_tokens=max_tokens, allow=True)
    llm._client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(stream=open_stream))
    )
    return llm, sent


def _log() -> list[dict]:
    lines = call_log_path().read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_a_parsed_answer_is_returned_and_the_call_logged():
    llm, sent = _llm(FakeStream(parsed=Answer(text="hi"), output_tokens=500))
    answer = llm.parse(system="sys", prompt="question", output_type=Answer)
    assert answer == Answer(text="hi")
    assert sent["system"] == "sys"
    assert sent["messages"] == [{"role": "user", "content": "question"}]
    assert sent["output_format"] is Answer
    assert sent["output_config"] == {"effort": "high"}
    [entry] = _log()
    assert entry["purpose"] == "Answer"
    assert entry["request_id"] == "req_test"
    assert (entry["input_tokens"], entry["output_tokens"]) == (1000, 500)
    # 1000 input tokens at $4 and 500 output tokens at $20 per million.
    assert entry["cost_usd"] == 0.014
    assert logged_spend() == (1, 0.014)


def test_an_unknown_model_is_priced_as_the_default():
    llm, _ = _llm(FakeStream(parsed=Answer(text="hi"), model="claude-new"))
    llm.parse(system="s", prompt="p", output_type=Answer)
    [entry] = _log()
    assert entry["model"] == "claude-new"
    assert entry["cost_usd"] == 0.005


@pytest.mark.parametrize(
    ("stream", "message"),
    [
        (FakeStream(stop_reason="refusal"), "model refused"),
        (FakeStream(stop_reason="max_tokens"), "hit max_tokens=64000"),
        (FakeStream(parsed=None), "no parsable output"),
    ],
)
def test_unusable_answers_raise_and_are_still_logged(stream, message):
    llm, _ = _llm(stream)
    with pytest.raises(LLMError, match=message) as e:
        llm.parse(system="s", prompt="p", output_type=Answer)
    assert "req_test" in str(e.value)
    assert len(_log()) == 1


def test_truncated_output_is_reported_as_hitting_max_tokens():
    stream = FakeStream(raises=_invalid(), output_tokens=100)
    llm, _ = _llm(stream, max_tokens=100)
    with pytest.raises(LLMError, match="hit max_tokens=100"):
        llm.parse(system="s", prompt="p", output_type=Answer)
    assert len(_log()) == 1


def test_output_of_the_wrong_shape_is_reported_as_such():
    llm, _ = _llm(FakeStream(raises=_invalid(), output_tokens=10))
    with pytest.raises(LLMError, match="didn't match schema"):
        llm.parse(system="s", prompt="p", output_type=Answer)
    assert len(_log()) == 1


def test_nothing_is_logged_when_nothing_arrived():
    stream = FakeStream(raises=ConnectionError("down"), snapshot=False)
    llm, _ = _llm(stream)
    with pytest.raises(ConnectionError):
        llm.parse(system="s", prompt="p", output_type=Answer)
    assert not call_log_path().exists()


class FixedLLM:
    model = "fixed"

    def parse(self, *, system: str, prompt: str, output_type: type) -> Answer:
        return Answer(text="København")


def test_a_recorded_answer_replays(tmp_path):
    path = tmp_path / "recordings" / "answer.json"
    recorder = RecordingLLM(FixedLLM(), path)
    assert recorder.model == "fixed"
    assert recorder.parse(system="s", prompt="p", output_type=Answer).text == (
        "København"
    )
    assert "København" in path.read_text(encoding="utf-8")
    replay = ReplayLLM(path)
    assert replay.model == "replay:fixed"
    assert replay.parse(system="", prompt="", output_type=Answer) == Answer(
        text="København"
    )


def test_a_recording_of_another_shape_is_rejected(tmp_path):
    path = tmp_path / "answer.json"
    path.write_text(json.dumps({"model": "m", "answer": {"other": 1}}), "utf-8")
    with pytest.raises(LLMError, match="doesn't match Answer"):
        ReplayLLM(path).parse(system="", prompt="", output_type=Answer)
