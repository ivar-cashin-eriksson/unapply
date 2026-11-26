"""Importing workspace folders (`unapply.workspace`) into the database.

A candidate workspace brings its settings, history, current profile and waiting
questions; a job workspace its settings, history and job, with every rubric version
in its history. Uploaded material stays in the folder: sources keep pointing to it
by their `uri`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from unapply.db.models import (
    CandidateHistoryRow,
    CandidateRow,
    InterviewQuestionRow,
    JobHistoryRow,
    JobRow,
)
from unapply.db.repository import (
    Repository,
    _candidate,
    _check_name,
    _job,
    _store_job,
    _store_profile,
)
from unapply.schemas import Job, Profile
from unapply.workspace import Workspace


def is_job_workspace(path: Path) -> bool:
    """Whether a workspace folder holds a job rather than a candidate.

    Parameters
    ----------
    path : Path
        The workspace folder.

    Returns
    -------
    bool
        True if it has a `job.json`, or is in a folder called `jobs` (a job
        workspace before its ad is extracted).
    """
    return (path / "job.json").exists() or path.resolve().parent.name == "jobs"


def import_workspace(repo: Repository, path: Path) -> str:
    """Import one workspace folder, under the folder's name.

    Everything is imported in one transaction: if anything fails, nothing is.

    Parameters
    ----------
    repo : Repository
        The database to import into.
    path : Path
        The workspace folder, with a `workspace.json`.

    Returns
    -------
    str
        "candidate" or "job".

    Raises
    ------
    ValueError
        If the folder isn't a workspace, its name isn't valid, a candidate or job
        with that name is already in the database, or a file in it isn't valid.
    """
    if not (path / "workspace.json").exists():
        raise ValueError(f"{path} is not a workspace: it has no workspace.json")
    ws = Workspace(path)
    _check_name(ws.name)
    history = _history(path)
    created = datetime.fromtimestamp((path / "workspace.json").stat().st_mtime)
    with repo.transaction() as s:
        if is_job_workspace(path):
            if _job(s, ws.name, missing_ok=True) is not None:
                raise ValueError(f"a job called {ws.name!r} already exists")
            job_row = JobRow(id=uuid4(), name=ws.name, settings=ws.settings())
            s.add(job_row)
            s.flush()
            for step, text, saved_at in history:
                job = Job.model_validate_json(text)
                _store_job(s, job_row, job)
                s.add(
                    JobHistoryRow(
                        job_id=job_row.id,
                        step=step,
                        job=job.model_dump(mode="json"),
                        saved_at=saved_at,
                    )
                )
            current = ws.job()
            if current is not None:
                _store_job(s, job_row, current)
            return "job"

        if _candidate(s, ws.name, missing_ok=True) is not None:
            raise ValueError(f"a candidate called {ws.name!r} already exists")
        row = CandidateRow(
            id=uuid4(), name=ws.name, settings=ws.settings(), created_at=created
        )
        s.add(row)
        s.flush()
        for step, text, saved_at in history:
            s.add(
                CandidateHistoryRow(
                    candidate_id=row.id,
                    step=step,
                    profile=Profile.model_validate_json(text).model_dump(mode="json"),
                    saved_at=saved_at,
                )
            )
        profile = ws.profile()
        if profile is not None:
            _store_profile(s, row, profile)
        asked = datetime.fromtimestamp(
            (path / "questions.json").stat().st_mtime
            if (path / "questions.json").exists()
            else created.timestamp()
        )
        for i, q in enumerate(ws.pending_questions() or []):
            s.add(
                InterviewQuestionRow(
                    candidate_id=row.id,
                    position=i,
                    skill=q["skill"],
                    reason=q["reason"],
                    text=q["text"],
                    asked_at=asked,
                )
            )
        return "candidate"


def _history(path: Path) -> list[tuple[str, str, datetime]]:
    """Read the history files, oldest first: step, JSON text and when written."""
    folder = path / "history"
    if not folder.exists():
        return []
    return [
        (
            f.stem.split("_", 1)[1],
            f.read_text(encoding="utf-8"),
            datetime.fromtimestamp(f.stat().st_mtime),
        )
        for f in sorted(folder.glob("*.json"))
    ]
