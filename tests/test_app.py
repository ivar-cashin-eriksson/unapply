"""The candidate app, clicked through headlessly with Streamlit's AppTest.

The John Doe demo replays recorded answers, so the whole journey runs offline. No
test may create an API client: the `no_client` fixture fails if one is created.
"""

from pathlib import Path

import anthropic
import pytest
from streamlit.testing.v1 import AppTest

from unapply.workspace import Workspace

APP = Path(__file__).parents[1] / "src" / "unapply" / "app" / "main.py"


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the app created an API client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


def start() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    return at


def go(at: AppTest, step: str) -> None:
    at.radio(key="step").set_value(step).run()
    assert not at.exception


def click(at: AppTest, key: str) -> None:
    at.button(key=key).click().run()
    assert not at.exception, [e.message for e in at.exception]


def flash(at: AppTest) -> str:
    return " ".join(s.value for s in at.success)


def test_john_doe_demo_from_material_to_profile():
    at = start()
    click(at, "demo")
    assert at.session_state["workspace"] == "john-doe-demo"
    assert any("Demo" in i.value for i in at.sidebar.info)

    # Material: extract (replayed).
    click(at, "extract")
    assert "Extracted 7 experiences and 45 skills" in flash(at)

    # Review: John's edits, approved.
    go(at, "Review")
    click(at, "john_review")
    assert "Saved: 6 experiences, 30 skills, 26 with your level. Approved." in flash(at)

    # Estimate: every skill, with John's findings.
    go(at, "Estimate")
    assert at.button(key="estimate").label == "Estimate 30 skills"
    click(at, "estimate")
    assert "3 overclaims, 4 unverified" in flash(at)
    assert [m.value for m in at.metric] == ["3", "4", "0", "2"]

    # Interview: questions, John's answers, submit.
    go(at, "Interview")
    click(at, "write_questions")
    assert len(at.text_area) == 8
    click(at, "john_answers")
    answers = [a.value for a in at.text_area]
    assert sum(bool(a) for a in answers) == 4
    [submit] = [b for b in at.button if b.label == "Submit answers"]
    submit.click().run()
    assert not at.exception
    assert "4 answers added" in flash(at)

    # Re-estimate only the answered skills.
    go(at, "Estimate")
    assert at.button(key="estimate").label == "Estimate 4 skills"
    click(at, "estimate")
    assert "3 overclaims, 3 unverified" in flash(at)

    # Profile, with every step done.
    go(at, "Profile")
    assert at.header[0].value == "5. Your profile"
    assert all(o.startswith("✓") for o in at.radio(key="step").options)


def test_paid_steps_are_disabled_until_allowed():
    at = start()
    at.text_input(key="new_name").input("jane").run()
    click(at, "create")
    assert at.session_state["workspace"] == "jane"
    extract = at.button(key="extract")
    assert extract.disabled
    assert any("Paid API calls are off" in c.value for c in at.caption)
    # A new session starts with the toggle off; turning it on enables the button.
    assert at.toggle(key="allow_api").value is False
    at.toggle(key="allow_api").set_value(True).run()
    assert not at.button(key="extract").disabled


def test_invalid_candidate_names_are_refused():
    at = start()
    at.text_input(key="new_name").input("Jane Doe!").run()
    click(at, "create")
    assert at.error and "lowercase" in at.error[0].value
    assert Workspace.names() == []
