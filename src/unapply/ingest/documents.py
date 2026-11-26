"""Load candidate material into plain-text documents.

Each document keeps the exact text the model sees, so evidence quotes can be checked
against it afterwards.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from unapply.schemas import Source, SourceKind

TEXT_SUFFIXES = {".txt", ".md", ".tex", ".yaml", ".yml", ".json"}


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
        Kind to give the documents. By default it is guessed: PDFs are CVs,
        LinkedIn exports are LinkedIn, and other text files are free text.

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
        return [_document(kind or SourceKind.FREE_TEXT, path, text)]
    return []


def load_linkedin_export(path: Path) -> SourceDocument:
    """Load a LinkedIn data export as one document.

    LinkedIn's "Get a copy of your data" export is a zip of CSV files (`Profile.csv`,
    `Positions.csv`, `Education.csv`, `Skills.csv` and others). Each CSV becomes a
    section with one line per row.

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
    sections = [_csv_section(name, files[name]) for name in sorted(files)]
    text = "\n\n".join(s for s in sections if s)
    return _document(SourceKind.LINKEDIN, path, text)


def _is_linkedin_export(path: Path) -> bool:
    if path.is_dir():
        return (path / "Positions.csv").exists()
    if path.suffix.lower() == ".zip" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return any(Path(n).name == "Positions.csv" for n in zf.namelist())
    return False


def _csv_section(name: str, content: str) -> str:
    """Render one CSV as '## name' followed by one 'key: value; ...' line per row."""
    rows = list(csv.DictReader(io.StringIO(content)))
    lines = [
        "; ".join(f"{k}: {v}" for k, v in row.items() if k and v and v.strip())
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
