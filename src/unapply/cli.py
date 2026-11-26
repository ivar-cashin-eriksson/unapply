"""Command-line interface: `unapply <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from unapply.ingest.documents import SourceDocument, load_path
from unapply.ingest.extract import extract_profile
from unapply.ingest.github import fetch_github
from unapply.llm import DEFAULT_MODEL, AnthropicLLM


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    Parameters
    ----------
    argv : list of str or None, optional
        Arguments, by default `sys.argv[1:]`.

    Returns
    -------
    int
        Exit code.
    """
    # Windows consoles default to cp1252, which can't print most CV text.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="unapply")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Extract a profile from material.")
    ingest.add_argument("paths", nargs="*", type=Path, help="Files or folders.")
    ingest.add_argument("--github", help="GitHub username to include.")
    ingest.add_argument(
        "--out", type=Path, required=True, help="Profile JSON to write."
    )
    ingest.add_argument("--model", default=DEFAULT_MODEL)
    ingest.add_argument("--effort", default="high")
    ingest.add_argument(
        "--dump-sources", type=Path, help="Also write the text sent to the model."
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "ingest":
        return _ingest(args)
    return 1


def _ingest(args: argparse.Namespace) -> int:
    documents: list[SourceDocument] = []
    for path in args.paths:
        documents.extend(load_path(path))
    if args.github:
        documents.append(fetch_github(args.github))
    if not documents:
        print("Nothing to ingest: give paths or --github.", file=sys.stderr)
        return 2
    for d in documents:
        print(f"source: {d.source.kind:<10} {d.name} ({len(d.text):,} chars)")
    if args.dump_sources:
        from unapply.ingest.extract import render_sources

        args.dump_sources.write_text(render_sources(documents), encoding="utf-8")

    result = extract_profile(documents, AnthropicLLM(args.model, args.effort))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result.profile.model_dump_json(indent=2), encoding="utf-8")

    p = result.profile
    print(
        f"\nprofile: {len(p.experiences)} experiences, {len(p.skills)} skills, "
        f"{len(p.evidence)} evidence quotes -> {args.out}"
    )
    print(f"rejected quotes (not found in their source): {len(result.rejected_quotes)}")
    for q in result.rejected_quotes:
        print(f"  [{q.source}] {q.quote[:100]!r}")
    print(f"dropped for lack of evidence: {len(result.unsupported)}")
    for item in result.unsupported:
        print(f"  {item}")
    return 0
