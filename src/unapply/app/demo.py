"""The free demo: John Doe, a synthetic candidate, with recorded model answers.

A demo workspace replays the answers recorded in `tests/fixtures/john_doe/`, so every
step works without paid API calls. The replies only fit John's material and his
choices, so the app offers to fill in his review edits and interview answers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from unapply.llm import ReplayLLM
from unapply.review import export_review_sheet
from unapply.schemas import Profile, SourceKind
from unapply.workspace import Workspace, jobs_dir

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
FIXTURE = FIXTURES / "john_doe"
JOB_FIXTURE = FIXTURES / "jobs" / "fjord_grocery"


def available() -> bool:
    """Whether the demo fixtures are present (they are in a checkout of the repo).

    Returns
    -------
    bool
        True if the demo can be created.
    """
    return (FIXTURE / "material").is_dir()


def create_demo(base: Path | None = None) -> Workspace:
    """Create a new demo workspace with John Doe's material.

    Parameters
    ----------
    base : Path or None, optional
        Data folder to create it in, by default `data_dir()`.

    Returns
    -------
    Workspace
        A workspace named "john-doe-demo", or "john-doe-demo-2" and so on if taken.
    """
    taken = set(Workspace.names(base))
    name = "john-doe-demo"
    n = 2
    while name in taken:
        name = f"john-doe-demo-{n}"
        n += 1
    ws = Workspace.create(name, base, demo=True)
    for f in (FIXTURE / "material").iterdir():
        shutil.copy(f, ws.material / f.name)
    return ws


def create_demo_job(base: Path | None = None) -> Workspace:
    """Create a new demo job workspace with the Fjord Grocery ad.

    Parameters
    ----------
    base : Path or None, optional
        Folder of job workspaces, by default `jobs_dir()`.

    Returns
    -------
    Workspace
        A workspace named "fjord-grocery-demo", or with a number if taken.
    """
    base = base or jobs_dir()
    taken = set(Workspace.names(base))
    name, n = "fjord-grocery-demo", 2
    while name in taken:
        name, n = f"fjord-grocery-demo-{n}", n + 1
    ws = Workspace.create(name, base, demo=True)
    shutil.copy(JOB_FIXTURE / "ad.md", ws.root / "ad.md")
    return ws


def demo_llm(purpose: str, profile: Profile | None = None) -> ReplayLLM:
    """Pick the recorded model for a step of John's journey.

    Parameters
    ----------
    purpose : str
        "extract", "estimate", "questions" or "rubric".
    profile : Profile or None, optional
        For "estimate": after an interview, the re-estimate is replayed.

    Returns
    -------
    ReplayLLM
        Replays the recorded answer.
    """
    if purpose == "rubric":
        return ReplayLLM(JOB_FIXTURE / "extraction.json")
    if purpose == "extract":
        return ReplayLLM(FIXTURE / "extraction.json")
    if purpose == "questions":
        return ReplayLLM(FIXTURE / "questions.json")
    if profile is not None and _interviewed(profile):
        return ReplayLLM(FIXTURE / "estimation_after_interview.json")
    return ReplayLLM(FIXTURE / "estimation.json")


def review_edits() -> dict[str, Any]:
    """John's review edits and answer key, from `review_edits.yaml`.

    Returns
    -------
    dict
        The parsed file.
    """
    return yaml.safe_load((FIXTURE / "review_edits.yaml").read_text(encoding="utf-8"))


def john_answers() -> dict[str, str]:
    """John's interview answers, by skill.

    Returns
    -------
    dict of str to str
        Skill name to answer. Skills not in it are skipped.
    """
    path = FIXTURE / "interview_answers.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["answers"]


def edit_review_sheet(sheet_text: str, edits: dict[str, Any]) -> tuple[str, list[str]]:
    """Make review edits to an exported review sheet.

    Parameters
    ----------
    sheet_text : str
        A sheet from `export_review_sheet`.
    edits : dict
        Edits in the format of `review_edits.yaml`.

    Returns
    -------
    str
        The edited sheet, approved.
    list of str
        Skill names in the edits that aren't on the sheet.
    """
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


def john_review_sheet(profile: Profile) -> str:
    """John's edited review sheet for his draft profile.

    Parameters
    ----------
    profile : Profile
        John's extracted draft.

    Returns
    -------
    str
        The sheet with his edits, approved.
    """
    return edit_review_sheet(export_review_sheet(profile), review_edits())[0]


def _interviewed(profile: Profile) -> bool:
    return any(
        s.kind == SourceKind.INTERVIEW and s.uri == "interview" for s in profile.sources
    )
