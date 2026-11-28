"""Command-line interface: `unapply <command>`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import find_dotenv, load_dotenv

from unapply.consent import ConsentSection
from unapply.estimation.claims import claim_support, summary
from unapply.estimation.skills import (
    EstimationResult,
    estimate_skills,
    skills_without_estimate,
)
from unapply.ingest.documents import SkippedFile, SourceDocument, load_path
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

if TYPE_CHECKING:
    from unapply.evaluation import Agreement, ReferenceEntry
    from unapply.matching import Ranked


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
    ingest.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Leave out files in the folders that match, such as 'old_cv.pdf' or "
        "'drafts/*'. Can be given more than once. README files and schemas are "
        "always left out of folders.",
    )
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
        "init",
        help="Create the tables, or migrate them to the newest version, and load "
        "the skill taxonomy.",
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

    match = commands.add_parser(
        "match",
        help="Match the candidates connected to a job, save and rank them.",
    )
    match.add_argument("job", help="The job's name in the database.")
    match.add_argument(
        "--candidates",
        nargs="+",
        help="Only these connected candidates; by default all with an approved "
        "profile.",
    )
    match.add_argument(
        "--scorer",
        choices=["baseline", "llm"],
        default="baseline",
        help="baseline: plain code, free (default). llm: one model call per candidate.",
    )
    match.add_argument(
        "--today",
        type=date.fromisoformat,
        help="Date current roles run to, for years of experience (YYYY-MM-DD).",
    )
    match.add_argument(
        "--url", help="SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite."
    )
    _add_model_options(match)
    match.epilog = (
        "With --scorer llm, --record and --replay take a folder with one "
        "<candidate>.json per candidate, or a file for a single candidate."
    )

    audit = commands.add_parser(
        "audit",
        help="List a job's rankings from the audit log and check each reproduces.",
    )
    audit.add_argument("job", help="The job's name in the database.")
    audit.add_argument(
        "--url", help="SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite."
    )

    consent = commands.add_parser(
        "consent",
        help="Opt a candidate in to a job, choosing what its agent may read over MCP.",
    )
    consent_steps = consent.add_subparsers(dest="step", required=True)
    grant = consent_steps.add_parser(
        "grant", help="Opt a candidate in to a job, or change what they share."
    )
    grant.add_argument("candidate", help="The candidate's name in the database.")
    grant.add_argument("job", help="The job's name in the database.")
    grant.add_argument(
        "--sections",
        nargs="*",
        choices=[s.value for s in ConsentSection],
        help="What the job's agent may read; by default everything.",
    )
    withdraw = consent_steps.add_parser(
        "withdraw", help="Opt a candidate out of a job."
    )
    withdraw.add_argument("candidate", help="The candidate's name in the database.")
    withdraw.add_argument("job", help="The job's name in the database.")
    consents = consent_steps.add_parser(
        "list", help="List the candidates who opted in to a job."
    )
    consents.add_argument("job", help="The job's name in the database.")
    for command in (grant, withdraw, consents):
        command.add_argument(
            "--url", help="SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite."
        )

    mcp = commands.add_parser(
        "mcp",
        help="Serve a job's matching agent over MCP (stdio): the candidates who "
        "opted in, anonymised, and only what each shared.",
    )
    mcp.add_argument("job", help="The job's name in the database.")
    mcp.add_argument(
        "--url", help="SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite."
    )

    ask_pool = commands.add_parser(
        "ask",
        help="Ask a demo question about a candidate of the synthetic pool, as an "
        "employer does once they reveal them, to record its answer.",
    )
    ask_pool.add_argument(
        "candidate", help="The candidate's folder in the pool, such as astrid-holm."
    )
    ask_pool.add_argument(
        "question", help="A question's id in the pool's questions.yaml, or any text."
    )
    _add_model_options(ask_pool)

    evaluate = commands.add_parser(
        "evaluate",
        help="Rank a synthetic candidate pool with each scorer and compare the "
        "rankings with a reference: top-k overlap and Kendall's tau. With --job, "
        "compare a job's ranking from the audit log instead.",
    )
    evaluate.add_argument(
        "pool",
        type=Path,
        nargs="?",
        help="Pool folder with a pool.yaml, by default tests/fixtures/pool.",
    )
    evaluate.add_argument(
        "--reference",
        type=Path,
        action="append",
        help="YAML ranking to compare with (see docs), by default the pool's "
        "intended ranking. Give it more than once, such as one per person who "
        "hires, to compare with each, and to see how much the references agree "
        "with each other: the ceiling.",
    )
    evaluate.add_argument(
        "--scorer",
        nargs="+",
        choices=["baseline", "llm"],
        help="Scorers to evaluate, by default both. llm replays recorded answers.",
    )
    evaluate.add_argument(
        "--job",
        help="Instead of a pool: a job's name in the database. Its latest ranking "
        "in the audit log, as its employer saw it, is compared with --reference, "
        "which names candidates as in the database. Nothing is scored again.",
    )
    evaluate.add_argument(
        "--ranking",
        type=int,
        help="With --job: the ranking's id in the audit log (see unapply audit), "
        "by default the latest.",
    )
    evaluate.add_argument(
        "--url",
        help="With --job: SQLAlchemy URL, by default $UNAPPLY_DATABASE_URL or SQLite.",
    )
    evaluate.add_argument(
        "--k",
        nargs="+",
        type=int,
        default=[3, 5],
        help="Top-k overlaps to report, by default 3 and 5.",
    )
    evaluate.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Also list each scorer's problems, such as criteria it can't score.",
    )
    evaluate.add_argument(
        "--record",
        action="store_true",
        help="Call the model instead of replaying, and record its answers in the "
        "pool, overwriting the recordings: extraction, estimation and (with the llm "
        "scorer) scores. Paid; needs --allow-api.",
    )
    evaluate.add_argument("--model", default=DEFAULT_MODEL)
    evaluate.add_argument("--effort", default="high")
    evaluate.add_argument(
        "--allow-api",
        action="store_true",
        help=f"Allow paid API calls for --record (otherwise {API_SWITCH}=1).",
    )

    app = commands.add_parser("app", help="Open the app in a browser.")
    app.add_argument("--port", type=int, default=8501)

    api = commands.add_parser(
        "api", help="Start the HTTP API over the database (docs at /docs)."
    )
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument(
        "--internal",
        action="store_true",
        help="Add the internal assessment routes. Never for a server candidates use.",
    )

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
    if args.command == "api":
        return _api(args)
    if args.command == "db":
        return _db(args)
    if args.command == "match":
        return _match(args)
    if args.command == "audit":
        return _audit(args)
    if args.command == "consent":
        return _consent(args)
    if args.command == "mcp":
        return _mcp(args)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "ask":
        return _ask(args)
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
    repo = Repository.from_url(args.url)
    if args.step == "init":
        from unapply.taxonomy import default_taxonomy, taxonomy_path

        taxonomy = default_taxonomy()
        repo.save_taxonomy(taxonomy)
        repo.engine.dispose()
        print(f"Database ready: {url}")
        print(
            f"Skill taxonomy loaded: {len(taxonomy.skills)} skills from {taxonomy_path()}"
        )
        return 0
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


def _match(args: argparse.Namespace) -> int:
    # Imported here, so commands that don't use the database don't load SQLAlchemy.
    from unapply.db.engine import init_db
    from unapply.db.repository import NotFound, Repository
    from unapply.matching import BaselineScorer, LLMScorer, Scorer
    from unapply.matching.run import MatchingError, match_job

    if args.scorer == "baseline" and (args.record or args.replay or args.allow_api):
        print(
            "Note: the baseline scorer calls no model; --record, --replay and "
            "--allow-api are ignored."
        )
    # Before anything else, so a refused paid call costs no time.
    llm = _paid_llm(args) if args.scorer == "llm" and not args.replay else None
    recorded: list[str] = []

    def scorer_for(name: str, settings: dict) -> Scorer:
        if args.scorer == "baseline":
            return BaselineScorer()
        names = [settings["github"]] if settings.get("github") else []
        if args.replay:
            path = args.replay / f"{name}.json" if args.replay.is_dir() else args.replay
            if not path.is_file():
                raise MatchingError(f"no recorded answer for {name!r} at {path}")
            return LLMScorer(ReplayLLM(path), names)
        assert llm is not None  # Made above whenever nothing is replayed.
        if args.record:
            recorded.append(name)
            single = args.record.suffix == ".json"
            if single and len(recorded) > 1:
                raise MatchingError(
                    "--record FILE fits one candidate; give a folder to record several"
                )
            path = args.record if single else args.record / f"{name}.json"
            return LLMScorer(RecordingLLM(llm, path), names)
        return LLMScorer(llm, names)

    init_db(args.url)
    repo = Repository.from_url(args.url)
    try:
        matching = match_job(
            repo, args.job, scorer_for, candidates=args.candidates, today=args.today
        )
    except (NotFound, MatchingError) as e:
        print(f"Can't match: {e}", file=sys.stderr)
        return 2
    finally:
        repo.engine.dispose()

    job = matching.job
    criteria = {c.id: c for c in job.rubric.criteria}
    scorers = sorted({r.match.model for r in matching.results.values()})
    print(
        f"{job.title} at {job.company}, rubric version {job.rubric.version}: "
        f"{len(matching.results)} candidates, scored by {', '.join(scorers) or '-'}"
    )
    for ranked in matching.ranking:
        name = matching.name_of(ranked)
        result = matching.results[name]
        status = "" if ranked.match.passed_hard_filters else "  (failed hard filters)"
        print()
        print(f"#{ranked.rank}  {name}  total {ranked.total:.2f}{status}")
        for check in result.filters.checks:
            print(f"  [{check.outcome.value}] {check.name}: {check.reason}")
        for s in ranked.match.criterion_scores:
            c = criteria[s.criterion_id]
            print(f"  {s.score:.2f}  {c.kind.value} w{c.weight:g}  {c.description}")
            print(f"        {s.rationale}")
        if result.problems:
            print(f"  problems ({len(result.problems)}):")
            for p in result.problems:
                print(f"    {p}")
    if not matching.results:
        print("No connected candidate has an approved profile yet.")
    return 0


def _audit(args: argparse.Namespace) -> int:
    from unapply.db.engine import init_db
    from unapply.db.repository import NotFound, Repository
    from unapply.matching.audit import AuditKind, check_ranking

    init_db(args.url)
    repo = Repository.from_url(args.url)
    try:
        try:
            job = repo.job(args.job)
        except NotFound as e:
            print(f"Can't audit: {e}", file=sys.stderr)
            return 2
        if job is None:
            print(
                f"No job {args.job!r} with a rubric in the database.", file=sys.stderr
            )
            return 2
        log = repo.audit_log(job.id)
    finally:
        repo.engine.dispose()
    rankings = [e for e in log if e.kind is AuditKind.RANKING]
    matches = len(log) - len(rankings)
    print(
        f"{job.title} at {job.company}: {len(rankings)} rankings and {matches} "
        "matches in the audit log"
    )
    failed = 0
    for entry in rankings:
        problems = check_ranking(entry, log)
        failed += bool(problems)
        print(
            f"#{entry.id}  {entry.recorded_at:%Y-%m-%d %H:%M:%S}  rubric version "
            f"{entry.rubric_version}  {entry.scorer} ({entry.model})  "
            f"{len(entry.payload['ranking'])} candidates  "
            f"{'NOT REPRODUCED' if problems else 'reproduced'}"
        )
        for p in problems:
            print(f"    {p}")
    return 1 if failed else 0


def _consent(args: argparse.Namespace) -> int:
    from unapply.db.engine import init_db
    from unapply.db.repository import NotFound, Repository

    init_db(args.url)
    repo = Repository.from_url(args.url)
    try:
        if args.step == "grant":
            sections = (
                None
                if args.sections is None
                else [ConsentSection(s) for s in args.sections]
            )
            consent = repo.grant_consent(args.candidate, args.job, sections)
            print(
                f"{args.candidate} opted in to {args.job}, sharing "
                f"{', '.join(consent.sections) or 'nothing yet'}."
            )
        elif args.step == "withdraw":
            if repo.withdraw_consent(args.candidate, args.job):
                print(f"{args.candidate} opted out of {args.job}.")
            else:
                print(f"{args.candidate} hadn't opted in to {args.job}.")
        else:
            found = repo.consents(args.job)
            print(f"{len(found)} candidates opted in to {args.job}")
            for c in found:
                print(
                    f"  {c.candidate}  {c.granted_at:%Y-%m-%d %H:%M}  "
                    f"{', '.join(c.sections) or 'nothing yet'}"
                )
    except NotFound as e:
        print(f"Can't change consent: {e}", file=sys.stderr)
        return 2
    finally:
        repo.engine.dispose()
    return 0


def _mcp(args: argparse.Namespace) -> int:
    from unapply.db.engine import init_db
    from unapply.db.repository import NotFound, Repository
    from unapply.mcp_server import build_server

    init_db(args.url)
    repo = Repository.from_url(args.url)
    try:
        server = build_server(repo, args.job)
    except NotFound as e:
        repo.engine.dispose()
        print(f"Can't serve: {e}", file=sys.stderr)
        return 2
    # Stdout carries the protocol, so everything else goes to stderr (logging
    # does by default).
    try:
        server.run("stdio")
    finally:
        repo.engine.dispose()
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    from unapply.evaluation import (
        DEFAULT_POOL,
        compare_ranking,
        evaluate_pool,
        load_pool,
        load_reference,
        rater_agreement,
    )
    from unapply.evaluation.pool import LLMFor

    if any(k < 1 for k in args.k):
        print("--k must be 1 or more", file=sys.stderr)
        return 2
    if args.job is not None:
        return _evaluate_job(args)
    if args.ranking is not None or args.url is not None:
        print("--ranking and --url need --job", file=sys.stderr)
        return 2
    llm_for: LLMFor = ReplayLLM
    if args.record:
        # Before anything else, so a refused paid call costs no time.
        llm = _paid_llm(args)

        def llm_for(path: Path) -> StructuredLLM:
            return RecordingLLM(llm, path)

    folder = args.pool or DEFAULT_POOL
    paths: list[Path] = args.reference or []
    ks = tuple(args.k)
    try:
        pool = load_pool(folder, llm_for)
        references = [load_reference(p) for p in paths] or [pool.intended]
        agreement = rater_agreement(references, ks) if len(references) > 1 else None
    except (FileNotFoundError, ValueError) as e:
        print(f"Can't evaluate: {e}", file=sys.stderr)
        return 2
    job = pool.job
    print(
        f"{job.title} at {job.company}, rubric version {job.rubric.version}: "
        f"{len(pool.candidates)} candidates in {folder}, roles counted to "
        f"{pool.today:%Y-%m-%d}"
    )
    if not paths:
        print("Reference: the pool's intended ranking")
    _print_references(paths, agreement)
    for name, candidate in pool.candidates.items():
        for p in candidate.problems:
            print(f"  problem: {name}: {p}")
    for kind in dict.fromkeys(args.scorer or ["baseline", "llm"]):
        try:
            evaluation = evaluate_pool(pool, kind, references[0], ks, llm_for)
            ranks = {n: r.rank for n, r in evaluation.ranking}
            order = [n for n, _ in evaluation.ranking]
            comparisons = [(evaluation.top_k, evaluation.tau)] + [
                compare_ranking(ranks, order, r, ks) for r in references[1:]
            ]
        except ValueError as e:
            print(f"Can't evaluate {kind}: {e}", file=sys.stderr)
            return 2
        print()
        print(f"{kind} ({evaluation.model})")
        _print_evaluated(evaluation.ranking, references, comparisons)
        if args.verbose:
            for name, result in evaluation.results.items():
                for p in result.problems:
                    print(f"  problem: {name}: {p}")
    return 0


def _evaluate_job(args: argparse.Namespace) -> int:
    """`unapply evaluate --job`: compare a job's ranking from the audit log."""
    from unapply.db.engine import init_db
    from unapply.db.repository import NotFound, Repository
    from unapply.evaluation import (
        compare_ranking,
        load_reference,
        rater_agreement,
        stored_ranking,
    )

    given = [
        option
        for option, value in (
            ("a pool", args.pool),
            ("--scorer", args.scorer),
            ("--record", args.record),
            ("--verbose", args.verbose),
        )
        if value
    ]
    if given:
        print(
            f"--job compares a stored ranking; it takes no {', '.join(given)}",
            file=sys.stderr,
        )
        return 2
    paths: list[Path] = args.reference or []
    if not paths:
        print("--job needs at least one --reference", file=sys.stderr)
        return 2
    ks = tuple(args.k)
    try:
        references = [load_reference(p) for p in paths]
        agreement = rater_agreement(references, ks) if len(references) > 1 else None
    except (FileNotFoundError, ValueError) as e:
        print(f"Can't evaluate: {e}", file=sys.stderr)
        return 2
    init_db(args.url)
    repo = Repository.from_url(args.url)
    try:
        job = repo.job(args.job)
        stored = stored_ranking(repo, args.job, args.ranking)
    except (NotFound, ValueError) as e:
        print(f"Can't evaluate: {e}", file=sys.stderr)
        return 2
    finally:
        repo.engine.dispose()
    assert job is not None  # stored_ranking refuses a job without a rubric.
    ranks = {n: r.rank for n, r in stored.ranking}
    order = [n for n, _ in stored.ranking]
    try:
        comparisons = [compare_ranking(ranks, order, r, ks) for r in references]
    except ValueError as e:
        print(f"Can't evaluate: {e}", file=sys.stderr)
        return 2
    print(
        f"{job.title} at {job.company}: ranking #{stored.entry_id} of "
        f"{stored.recorded_at:%Y-%m-%d %H:%M:%S}, rubric version "
        f"{stored.rubric_version}, {len(stored.ranking)} candidates"
    )
    _print_references(paths, agreement)
    print()
    print(f"{stored.scorer} ({stored.model})")
    _print_evaluated(stored.ranking, references, comparisons)
    return 0


def _print_references(paths: list[Path], agreement: Agreement | None) -> None:
    """Print the reference files and, for several, how much they agree."""
    if len(paths) == 1:
        print(f"Reference: {paths[0]}")
    elif paths:
        print("References:")
        for i, p in enumerate(paths, 1):
            print(f"  {i}: {p}")
    if agreement is not None:
        print(
            "Agreement between the references (the ceiling, "
            f"{agreement.pairs} pair{'s' if agreement.pairs > 1 else ''}): "
            f"{_comparison(agreement.top_k, agreement.tau)}"
        )


def _print_evaluated(
    ranking: list[tuple[str, Ranked]],
    references: list[list[ReferenceEntry]],
    comparisons: list[tuple[dict[int, float], float | None]],
) -> None:
    """Print a ranking beside each reference's ranks, and how it compares."""
    from unapply.evaluation import mean_comparison

    wanted = [{e.candidate: e.rank for e in r} for r in references]
    headers = (
        ["reference"]
        if len(references) == 1
        else [f"ref {i}" for i in range(1, len(references) + 1)]
    )
    print("  rank  total  " + "  ".join(headers) + "  candidate")
    for name, ranked in ranking:
        status = "" if ranked.match.passed_hard_filters else "  (failed hard filters)"
        refs = "  ".join(
            f"{w.get(name, '-')!s:>{len(h)}}"
            for w, h in zip(wanted, headers, strict=True)
        )
        print(f"  {ranked.rank:>4}  {ranked.total:5.2f}  {refs}  {name}{status}")
    if len(comparisons) == 1:
        print(f"  {_comparison(*comparisons[0])}")
    else:
        for i, c in enumerate(comparisons, 1):
            print(f"  ref {i}: {_comparison(*c)}")
        print(f"  mean: {_comparison(*mean_comparison(comparisons))}")


def _comparison(top_k: dict[int, float], tau: float | None) -> str:
    """Format top-k overlaps and Kendall's tau on one line."""
    overlaps = "  ".join(f"top-{k} overlap {v:.2f}" for k, v in top_k.items())
    return f"{overlaps}  Kendall's tau {'-' if tau is None else f'{tau:.2f}'}"


def _ask(args: argparse.Namespace) -> int:
    import yaml

    from unapply.evaluation import load_pool
    from unapply.jobs.ask import DEMO_QUESTIONS, ask_candidate, check_question

    # Before anything else, so a refused paid call costs no time.
    llm = _llm(args)
    spec = yaml.safe_load(DEMO_QUESTIONS.read_text(encoding="utf-8")) or {}
    texts = {q["id"]: q["text"] for q in spec.get("questions", [])}
    question = check_question(texts.get(args.question, args.question), [])
    pool = load_pool()
    if args.candidate not in pool.candidates:
        print(f"No candidate {args.candidate!r} in the pool.", file=sys.stderr)
        return 2
    answer = ask_candidate(pool.candidates[args.candidate].profile, question, llm)
    print(f"Q: {answer.question}")
    print(f"A: {answer.answer}")
    print(f"Answered by the material: {'yes' if answer.answered else 'no'}")
    for quote in answer.evidence:
        print(f"  [{quote.source}] {quote.quote}")
    for problem in answer.problems:
        print(f"  problem: {problem}")
    return 0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _app(args: argparse.Namespace) -> int:
    import subprocess

    script = Path(__file__).parent / "app" / "main.py"
    command = [sys.executable, "-m", "streamlit", "run", str(script)]
    command += ["--server.port", str(args.port), "--browser.gatherUsageStats", "false"]
    return subprocess.call(command)


def _api(args: argparse.Namespace) -> int:
    # Imported here, so other commands don't load FastAPI.
    import uvicorn

    from unapply.api import create_app

    uvicorn.run(
        create_app(internal_routes=args.internal), host=args.host, port=args.port
    )
    return 0


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
    llm = _paid_llm(args)
    return RecordingLLM(llm, args.record) if args.record else llm


def _paid_llm(args: argparse.Namespace) -> AnthropicLLM:
    """Make the Claude client; refuse up front if paid calls aren't allowed."""
    llm = AnthropicLLM(args.model, args.effort, allow=args.allow_api)
    if not llm.allowed:
        raise APICallsDisabled(
            "this would make a paid API call, which is off. Add --allow-api to allow "
            f"it for this command, set {API_SWITCH}=1 in .env, or use --replay."
        )
    return llm


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
    skipped: list[SkippedFile] = []
    for path in args.paths:
        documents.extend(load_path(path, exclude=args.exclude, skipped=skipped))
    for f in skipped:
        print(f"skipped: {f.path.as_posix()} ({f.reason})")
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
