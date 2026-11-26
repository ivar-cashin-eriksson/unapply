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
# Words that would give the hidden assessment away on a candidate's page.
ASSESSMENT_WORDS = ["overclaim", "underclaim", "unverified", "estimate", "confidence"]


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
    at.segmented_control(key="step").set_value(step).run()
    assert not at.exception, [e.message for e in at.exception]


def click(at: AppTest, key: str) -> None:
    at.button(key=key).click().run()
    assert not at.exception, [e.message for e in at.exception]


def flash(at: AppTest) -> str:
    return " ".join(s.value for s in at.success)


def visible_text(at: AppTest) -> str:
    """Everything a candidate can read on the current page, lowercased."""
    parts = [
        e.value
        for kind in (
            "markdown",
            "caption",
            "header",
            "subheader",
            "success",
            "info",
            "warning",
        )
        for e in getattr(at.main, kind)
    ]
    for df in at.main.dataframe:
        parts += [str(c) for c in df.value.columns] + df.value.astype(
            str
        ).values.ravel().tolist()
    return " ".join(str(p) for p in parts).lower()


def assert_no_assessment(at: AppTest) -> None:
    text = visible_text(at)
    assert not [w for w in ASSESSMENT_WORDS if w in text], text


def test_john_doe_demo_hides_the_assessment_from_the_candidate():
    at = start()
    click(at, "demo")
    assert at.session_state["workspace"] == "john-doe-demo"
    assert at.sidebar.selectbox(key="workspace").value == "john-doe-demo"

    # Material: extract (replayed); the app moves on to the review.
    click(at, "extract")
    assert "Found 7 experiences and 45 skills" in flash(at)
    assert at.session_state["step"] == "Review"

    # Review: John's edits, approved; the app moves on to the questions.
    click(at, "john_review")
    assert "Approved: 30 skills, 26 with your level" in flash(at)
    assert at.session_state["step"] == "Questions"
    assert_no_assessment(at)

    # Questions: the assessment runs in the background, then 8 questions.
    click(at, "prepare_questions")
    assert len(at.text_area) == 8
    assert_no_assessment(at)
    click(at, "john_answers")
    [submit] = [b for b in at.button if b.label == "Submit answers"]
    submit.click().run()
    assert not at.exception
    assert "4 answers saved" in flash(at)
    assert_no_assessment(at)

    # Profile: no estimates anywhere, and the download leaves them out too.
    go(at, "Profile")
    assert_no_assessment(at)
    download = at.get("download_button")[0]
    assert download.proto.label == "Download my profile"

    # Developer view: the internal page shows the assessment after the answers.
    at.sidebar.toggle(key="dev_view").set_value(True).run()
    go(at, "Assessment")
    assert any("Internal" in w.value for w in at.warning)
    assert [m.value for m in at.metric] == ["3", "3", "0", "2"]
    assert "Every skill has an estimate." in [c.value for c in at.caption]


def test_paid_steps_are_disabled_until_allowed():
    at = start()
    at.text_input(key="new_name").input("jane").run()
    click(at, "create")
    assert at.session_state["workspace"] == "jane"
    assert at.button(key="extract").disabled
    assert any("Paid API calls are off" in c.value for c in at.caption)
    # A new session starts with the toggle off; turning it on enables the button.
    assert at.toggle(key="allow_api").value is False
    at.toggle(key="allow_api").set_value(True).run()
    assert not at.button(key="extract").disabled


def test_assessment_page_is_only_in_the_developer_view():
    at = start()
    click(at, "demo")
    assert "Assessment" not in at.segmented_control(key="step").options
    at.sidebar.toggle(key="dev_view").set_value(True).run()
    assert "Assessment" in at.segmented_control(key="step").options


def test_invalid_candidate_names_are_refused():
    at = start()
    at.text_input(key="new_name").input("Jane Doe!").run()
    click(at, "create")
    assert at.error and "lowercase" in at.error[0].value
    assert Workspace.names() == []
