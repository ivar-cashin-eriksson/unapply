"""Command-line interface: `unapply <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from unapply.estimation.claims import claim_support, summary
from unapply.estimation.skills import (
    EstimationResult,
    estimate_skills,
    skills_without_estimate,
)
from unapply.ingest.documents import SourceDocument, load_path
from unapply.ingest.extract import extract_profile
from unapply.ingest.github import cached_fetcher, fetch_github
from unapply.interview.questions import MAX_QUESTIONS, select_topics, write_questions
from unapply.interview.sheet import (
    InterviewError,
    apply_interview_sheet,
    export_interview_sheet,
)
from unapply.jobs.extract import extract_job
from unapply.jobs.sheet import RubricError, apply_rubric_sheet, export_rubric_sheet
from unapply.llm import (
    API_SWITCH,
    DEFAULT_MODEL,
    QUESTION_MODEL,
    AnthropicLLM,
    APICallsDisabled,
    RecordingLLM,
    ReplayLLM,
    StructuredLLM,
)
from unapply.review import ReviewError, apply_review_sheet, export_review_sheet
from unapply.schemas import CriterionKind, Job, Profile


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
    estimate.add_argument(
        "--all",
        action="store_true",
        help="Re-estimate every skill, not only those without an estimate.",
    )
    _add_model_options(estimate)

    interview = commands.add_parser(
        "interview", help="Ask about skills the documents don't show enough of."
    )
    rounds = interview.add_subparsers(dest="step", required=True)
    ask = rounds.add_parser("export", help="Write questions to answer.")
    ask.add_argument("profile", type=Path, help="Estimated profile JSON.")
    ask.add_argument("--sheet", type=Path, required=True, help="Sheet to write.")
    ask.add_argument("--max-questions", type=int, default=MAX_QUESTIONS)
    # Writing questions is a light task, so a cheaper model by default.
    _add_model_options(ask, model=QUESTION_MODEL, effort="medium")
    answer = rounds.add_parser("apply", help="Add the answers to the profile.")
    answer.add_argument("profile", type=Path, help="Profile JSON it was exported from.")
    answer.add_argument("sheet", type=Path, help="The answered sheet.")
    answer.add_argument(
        "--out", type=Path, required=True, help="Profile JSON to write."
    )

    job = commands.add_parser("job", help="Turn a job ad into a rubric and review it.")
    job_steps = job.add_subparsers(dest="step", required=True)
    job_extract = job_steps.add_parser("extract", help="Extract a rubric from an ad.")
    job_extract.add_argument("ad", type=Path, help="The job ad: text, Markdown or PDF.")
    job_extract.add_argument(
        "--out", type=Path, required=True, help="Job JSON to write."
    )
    job_extract.add_argument("--company", help="Company name, if not in the ad.")
    job_extract.add_argument("--title", help="Job title, if not in the ad.")
    _add_model_options(job_extract)
    job_export = job_steps.add_parser("export", help="Write a rubric sheet to edit.")
    job_export.add_argument("job", type=Path, help="Job JSON.")
    job_export.add_argument("--sheet", type=Path, required=True, help="Sheet to write.")
    job_apply = job_steps.add_parser("apply", help="Apply an edited rubric sheet.")
    job_apply.add_argument("job", type=Path, help="Job JSON it was exported from.")
    job_apply.add_argument("sheet", type=Path, help="The edited sheet.")
    job_apply.add_argument("--out", type=Path, required=True, help="Job JSON to write.")

    db = commands.add_parser("db", help="Create the database and import workspaces.")
    db_steps = db.add_subparsers(dest="step", required=True)
    db_init = db_steps.add_parser(
        "init", help="Create the tables, or migrate them to the newest version."
    )
    db_import = db_steps.add_parser(
        "import", help="Import candidate or job workspace folders."
    )
    db_import.add_argument(
        "workspaces", nargs="+", type=Path, help="Workspace folders, such as data/me."
    )
    for command in (db_init, db_import):
        command.add_argument(
            "--url", help="SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite."
        )

    app = commands.add_parser("app", help="Open the app in a browser.")
    app.add_argument("--port", type=int, default=8501)

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
    try:
        return _run(args)
    except APICallsDisabled as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 3


def _run(args: argparse.Namespace) -> int:
    if args.command == "job":
        return _job(args)
    if args.command == "app":
        return _app(args)
    if args.command == "db":
        return _db(args)
    if args.command == "ingest":
        return _ingest(args)
    if args.command == "review":
        return _review(args)
    if args.command == "estimate":
        return _estimate(args)
    if args.command == "interview":
        return _interview(args)
    return 1


def _interview(args: argparse.Namespace) -> int:
    profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8"))
    if args.step == "export":
        if args.sheet.exists():
            print(
                f"{args.sheet} exists; not overwriting your answers.", file=sys.stderr
            )
            return 2
        try:
            topics = select_topics(profile, args.max_questions)
        except ValueError as e:
            print(f"Can't write questions: {e}", file=sys.stderr)
            return 2
        if not topics:
            print(
                "Nothing to ask: every rated skill is supported or already asked about."
            )
            return 0
        questions = write_questions(profile, topics, _llm(args))
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        args.sheet.write_text(
            export_interview_sheet(profile, questions), encoding="utf-8"
        )
        for q in questions:
            print(f"[{q.reason}] {q.skill}: {q.text}")
        print()
        print(
            f"Wrote {len(questions)} questions to {args.sheet}. Answer them, then run"
        )
        print("`unapply interview apply`, then `unapply estimate` again.")
        return 0
    try:
        updated, n = apply_interview_sheet(
            profile, args.sheet.read_text(encoding="utf-8")
        )
    except InterviewError as e:
        print(f"Can't apply {args.sheet}: {e}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    print(f"{n} answers added -> {args.out}")
    if n:
        print("Run `unapply estimate` on it to update the estimates.")
    return 0


def _job(args: argparse.Namespace) -> int:
    if args.step == "extract":
        llm = _llm(args)  # Before reading anything, so a refused call costs no time.
        documents = load_path(args.ad)
        if len(documents) != 1:
            print(f"Expected one job ad file, got {len(documents)}.", file=sys.stderr)
            return 2
        result = extract_job(
            documents[0].text, llm, company=args.company, title=args.title
        )
        _write(args.out, result.job.model_dump_json(indent=2))
        rubric = result.job.rubric
        musts = sum(c.kind == CriterionKind.MUST_HAVE for c in rubric.criteria)
        print(f"{result.job.title} at {result.job.company}")
        print(f"hard filters: {rubric.hard_filters.model_dump(exclude_defaults=True)}")
        print(
            f"{musts} must-haves, {len(rubric.criteria) - musts} nice-to-haves "
            f"-> {args.out}"
        )
        for c in rubric.criteria:
            print(f"  [{c.kind.value}] weight {c.weight:g}: {c.description}")
        if result.dropped:
            print(f"dropped ({len(result.dropped)}):")
            for d in result.dropped:
                print(f"  {d}")
        return 0
    job = Job.model_validate_json(args.job.read_text(encoding="utf-8"))
    if args.step == "export":
        if args.sheet.exists():
            print(f"{args.sheet} exists; not overwriting your edits.", file=sys.stderr)
            return 2
        _write(args.sheet, export_rubric_sheet(job))
        print(f"Wrote {args.sheet}. Edit it, then run `unapply job apply`.")
        return 0
    try:
        updated = apply_rubric_sheet(job, args.sheet.read_text(encoding="utf-8"))
    except RubricError as e:
        print(f"Can't apply {args.sheet}: {e}", file=sys.stderr)
        return 2
    _write(args.out, updated.model_dump_json(indent=2))
    r = updated.rubric
    print(f"rubric version {r.version}: {len(r.criteria)} criteria -> {args.out}")
    print("Approved." if r.approved_at else "Not approved yet.")
    return 0


def _db(args: argparse.Namespace) -> int:
    # Imported here, so commands that don't use the database don't load SQLAlchemy.
    from unapply.db.engine import init_db
    from unapply.db.importer import import_workspace
    from unapply.db.repository import Repository

    url = init_db(args.url)
    if args.step == "init":
        print(f"Database ready: {url}")
        return 0
    repo = Repository.from_url(args.url)
    failed = 0
    for path in args.workspaces:
        try:
            kind = import_workspace(repo, path)
        except ValueError as e:
            print(f"Not imported: {path}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"Imported {kind} {path.name!r} from {path}")
    repo.engine.dispose()
    return 2 if failed else 0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _app(args: argparse.Namespace) -> int:
    import subprocess

    script = Path(__file__).parent / "app" / "main.py"
    command = [sys.executable, "-m", "streamlit", "run", str(script)]
    command += ["--server.port", str(args.port), "--browser.gatherUsageStats", "false"]
    return subprocess.call(command)


def _add_model_options(
    command: argparse.ArgumentParser,
    model: str = DEFAULT_MODEL,
    effort: str = "high",
) -> None:
    command.add_argument("--model", default=model)
    command.add_argument("--effort", default=effort)
    recording = command.add_mutually_exclusive_group()
    recording.add_argument(
        "--record", type=Path, help="Save the model's answer to this file."
    )
    recording.add_argument(
        "--replay",
        type=Path,
        help="Use an answer saved with --record instead of calling the model.",
    )
    command.add_argument(
        "--allow-api",
        action="store_true",
        help=f"Allow this command to make paid API calls (otherwise {API_SWITCH}=1).",
    )


def _llm(args: argparse.Namespace) -> StructuredLLM:
    """Pick the model client; refuse up front if a paid call isn't allowed."""
    if args.replay:
        return ReplayLLM(args.replay)
    llm = AnthropicLLM(args.model, args.effort, allow=args.allow_api)
    if not llm.allowed:
        raise APICallsDisabled(
            "this would make a paid API call, which is off. Add --allow-api to allow "
            f"it for this command, set {API_SWITCH}=1 in .env, or use --replay."
        )
    return RecordingLLM(llm, args.record) if args.record else llm


def _estimate(args: argparse.Namespace) -> int:
    profile = Profile.model_validate_json(args.profile.read_text(encoding="utf-8"))
    if profile.approved_by_candidate_at is None:
        print("Note: this profile isn't approved by the candidate yet.")
    names = None if args.all else skills_without_estimate(profile)
    if names is not None and not names:
        print("Every skill already has an estimate; use --all to redo them.")
    else:
        if names is not None and len(names) < len(profile.skills):
            print(
                f"Estimating {len(names)} skills without an estimate: {sorted(names)}"
            )
    result = (
        estimate_skills(profile, _llm(args), names)
        if names is None or names
        else EstimationResult(profile=profile)
    )
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
    print(f"\nclaim support: {summary(support)}")
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
    llm = _llm(args)  # Before any loading, so a refused call costs no time.
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

    result = extract_profile(documents, llm)
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
