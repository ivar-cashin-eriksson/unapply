"""The command line's refusals: each prints why, exits 2 and writes nothing.

The happy paths are tested with the steps they run (test_end_to_end.py, test_jobs.py,
test_evaluation.py and others); these are the ways a command stops early. Inputs are
the synthetic pool's profiles and job, and no model is called.
"""

from pathlib import Path

import pytest

from unapply.cli import main
from unapply.evaluation import load_pool
from unapply.schemas import Profile

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTION = FIXTURES / "john_doe" / "extraction.json"


@pytest.fixture(scope="module")
def pool():
    return load_pool()


@pytest.fixture
def profile_path(tmp_path, pool) -> Path:
    """Astrid Holm's estimated profile: every skill estimated, nothing to ask."""
    path = tmp_path / "profile.json"
    profile = pool.candidates["astrid-holm"].profile
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


@pytest.fixture
def job_path(tmp_path, pool) -> Path:
    path = tmp_path / "job.json"
    path.write_text(pool.job.model_dump_json(indent=2), encoding="utf-8")
    return path


def run(*args: object) -> int:
    return main([str(a) for a in args])


def test_interview_export_keeps_an_existing_sheet(profile_path, tmp_path, capsys):
    sheet = tmp_path / "interview.yaml"
    sheet.write_text("my answers\n", encoding="utf-8")
    assert run("interview", "export", profile_path, "--sheet", sheet) == 2
    assert "not overwriting your answers" in capsys.readouterr().err
    assert sheet.read_text(encoding="utf-8") == "my answers\n"


def test_interview_export_needs_claim_support(profile_path, tmp_path, capsys):
    profile = Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    profile_path.write_text(
        profile.model_copy(update={"claim_support": None}).model_dump_json(),
        encoding="utf-8",
    )
    sheet = tmp_path / "interview.yaml"
    assert run("interview", "export", profile_path, "--sheet", sheet) == 2
    assert "run `unapply estimate` first" in capsys.readouterr().err
    assert not sheet.exists()


def test_interview_export_with_nothing_to_ask(profile_path, tmp_path, capsys):
    # No --replay or --allow-api: with nothing to ask, no model is needed.
    sheet = tmp_path / "interview.yaml"
    assert run("interview", "export", profile_path, "--sheet", sheet) == 0
    assert "Nothing to ask" in capsys.readouterr().out
    assert not sheet.exists()


@pytest.mark.parametrize(
    "text, message",
    [
        ("questions: [unclosed\n", "isn't valid YAML"),
        ("", "empty or not a mapping"),
        (
            "profile: 00000000-0000-0000-0000-000000000000\nquestions: []\n",
            "this sheet is for profile 00000000",
        ),
        (
            "profile: {id}\nquestions:\n- skill: Underwater basket weaving\n"
            "  question: Have you?\n  answer: Yes\n",
            "skills not in the profile: ['Underwater basket weaving']",
        ),
    ],
)
def test_interview_apply_rejects_a_bad_sheet(
    profile_path, tmp_path, capsys, text, message
):
    sheet, out = tmp_path / "interview.yaml", tmp_path / "answered.json"
    profile = Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    sheet.write_text(text.replace("{id}", str(profile.id)), encoding="utf-8")
    assert run("interview", "apply", profile_path, sheet, "--out", out) == 2
    assert message in capsys.readouterr().err
    assert not out.exists()


def test_interview_apply_with_no_answers_writes_the_profile_unchanged(
    profile_path, tmp_path, capsys
):
    sheet, out = tmp_path / "interview.yaml", tmp_path / "answered.json"
    profile = Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    sheet.write_text(f"profile: {profile.id}\nquestions: []\n", encoding="utf-8")
    assert run("interview", "apply", profile_path, sheet, "--out", out) == 0
    printed = capsys.readouterr().out
    assert "0 answers added" in printed
    assert "unapply estimate" not in printed
    assert Profile.model_validate_json(out.read_text(encoding="utf-8")) == profile


def test_job_extract_wants_one_ad(tmp_path, capsys):
    folder = tmp_path / "ads"
    folder.mkdir()
    for name in ("one.md", "two.md"):
        (folder / name).write_text("# A job\n\nWork.\n", encoding="utf-8")
    out = tmp_path / "job.json"
    args = ["job", "extract", folder, "--replay", EXTRACTION, "--out", out]
    assert run(*args) == 2
    assert "Expected one job ad file, got 2" in capsys.readouterr().err
    assert not out.exists()


def test_job_export_keeps_an_existing_sheet(job_path, tmp_path, capsys):
    sheet = tmp_path / "rubric.yaml"
    sheet.write_text("my edits\n", encoding="utf-8")
    assert run("job", "export", job_path, "--sheet", sheet) == 2
    assert "not overwriting your edits" in capsys.readouterr().err
    assert sheet.read_text(encoding="utf-8") == "my edits\n"


def test_job_apply_rejects_a_bad_sheet(job_path, tmp_path, capsys):
    sheet, out = tmp_path / "rubric.yaml", tmp_path / "approved.json"
    sheet.write_text("criteria: [unclosed\n", encoding="utf-8")
    assert run("job", "apply", job_path, sheet, "--out", out) == 2
    assert "isn't valid YAML" in capsys.readouterr().err
    assert not out.exists()


def test_review_apply_rejects_a_bad_sheet(profile_path, tmp_path, capsys):
    sheet, out = tmp_path / "review.yaml", tmp_path / "reviewed.json"
    sheet.write_text("", encoding="utf-8")
    assert run("review", "apply", profile_path, sheet, "--out", out) == 2
    assert f"Can't apply {sheet}" in capsys.readouterr().err
    assert not out.exists()


def test_estimate_with_every_skill_estimated_calls_no_model(
    profile_path, tmp_path, capsys
):
    # No --replay or --allow-api: a needed paid call would stop it with exit 3.
    out = tmp_path / "estimated.json"
    assert run("estimate", profile_path, "--out", out) == 0
    assert "Every skill already has an estimate" in capsys.readouterr().out
    before = Profile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    after = Profile.model_validate_json(out.read_text(encoding="utf-8"))
    assert [s.estimate for s in after.skills] == [s.estimate for s in before.skills]


def test_ingest_needs_something_to_ingest(tmp_path, capsys):
    out = tmp_path / "draft.json"
    assert run("ingest", "--replay", EXTRACTION, "--out", out) == 2
    assert "Nothing to ingest" in capsys.readouterr().err
    assert not out.exists()


def test_ask_about_an_unknown_candidate(capsys):
    assert run("ask", "nobody-at-all", "team", "--replay", EXTRACTION) == 2
    assert "No candidate 'nobody-at-all' in the pool." in capsys.readouterr().err
