"""Load candidate material into plain-text documents.

Each document keeps the exact text the model sees, so evidence quotes can be checked
against it afterwards.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from unapply.schemas import Source, SourceKind

TEXT_SUFFIXES = {".txt", ".md", ".tex", ".yaml", ".yml", ".json"}

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


def load_path(path: Path, kind: SourceKind | None = None) -> list[SourceDocument]:
    """Load a file, or every supported file in a folder.

    LinkedIn data exports (a zip, or a folder containing `Positions.csv`) are loaded
    as one LinkedIn document.

    Parameters
    ----------
    path : Path
        A file or a folder. Folders are searched recursively.
    kind : SourceKind or None, optional
        Kind to give the documents. By default it is guessed: PDFs and text
        files named like `cv.md` or `jane_resume.txt` are CVs, LinkedIn exports
        are LinkedIn, and other text files are free text.

    Returns
    -------
    list of SourceDocument
        One document per file, in path order. Unsupported files are skipped.

    Raises
    ------
    FileNotFoundError
        If `path` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if _is_linkedin_export(path):
        return [load_linkedin_export(path)]
    if path.is_dir():
        docs: list[SourceDocument] = []
        for child in sorted(path.iterdir()):
            docs.extend(load_path(child, kind))
        return docs
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
