"""A candidate's workspace: their material, current profile and a history of steps.

Each workspace is a folder in the data folder (`$UNAPPLY_DATA`, by default `data/`):

    data/<name>/
        workspace.json        settings, such as the GitHub username
        material/             uploaded files
        profile.json          the current profile
        history/              the profile after every step, numbered
        questions.json        interview questions waiting for answers, if any
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from unapply.schemas import Profile

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def data_dir() -> Path:
    """Return the data folder: `$UNAPPLY_DATA`, by default `data` here.

    Returns
    -------
    Path
        The folder. It may not exist yet.
    """
    return Path(os.environ.get("UNAPPLY_DATA", "data"))


@dataclass(frozen=True)
class Workspace:
    """One candidate's folder.

    Parameters
    ----------
    root : Path
        The workspace folder.
    """

    root: Path

    @classmethod
    def create(cls, name: str, base: Path | None = None, **settings: Any) -> Workspace:  # noqa: ANN401
        """Create a new, empty workspace.

        Parameters
        ----------
        name : str
            Folder name: lowercase letters, digits, "-" and "_", at most 64.
        base : Path or None, optional
            Folder to create it in, by default `data_dir()`.
        **settings
            Initial settings, such as `demo=True`.

        Returns
        -------
        Workspace
            The new workspace.

        Raises
        ------
        ValueError
            If the name isn't valid or the workspace already exists.
        """
        if not NAME.match(name):
            raise ValueError(
                "use lowercase letters, digits, '-' and '_' only, starting with a "
                "letter or digit"
            )
        root = (base or data_dir()) / name
        if (root / "workspace.json").exists():
            raise ValueError(f"a candidate called {name!r} already exists")
        (root / "material").mkdir(parents=True, exist_ok=True)
        ws = cls(root)
        ws.save_settings(settings)
        return ws

    @staticmethod
    def names(base: Path | None = None) -> list[str]:
        """List the workspaces in the data folder.

        Parameters
        ----------
        base : Path or None, optional
            Folder to look in, by default `data_dir()`.

        Returns
        -------
        list of str
            Workspace names, sorted.
        """
        base = base or data_dir()
        if not base.exists():
            return []
        return sorted(p.parent.name for p in base.glob("*/workspace.json"))

    @property
    def name(self) -> str:
        """The workspace's folder name."""
        return self.root.name

    @property
    def material(self) -> Path:
        """Folder of uploaded material."""
        return self.root / "material"

    def settings(self) -> dict[str, Any]:
        """Read the settings, such as `github` and `demo`.

        Returns
        -------
        dict
            The settings.
        """
        return json.loads((self.root / "workspace.json").read_text(encoding="utf-8"))

    def save_settings(self, settings: dict[str, Any]) -> None:
        """Replace the settings.

        Parameters
        ----------
        settings : dict
            The new settings. Must be JSON-serialisable.
        """
        (self.root / "workspace.json").write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )

    def profile(self) -> Profile | None:
        """Read the current profile.

        Returns
        -------
        Profile or None
            The profile, or None before the first extraction.
        """
        path = self.root / "profile.json"
        if not path.exists():
            return None
        return Profile.model_validate_json(path.read_text(encoding="utf-8"))

    def save_profile(self, profile: Profile, step: str) -> Path:
        """Make `profile` the current profile and keep a copy in the history.

        Parameters
        ----------
        profile : Profile
            The profile after `step`.
        step : str
            What produced it, such as "extracted" or "reviewed".

        Returns
        -------
        Path
            The history file written, such as `history/003_reviewed.json`.
        """
        text = profile.model_dump_json(indent=2)
        (self.root / "profile.json").write_text(text, encoding="utf-8")
        history = self.root / "history"
        history.mkdir(exist_ok=True)
        path = history / f"{len(self.history()) + 1:03d}_{step}.json"
        path.write_text(text, encoding="utf-8")
        return path

    def history(self) -> list[str]:
        """List the steps taken so far, oldest first.

        Returns
        -------
        list of str
            Step names, such as ["extracted", "reviewed", "estimated"].
        """
        history = self.root / "history"
        if not history.exists():
            return []
        return [p.stem.split("_", 1)[1] for p in sorted(history.glob("*.json"))]

    def pending_questions(self) -> list[dict[str, str]] | None:
        """Read interview questions waiting for answers.

        Returns
        -------
        list of dict or None
            Questions with `skill`, `reason` and `text`, or None if there are none.
        """
        path = self.root / "questions.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_pending_questions(self, questions: list[dict[str, str]] | None) -> None:
        """Store interview questions waiting for answers, or clear them with None.

        Parameters
        ----------
        questions : list of dict or None
            Questions with `skill`, `reason` and `text`.
        """
        path = self.root / "questions.json"
        if questions is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(questions, indent=2), encoding="utf-8")
