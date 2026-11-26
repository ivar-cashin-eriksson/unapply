"""Command-line interface: `unapply <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from unapply.estimation.claims import claim_support
from unapply.estimation.skills import estimate_skills
from unapply.ingest.documents import SourceDocument, load_path
from unapply.ingest.extract import extract_profile
from unapply.ingest.github import cached_fetcher, fetch_github
from unapply.llm import (
    DEFAULT_MODEL,
    AnthropicLLM,
    RecordingLLM,
    ReplayLLM,
    StructuredLLM,
)
from unapply.review import ReviewError, apply_review_sheet, export_review_sheet
from unapply.schemas import Profile


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
    # Secrets such as ANTHROPIC_API_KEY live in a gitignored .env in the project.
    # Variables already set in the environment take precedence.
    load_dotenv(find_dotenv(usecwd=True))
    parser = argparse.ArgumentParser(prog="unapply")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Extract a profile from material.")
    ingest.add_argument("paths", nargs="*", type=Path, help="Files or folders.")
    ingest.add_argument("--github", help="GitHub username to include.")
    ingest.add_argument(
        "--github-cache",
        type=Path,
        default=Path("data/.cache/github"),
        help="Folder caching GitHub responses; delete it to refetch.",
    )
    ingest.add_argument(
        "--out", type=Path, required=True, help="Profile JSON to write."
    )
    ingest.add_argument(
        "--dump-sources", type=Path, help="Also write the text sent to the model."
    )
    _add_model_options(ingest)

    estimate = commands.add_parser(
        "estimate", help="Estimate skill levels from evidence and check claim support."
    )
    estimate.add_argument("profile", type=Path, help="Profile JSON.")
    estimate.add_argument(
        "--out", type=Path, required=True, help="Profile JSON to write."
    )
    _add_model_options(estimate)

    review = commands.add_parser("review", help="Review and approve a profile.")
    steps = review.add_subparsers(dest="step", required=True)
    export = steps.add_parser("export", help="Write a review sheet to edit.")
    export.add_argument("profile", type=Path, help="Profile JSON.")
    export.add_argument("--sheet", type=Path, required=True, help="Sheet to write.")
    apply = steps.add_parser("apply", help="Apply an edited review sheet.")
    apply.add_argument("profile", type=Path, help="Profile JSON it was exported from.")
    apply.add_argument("sheet", type=Path, help="The edited sheet.")
    apply.add_argument("--out", type=Path, required=True, help="Profile JSON to write.")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "ingest":
        return _ingest(args)
    if args.command == "review":
        return _review(args)
    if args.command == "estimate":
        return _estimate(args)
    return 1


def _add_model_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--model", default=DEFAULT_MODEL)
    command.add_argument("--effort", default="high")
    recording = command.add_mutually_exclusive_group()
    recording.add_argument(
        "--record", type=Path, help="Save the model's answer to this file."
    )
    recording.add_argument(
        "--replay",
        type=Path,
        help="Use an answer saved with --record instead of calling the model.",
    )


def _llm(args: argparse.Namespace) -> StructuredLLM:
    if args.replay:
        return ReplayLLM(args.replay)
    llm = AnthropicLLM(args.model, args.effort)
    return RecordingLLM(llm, args.record) if args.record else llm


def _estimate(args: argparse.Namespace) -> int:
    profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8"))
    if profile.approved_by_candidate_at is None:
        print("Note: this profile isn't approved by the candidate yet.")
    result = estimate_skills(profile, _llm(args))
    support = claim_support(result.profile)
    estimated = result.profile.model_copy(update={"claim_support": support})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(estimated.model_dump_json(indent=2), encoding="utf-8")

    flags = {
        **{n: "OVERCLAIM" for n in support.overclaims},
        **{n: "underclaim" for n in support.underclaims},
        **{n: "unverified" for n in support.unverified},
        **{n: "unsupported" for n in support.unsupported_claims},
    }
    print(f"\n{'skill':<30} {'own':>3} {'est':>3} {'conf':>4}  reason")
    for s in estimated.skills:
        own = str(int(s.self_level)) if s.self_level else "-"
        if s.estimate is None:
            print(f"{s.name[:30]:<30} {own:>3}   -    -  (not estimated)")
            continue
        flag = f"[{flags[s.name]}] " if s.name in flags else ""
        print(
            f"{s.name[:30]:<30} {own:>3} {int(s.estimate.level):>3} "
            f"{s.estimate.confidence:>4.2f}  {flag}{s.estimate.rationale}"
        )
    print(f"\nclaim support: {support.score:.2f}")
    for label, names in [
        ("overclaims", support.overclaims),
        ("underclaims", support.underclaims),
        ("unverified (worth adding evidence)", support.unverified),
        ("only your own statement", support.unsupported_claims),
    ]:
        print(f"  {label}: {', '.join(names) or 'none'}")
    if result.problems:
        print(f"problems with the model's answer ({len(result.problems)}):")
        for p in result.problems:
            print(f"  {p}")
    print(f"-> {args.out}")
    return 0


def _review(args: argparse.Namespace) -> int:
    profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8"))
    if args.step == "export":
        if args.sheet.exists():
            print(f"{args.sheet} exists; not overwriting your edits.", file=sys.stderr)
            return 2
        args.sheet.write_text(export_review_sheet(profile), encoding="utf-8")
        print(f"Wrote {args.sheet}. Edit it, then run `unapply review apply`.")
        return 0
    try:
        reviewed = apply_review_sheet(profile, args.sheet.read_text(encoding="utf-8"))
    except ReviewError as e:
        print(f"Can't apply {args.sheet}: {e}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(reviewed.model_dump_json(indent=2), encoding="utf-8")
    rated = sum(s.self_level is not None for s in reviewed.skills)
    print(
        f"{len(reviewed.experiences)} experiences, {len(reviewed.skills)} skills "
        f"({rated} with your level) -> {args.out}"
    )
    print("Approved." if reviewed.approved_by_candidate_at else "Not approved yet.")
    return 0


def _ingest(args: argparse.Namespace) -> int:
    documents: list[SourceDocument] = []
    for path in args.paths:
        documents.extend(load_path(path))
    if args.github:
        fetch = cached_fetcher(args.github_cache)
        documents.append(fetch_github(args.github, fetch=fetch))
    if not documents:
        print("Nothing to ingest: give paths or --github.", file=sys.stderr)
        return 2
    for d in documents:
        print(f"source: {d.source.kind:<10} {d.name} ({len(d.text):,} chars)")
    if args.dump_sources:
        from unapply.ingest.extract import render_sources

        args.dump_sources.write_text(render_sources(documents), encoding="utf-8")

    result = extract_profile(documents, _llm(args))
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
