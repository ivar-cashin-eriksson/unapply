"""Paid API calls are off unless explicitly allowed."""

import json

import anthropic
import pytest
from pydantic import BaseModel

from unapply.cli import main
from unapply.llm import (
    API_SWITCH,
    AnthropicLLM,
    APICallsDisabled,
    api_calls_allowed,
    call_log_path,
    logged_spend,
)


class Answer(BaseModel):
    text: str


@pytest.fixture
def no_client(monkeypatch):
    """Fail loudly if anything tries to create an API client."""

    def refuse(*args, **kwargs):
        raise AssertionError("an API client was created")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


def test_calls_are_off_by_default(no_client):
    assert not api_calls_allowed()
    llm = AnthropicLLM()
    assert not llm.allowed
    with pytest.raises(APICallsDisabled, match="--allow-api"):
        llm.parse(system="s", prompt="p", output_type=Answer)


def test_allow_flag_or_switch_allows(monkeypatch):
    assert AnthropicLLM(allow=True).allowed
    monkeypatch.setenv(API_SWITCH, "1")
    assert AnthropicLLM().allowed
    for value in ["true", "yes", "0", ""]:
        monkeypatch.setenv(API_SWITCH, value)
        assert not AnthropicLLM().allowed


def test_cli_refuses_before_doing_anything(no_client, tmp_path, capsys):
    out = tmp_path / "profile.json"
    material = tmp_path / "material"
    material.mkdir()
    (material / "cv.md").write_text("Python developer.", encoding="utf-8")
    assert main(["ingest", str(material), "--out", str(out)]) == 3
    err = capsys.readouterr().err
    assert "paid API call" in err and "--allow-api" in err
    assert not out.exists()


def test_cli_still_runs_with_replay(no_client, tmp_path):
    material = tmp_path / "material"
    material.mkdir()
    (material / "cv.md").write_text("Python developer.", encoding="utf-8")
    replay = tmp_path / "answer.json"
    replay.write_text(
        json.dumps(
            {
                "model": "test",
                "answer": {
                    "headline": "Developer",
                    "experiences": [],
                    "skills": [
                        {
                            "name": "python",
                            "category": "technology",
                            "self_level": None,
                            "evidence": [{"source": "S1", "quote": "Python developer"}],
                        }
                    ],
                    "preferences": {
                        "locations": [],
                        "work_modes": [],
                        "work_permits": [],
                        "dealbreakers": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "profile.json"
    args = ["ingest", str(material), "--replay", str(replay), "--out", str(out)]
    assert main(args) == 0
    assert out.exists()


def test_spend_is_read_from_the_call_log():
    assert logged_spend() == (0, 0.0)
    path = call_log_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"cost_usd": 0.25}) + "\n" + json.dumps({"cost_usd": 0.5}) + "\n",
        encoding="utf-8",
    )
    assert logged_spend() == (2, 0.75)
