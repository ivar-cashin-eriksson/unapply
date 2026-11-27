"""Load candidate material into plain-text documents.

Each document keeps the exact text the model sees, so evidence quotes can be checked
against it afterwards.
"""

from __future__ import annotations

import csv
import fnmatch
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from unapply.schemas import Source, SourceKind

TEXT_SUFFIXES = {".txt", ".md", ".tex", ".yaml", ".yml", ".json"}

# Files in a folder that describe the folder rather than the candidate, such as a
# README saying what each file is: their text would be read as claims about the
# candidate. Matched on the lowercase file name without its suffix.
FOLDER_FILES = {"readme", "changelog", "contributing", "license", "licence"}

# Why a file in a folder isn't loaded.
EXCLUDED = "excluded"
DESCRIBES_FOLDER = "describes the folder, not the candidate"
SCHEMA = "a schema, not material about the candidate"
UNSUPPORTED = "not a file type that can be read"

# The only LinkedIn export files and columns that are loaded, and so the only ones
# sent to the model. The export also holds messages, connections (other people's
# data), contact details, receipts and ID verification: none of that belongs in a
# profile. None means every column. Files are rendered in this order.
LINKEDIN_COLUMNS: dict[str, tuple[str, ...] | None] = {
    "Profile.csv": ("Headline", "Summary", "Industry", "Geo Location"),
    "Profile Summary.csv": None,
    "Positions.csv": None,
    "Education.csv": None,
    "Skills.csv": None,
    "Languages.csv": None,
    "Certifications.csv": ("Name", "Authority", "Started On", "Finished On"),
    "Honors.csv": None,
    "Organizations.csv": None,
    "Projects.csv": None,
    "Publications.csv": None,
    "Courses.csv": None,
    "TestScores.csv": None,
    "Volunteering.csv": None,
    "Job Seeker Preferences.csv": (
        "Locations",
        "Industries",
        "Company Employee Count",
        "Preferred Job Types",
        "Job Titles",
        "Preferred Start Time Range",
    ),
}


@dataclass(frozen=True)
class SkippedFile:
    """A file in a folder that isn't loaded, and why.

    Parameters
    ----------
    path : Path
        The file (or folder, if excluded as a whole).
    reason : str
        Why it is skipped: `EXCLUDED`, `DESCRIBES_FOLDER`, `SCHEMA` or
        `UNSUPPORTED`.
    """

    path: Path
    reason: str


@dataclass(frozen=True)
class SourceDocument:
    """A source with the text extracted from it.

    Parameters
    ----------
    source : Source
        The source the text comes from.
    name : str
        Human-readable name, such as the file name.
    text : str
        The extracted text, exactly as shown to the model.
    """

    source: Source
    name: str
    text: str


def load_path(
    path: Path,
    kind: SourceKind | None = None,
    *,
    exclude: Sequence[str] = (),
    skipped: list[SkippedFile] | None = None,
) -> list[SourceDocument]:
    """Load a file, or every supported file in a folder.

    LinkedIn data exports (a zip, or a folder containing `Positions.csv`) are loaded
    as one LinkedIn document. In a folder, files that aren't about the candidate
    are skipped: files describing the folder, such as `README.md` (see
    `FOLDER_FILES`), and JSON or YAML schemas (a top-level `$schema` key). A file
    given by name is always loaded if it can be read.

    Parameters
    ----------
    path : Path
        A file or a folder. Folders are searched recursively.
    kind : SourceKind or None, optional
        Kind to give the documents. By default it is guessed: PDFs and text
        files named like `cv.md` or `jane_resume.txt` are CVs, LinkedIn exports
        are LinkedIn, and other text files are free text.
    exclude : sequence of str, optional
        Glob patterns of files or folders in `path` that the candidate leaves out,
        such as "old_cv.pdf", "*.json" or "drafts/*". Matched, ignoring case,
        against the file name and the path relative to `path` (with "/").
    skipped : list of SkippedFile or None, optional
        If given, every file in a folder that isn't loaded is appended to it, with
        the reason, so the caller can say what was left out.

    Returns
    -------
    list of SourceDocument
        One document per file, in path order.

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir() and not _is_linkedin_export(path):
        docs: list[SourceDocument] = []
        _load_folder(path, path, kind, tuple(exclude), docs, skipped)
        return docs
    return _load_file(path, kind)


def skip_reason(path: Path) -> str | None:
    """Say why a file found in a folder isn't loaded, apart from exclusions.

    Parameters
    ----------
    path : Path
        A file.

    Returns
    -------
    str or None
        `DESCRIBES_FOLDER`, `SCHEMA` or `UNSUPPORTED`; None if the file is loaded.
    """
    if _is_linkedin_export(path):
        return None
    if path.stem.lower() in FOLDER_FILES:
        return DESCRIBES_FOLDER
    suffix = path.suffix.lower()
    if suffix != ".pdf" and suffix not in TEXT_SUFFIXES:
        return UNSUPPORTED
    if suffix in {".json", ".yaml", ".yml"} and _is_schema(path):
        return SCHEMA
    return None


def _load_folder(
    folder: Path,
    root: Path,
    kind: SourceKind | None,
    exclude: tuple[str, ...],
    docs: list[SourceDocument],
    skipped: list[SkippedFile] | None,
) -> None:
    """Load a folder's files into `docs`, recording skipped ones in `skipped`."""
    for child in sorted(folder.iterdir()):
        relative = child.relative_to(root).as_posix().lower()
        if any(
            fnmatch.fnmatchcase(name, pattern.lower())
            for pattern in exclude
            for name in (child.name.lower(), relative)
        ):
            reason: str | None = EXCLUDED
        elif child.is_dir() and not _is_linkedin_export(child):
            _load_folder(child, root, kind, exclude, docs, skipped)
            continue
        else:
            reason = None if child.is_dir() else skip_reason(child)
        if reason is None:
            docs.extend(_load_file(child, kind))
        elif skipped is not None:
            skipped.append(SkippedFile(child, reason))


def _is_schema(path: Path) -> bool:
    """Whether a JSON or YAML file is a JSON Schema: a mapping with `$schema`."""
    try:
        text = path.read_text(encoding="utf-8")
        data = (
            json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
        )
    except (ValueError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and "$schema" in data


def _load_file(path: Path, kind: SourceKind | None) -> list[SourceDocument]:
    """Load one file, or a LinkedIn export; nothing if it can't be read."""
    if _is_linkedin_export(path):
        return [load_linkedin_export(path)]
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return [_document(kind or SourceKind.CV, path, _pdf_text(path))]
    if suffix in TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        guessed = SourceKind.CV if _looks_like_cv(path) else SourceKind.FREE_TEXT
        return [_document(kind or guessed, path, text)]
    return []


def load_linkedin_export(path: Path) -> SourceDocument:
    """Load a LinkedIn data export as one document.

    LinkedIn's "Get a copy of your data" export is a zip of CSV files. Only the
    files and columns in `LINKEDIN_COLUMNS` are used, each as a section with one line
    per row. Two more sections are derived without personal data: endorsements
    received, as a count per skill without the endorsers' names, and completed
    LinkedIn Learning courses.

    Parameters
    ----------
    path : Path
        The export zip, or the folder it was unpacked to.

    Returns
    -------
    SourceDocument
        A LinkedIn document.
    """
    if path.is_dir():
        files = {p.name: p.read_text(encoding="utf-8-sig") for p in path.glob("*.csv")}
    else:
        with zipfile.ZipFile(path) as zf:
            files = {
                Path(n).name: zf.read(n).decode("utf-8-sig")
                for n in zf.namelist()
                if n.lower().endswith(".csv")
            }
    sections = [
        _csv_section(name, files[name], columns)
        for name, columns in LINKEDIN_COLUMNS.items()
        if name in files
    ]
    if "Endorsement_Received_Info.csv" in files:
        sections.append(_endorsements(files["Endorsement_Received_Info.csv"]))
    if "Learning.csv" in files:
        sections.append(_completed_learning(files["Learning.csv"]))
    text = "\n\n".join(s for s in sections if s)
    return _document(SourceKind.LINKEDIN, path, text)


def _endorsements(content: str) -> str:
    """Count endorsements per skill; endorser names are not kept."""
    counts = Counter(
        row["Skill Name"].strip()
        for row in csv.DictReader(io.StringIO(content))
        if (row.get("Skill Name") or "").strip()
        and (row.get("Endorsement Status") or "ACCEPTED").upper() == "ACCEPTED"
    )
    lines = [f"{skill}: {n}" for skill, n in counts.most_common()]
    return "## Endorsements received (per skill)\n" + "\n".join(lines) if lines else ""


def _completed_learning(content: str) -> str:
    """List completed LinkedIn Learning content with its completion date."""
    lines = [
        f"{row['Content Title']} ({row.get('Content Type') or 'content'}), "
        f"completed {row['Content Completed At (if completed)']}"
        for row in csv.DictReader(io.StringIO(content))
        if (row.get("Content Completed At (if completed)") or "").strip()
        and row.get("Content Title")
    ]
    return "## Completed LinkedIn Learning\n" + "\n".join(lines) if lines else ""


def _is_linkedin_export(path: Path) -> bool:
    if path.is_dir():
        return (path / "Positions.csv").exists()
    if path.suffix.lower() == ".zip" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return any(Path(n).name == "Positions.csv" for n in zf.namelist())
    return False


def _csv_section(name: str, content: str, columns: tuple[str, ...] | None) -> str:
    """Render a CSV as '## name' and one 'key: value; ...' line per row."""
    rows = list(csv.DictReader(io.StringIO(content)))
    lines = [
        "; ".join(
            f"{k}: {v}"
            for k, v in row.items()
            if k and v and v.strip() and (columns is None or k in columns)
        )
        for row in rows
    ]
    lines = [line for line in lines if line]
    return f"## {Path(name).stem}\n" + "\n".join(lines) if lines else ""


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def _document(kind: SourceKind, path: Path, text: str) -> SourceDocument:
    return SourceDocument(
        source=Source(kind=kind, uri=path.as_posix()), name=path.name, text=text
    )


def _looks_like_cv(path: Path) -> bool:
    """Whether a text file's name says it is a CV, such as cv.md or john_resume.txt."""
    return bool(
        re.search(r"(^|[_\-. ])(cv|resume|résumé)([_\-. ]|$)", path.stem.lower())
    )
