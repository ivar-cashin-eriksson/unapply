"""John Doe, a synthetic candidate, from material to an interviewed profile.

Runs the commands a candidate runs: ingest, review export, edit, review apply,
estimate, interview export, answer, interview apply and estimate again. By default
the model's answers are replayed from tests/fixtures/john_doe/, so the test is free
and offline. With UNAPPLY_LIVE=1 it calls Claude instead (about $0.35). With
UNAPPLY_E2E_OUT=<folder> the files are kept there instead of a temporary folder.
"""

import os
import re
from pathlib import Path

import pytest
import yaml

from unapply.cli import main
from unapply.schemas import Profile, SkillLevel, SourceKind

FIXTURE = Path(__file__).parent / "fixtures" / "john_doe"
LIVE = os.environ.get("UNAPPLY_LIVE") == "1"


@pytest.fixture
def out(tmp_path):
    folder = Path(os.environ.get("UNAPPLY_E2E_OUT") or tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    for name in (
        "profile.draft.json",
        "review.yaml",
        "profile.reviewed.json",
        "profile.estimated.json",
        "interview.yaml",
        "profile.interviewed.json",
        "profile.reestimated.json",
    ):
        (folder / name).unlink(missing_ok=True)
    return folder


def edit_sheet(sheet_text: str, edits: dict) -> tuple[str, list[str]]:
    """Make John's edits to an exported sheet; return it and the names not found."""
    sheet = yaml.safe_load(sheet_text)
    names = {s["name"] for s in sheet["skills"]}
    missing = [n for n in [*edits["levels"], *edits["remove_skills"]] if n not in names]
    for skill in sheet["skills"]:
        if skill["name"] in edits["levels"]:
            skill["level"] = edits["levels"][skill["name"]]
        if skill["name"] in edits["remove_skills"]:
            skill["keep"] = False
    for x in sheet["experiences"]:
        if any(x["title"].startswith(t) for t in edits["remove_experiences"]):
            x["keep"] = False
    sheet["preferences"].update(edits["preferences"])
    sheet["add_skills"] = edits["add_skills"]
    sheet["approve"] = True
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False), missing


def run(*args: object) -> int:
    return main([str(a) for a in args])


def test_john_doe_from_material_to_estimated_profile(out, capsys):
    edits = yaml.safe_load((FIXTURE / "review_edits.yaml").read_text(encoding="utf-8"))
    draft, sheet, reviewed = (
        out / "profile.draft.json",
        out / "review.yaml",
        out / "profile.reviewed.json",
    )

    # 1. Ingest his material.
    model = (
        ["--allow-api", "--record", out / "extraction.json"]
        if LIVE
        else ["--replay", FIXTURE / "extraction.json"]
    )
    assert run("ingest", FIXTURE / "material", *model, "--out", draft) == 0
    printed = capsys.readouterr().out
    assert "source: cv         cv.md" in printed
    assert "rejected quotes (not found in their source): 0" in printed
    assert "dropped for lack of evidence: 0" in printed

    # Contact details on the CV stay out of the profile.
    assert not re.search(r"john\.doe@|\+45", draft.read_text(encoding="utf-8"))

    # 2. Export a review sheet; exporting again doesn't overwrite it.
    assert run("review", "export", draft, "--sheet", sheet) == 0
    assert run("review", "export", draft, "--sheet", sheet) == 2

    # 3. He edits it, first with a typo, which is rejected and names the skill.
    exported = sheet.read_text(encoding="utf-8")
    edited, missing = edit_sheet(exported, edits)
    if LIVE and missing:
        print(f"live extraction named these differently, not edited: {missing}")
    else:
        assert missing == []
    typo = {**edits, "levels": {**edits["levels"], "python": 6}}
    sheet.write_text(edit_sheet(exported, typo)[0], encoding="utf-8")
    capsys.readouterr()
    assert run("review", "apply", draft, sheet, "--out", reviewed) == 2
    assert 'skills "python" level' in capsys.readouterr().err
    assert not reviewed.exists()

    # 4. Fixed, it applies and is approved.
    sheet.write_text(edited, encoding="utf-8")
    assert run("review", "apply", draft, sheet, "--out", reviewed) == 0
    profile = Profile.model_validate_json(reviewed.read_text(encoding="utf-8"))

    assert profile.approved_by_candidate_at is not None
    assert profile.preferences.salary_min == 600_000
    names = {s.name for s in profile.skills}
    assert names.isdisjoint(edits["remove_skills"])
    assert not any(x.title.startswith("Open-source") for x in profile.experiences)
    for name, level in edits["levels"].items():
        if name in names:
            assert profile.skill(name).self_level == SkillLevel(level)

    # Added skills rest only on his own statement, kept apart from his documents.
    kinds = {s.id: s.kind for s in profile.sources}
    evidence = {e.id: e for e in profile.evidence}
    for name in edits["answer_key"]["self_stated_only"]:
        sources = {
            kinds[evidence[i].source_id] for i in profile.skill(name).evidence_ids
        }
        assert sources == {SourceKind.INTERVIEW}

    # The overclaims are in place for M2 to catch.
    for name in edits["answer_key"]["overclaims"]:
        if name in names:
            assert profile.skill(name).self_level == SkillLevel.ADVANCED

    # 5. Estimate his levels from the evidence and check his claims.
    estimated = out / "profile.estimated.json"
    model = (
        ["--allow-api", "--record", out / "estimation.json"]
        if LIVE
        else ["--replay", FIXTURE / "estimation.json"]
    )
    assert run("estimate", reviewed, *model, "--out", estimated) == 0
    assert "problems with the model's answer" not in capsys.readouterr().out
    profile = Profile.model_validate_json(estimated.read_text(encoding="utf-8"))
    key = edits["answer_key"]
    support = profile.claim_support
    assert set(key["overclaims"]) <= set(support.overclaims)
    assert set(key["unverified"]) <= set(support.unverified)
    assert set(support.unsupported_claims) == set(key["self_stated_only"])
    flagged = set(support.overclaims) | set(support.unverified)
    assert flagged.isdisjoint(key["consistent"])
    for name in key["consistent"]:
        s = profile.skill(name)
        assert abs(int(s.self_level) - int(s.estimate.level)) <= 1
    for name in key["rated_lower_than_estimate"]:
        s = profile.skill(name)
        assert s.estimate.level > s.self_level
    assert support.rated == 26 and support.score is None
    # Estimates never see his own levels, and every one cites its own evidence.
    for s in profile.skills:
        assert s.estimate is not None
        assert set(s.estimate.evidence_ids) <= set(s.evidence_ids)

    # 6. Follow-up questions about what his documents don't show.
    questions = out / "interview.yaml"
    model = (
        ["--allow-api", "--record", out / "questions.json"]
        if LIVE
        else ["--replay", FIXTURE / "questions.json"]
    )
    assert run("interview", "export", estimated, "--sheet", questions, *model) == 0
    sheet = yaml.safe_load(questions.read_text(encoding="utf-8"))
    asked = [q["skill"] for q in sheet["questions"]]
    assert len(asked) == 8
    # Unverified and self-stated skills come before overclaims.
    assert set(asked[:4]) == set(key["unverified"])
    assert set(asked[4:6]) == set(key["self_stated_only"])
    assert set(asked[6:]) <= set(key["overclaims"])

    # 7. He answers some of them, and only the answered skills are re-estimated.
    interview = yaml.safe_load(
        (FIXTURE / "interview_answers.yaml").read_text(encoding="utf-8")
    )
    for q in sheet["questions"]:
        q["answer"] = interview["answers"].get(q["skill"], "")
    questions.write_text(yaml.safe_dump(sheet, allow_unicode=True), encoding="utf-8")
    answered = out / "profile.interviewed.json"
    assert run("interview", "apply", estimated, questions, "--out", answered) == 0
    assert "4 answers added" in capsys.readouterr().out

    after = out / "profile.reestimated.json"
    model = (
        ["--allow-api", "--record", out / "estimation_after_interview.json"]
        if LIVE
        else ["--replay", FIXTURE / "estimation_after_interview.json"]
    )
    assert run("estimate", answered, *model, "--out", after) == 0
    printed = capsys.readouterr().out
    assert "Estimating 4 skills without an estimate" in printed
    assert "problems with the model's answer" not in printed
    before, now = (
        profile,
        Profile.model_validate_json(after.read_text(encoding="utf-8")),
    )
    expect = interview["expect"]
    for name in expect["raised"]:
        assert now.skill(name).estimate.level > before.skill(name).estimate.level
        assert name not in now.claim_support.unverified
    for name in expect["unchanged"]:
        assert now.skill(name).estimate.level == before.skill(name).estimate.level
    for name in expect["confidence_capped"]:
        assert now.skill(name).estimate.confidence <= 0.3
    for s in now.skills:
        if s.name not in interview["answers"]:
            assert s.estimate == before.skill(s.name).estimate
