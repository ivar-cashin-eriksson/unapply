"""A pool of synthetic candidates for one job, and evaluating scorers on it.

A pool is a folder with a `pool.yaml` and one folder per candidate::

    pool.yaml                  the job, the date to match on, the intended ranking
    <candidate>/material/      the candidate's CV
    <candidate>/extraction.json    recorded extraction of the material
    <candidate>/review.yaml        the candidate's review edits (own levels)
    <candidate>/estimation.json    recorded estimate of the reviewed profile
    <candidate>/<match file>       recorded LLM scorer answer for the job

Loading a pool replays each candidate's journey: extract, review and approve,
estimate. The job's rubric is extracted from its recording and approved. Nothing
is stored in the database, so evaluating a pool changes nothing. `store_pool` puts a
loaded pool in the database as a demo, for the employer's shortlist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4

import yaml
from pydantic import BaseModel

from unapply.app.demo import FIXTURES, edit_review_sheet
from unapply.estimation.claims import claim_support
from unapply.estimation.skills import estimate_skills, skills_without_estimate
from unapply.evaluation.metrics import (
    ReferenceEntry,
    kendall_tau,
    parse_reference,
    top_k_overlap,
)
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.jobs.extract import extract_job
from unapply.jobs.sheet import apply_rubric_sheet, export_rubric_sheet
from unapply.llm import LLMError, ReplayLLM, StructuredLLM
from unapply.matching import (
    BaselineScorer,
    LLMScorer,
    MatchResult,
    Ranked,
    Scorer,
    match_candidate,
    rank,
)
from unapply.review import apply_review_sheet, export_review_sheet
from unapply.schemas import Job, Profile

if TYPE_CHECKING:
    from unapply.db.repository import Repository

T = TypeVar("T", bound=BaseModel)

# The synthetic pool for Fjord Grocery, in a checkout of the repo.
DEFAULT_POOL = FIXTURES / "pool"
# The top-k overlaps reported by default.
DEFAULT_KS = (3, 5)
SCORERS = ("baseline", "llm")
# Pool candidates stored as demos are named with this in front of their folder name.
DEMO_PREFIX = "pool-"

# Makes the model for one recorded step, given the recording's path: a replay of
# it by default, or a real model that records its answer there.
LLMFor = Callable[[Path], StructuredLLM]


@dataclass
class PoolCandidate:
    """A candidate in a pool, with their approved, estimated profile.

    Parameters
    ----------
    name : str
        The candidate's folder name, such as "astrid-holm".
    folder : Path
        Their folder in the pool.
    profile : Profile
        Extracted, reviewed and approved, and estimated.
    problems : list of str
        Anything that didn't fit on the way: quotes not found in the CV, skills or
        experiences dropped, review edits for skills that weren't extracted, and
        estimation problems. Empty for a consistent fixture.
    """

    name: str
    folder: Path
    profile: Profile
    problems: list[str] = field(default_factory=list)


@dataclass
class Pool:
    """A job and its synthetic candidates, with the intended ranking.

    Parameters
    ----------
    folder : Path
        The pool folder.
    job : Job
        The job, with its rubric approved.
    today : date
        The date current roles run to, so years of experience don't change over
        time.
    candidates : dict of str to PoolCandidate
        By name, sorted.
    intended : list of ReferenceEntry
        The ranking the pool was written to have, best first.
    match_file : str
        File name of each candidate's recorded LLM scorer answer.
    """

    folder: Path
    job: Job
    today: date
    candidates: dict[str, PoolCandidate]
    intended: list[ReferenceEntry]
    match_file: str

    def match_recording(self, name: str) -> Path:
        """Where a candidate's recorded LLM scorer answer is.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        Path
            The file.
        """
        return self.folder / name / self.match_file


@dataclass
class Evaluation:
    """One scorer's ranking of a pool, compared with a reference ranking.

    Parameters
    ----------
    scorer : str
        "baseline" or "llm".
    model : str
        Model or method that scored, as recorded on the matches.
    results : dict of str to MatchResult
        Each candidate's match, by name.
    ranking : list of tuple of (str, Ranked)
        Candidate name and place, best first.
    top_k : dict of int to float
        Top-k overlap with the reference, by k.
    tau : float or None
        Kendall's tau-b with the reference; None if it can't be computed.
    """

    scorer: str
    model: str
    results: dict[str, MatchResult]
    ranking: list[tuple[str, Ranked]]
    top_k: dict[int, float]
    tau: float | None


class _NoAnswer:
    """Stands in for a model when a candidate has no recorded answer."""

    model = "replay:none"

    def __init__(self, path: Path) -> None:
        self.path = path

    def parse(self, *, system: str, prompt: str, output_type: type[T]) -> T:
        raise LLMError(f"no recorded answer at {self.path}")


def load_pool(folder: Path = DEFAULT_POOL, llm_for: LLMFor = ReplayLLM) -> Pool:
    """Load a pool: replay every candidate's journey and approve the job's rubric.

    Parameters
    ----------
    folder : Path, optional
        The pool folder, by default the Fjord Grocery pool in `tests/fixtures/pool`.
    llm_for : callable, optional
        Makes the model for each candidate's extraction and estimation from the
        recording's path; by default it replays the recording. The job's rubric is
        always replayed: it has its own recording command.

    Returns
    -------
    Pool
        The job and the candidates, each with an approved, estimated profile.

    Raises
    ------
    FileNotFoundError
        If `pool.yaml`, the job or a candidate's files are missing.
    ValueError
        If `pool.yaml` or the intended ranking is invalid, or the intended ranking
        names a candidate without a folder.
    """
    spec = yaml.safe_load((folder / "pool.yaml").read_text(encoding="utf-8")) or {}
    for key in ("job", "today", "intended"):
        if key not in spec:
            raise ValueError(f"{folder / 'pool.yaml'}: `{key}` is missing")
    intended = parse_reference(spec["intended"], str(folder / "pool.yaml"))
    job = _approved_job(folder / spec["job"])
    names = [e.candidate for e in intended]
    missing = [n for n in names if not (folder / n / "material").is_dir()]
    if missing:
        raise ValueError(f"no candidate folder for: {', '.join(missing)}")
    candidates = {n: _candidate(folder / n, llm_for) for n in sorted(names)}
    today = spec["today"]
    if not isinstance(today, date):
        today = date.fromisoformat(str(today))
    return Pool(
        folder=folder,
        job=job,
        today=today,
        candidates=candidates,
        intended=intended,
        match_file=spec.get("match_file", "match.json"),
    )


def _approved_job(folder: Path) -> Job:
    ad = (folder / "ad.md").read_text(encoding="utf-8")
    job = extract_job(ad, ReplayLLM(folder / "extraction.json")).job
    sheet = export_rubric_sheet(job).replace("approve: false", "approve: true")
    return apply_rubric_sheet(job, sheet)


def _candidate(folder: Path, llm_for: LLMFor) -> PoolCandidate:
    """Replay one candidate's journey: extract, review and approve, estimate."""
    extracted = extract_profile(
        load_path(folder / "material"), llm_for(folder / "extraction.json")
    )
    problems = [
        f"quote not found in {q.source}: {q.quote!r}" for q in extracted.rejected_quotes
    ]
    problems += [f"dropped, no quote found: {u}" for u in extracted.unsupported]
    edits: dict[str, Any] = {
        "levels": {},
        "remove_skills": [],
        "remove_experiences": [],
        "preferences": {},
        "add_skills": [],
    }
    review = folder / "review.yaml"
    if review.is_file():
        edits |= yaml.safe_load(review.read_text(encoding="utf-8")) or {}
    sheet, unknown = edit_review_sheet(export_review_sheet(extracted.profile), edits)
    problems += [f"review edit for a skill that wasn't extracted: {n}" for n in unknown]
    reviewed = apply_review_sheet(extracted.profile, sheet)
    estimated = estimate_skills(
        reviewed, llm_for(folder / "estimation.json"), skills_without_estimate(reviewed)
    )
    problems += [f"estimation: {p}" for p in estimated.problems]
    profile = estimated.profile.model_copy(
        update={"claim_support": claim_support(estimated.profile)}
    )
    return PoolCandidate(folder.name, folder, profile, problems)


def pool_scorer(
    pool: Pool, kind: str, llm_for: LLMFor = ReplayLLM
) -> Callable[[str], Scorer]:
    """Make the function that gives each candidate in a pool their scorer.

    Parameters
    ----------
    pool : Pool
        The pool.
    kind : str
        "baseline" or "llm".
    llm_for : callable, optional
        For "llm": makes the model from the path of the candidate's recorded
        answer; by default it replays it. Candidates without a recording to
        replay get a model that fails when asked.

    Returns
    -------
    callable
        From candidate name to scorer.

    Raises
    ------
    ValueError
        If `kind` isn't a known scorer.
    """
    if kind == "baseline":
        baseline = BaselineScorer()
        return lambda name: baseline
    if kind != "llm":
        raise ValueError(f"unknown scorer {kind!r}; use one of {', '.join(SCORERS)}")

    def llm_scorer(name: str) -> Scorer:
        path = pool.match_recording(name)
        try:
            llm: StructuredLLM = llm_for(path)
        except FileNotFoundError:  # Nothing recorded to replay.
            llm = _NoAnswer(path)
        return LLMScorer(llm)

    return llm_scorer


def evaluate_pool(
    pool: Pool,
    kind: str,
    reference: list[ReferenceEntry] | None = None,
    ks: tuple[int, ...] = DEFAULT_KS,
    llm_for: LLMFor = ReplayLLM,
) -> Evaluation:
    """Match and rank a pool with one scorer, and compare with a reference.

    Parameters
    ----------
    pool : Pool
        The pool.
    kind : str
        "baseline" or "llm".
    reference : list of ReferenceEntry or None, optional
        The ranking to compare with, by default the pool's intended ranking.
    ks : tuple of int, optional
        The top-k overlaps to report.
    llm_for : callable, optional
        For "llm": makes the model from each recording's path; see `pool_scorer`.

    Returns
    -------
    Evaluation
        The ranking and how it compares.

    Raises
    ------
    ValueError
        If `kind` is unknown, or the reference has no candidate of the pool.
    LLMError
        If a candidate has no recorded answer.
    """
    reference = reference if reference is not None else pool.intended
    scorer_for = pool_scorer(pool, kind, llm_for)
    results = {
        name: match_candidate(c.profile, pool.job, scorer_for(name), pool.today)
        for name, c in pool.candidates.items()
    }
    names = {r.match.id: name for name, r in results.items()}
    ranked = rank([r.match for r in results.values()], pool.job.rubric)
    ranking = [(names[r.match.id], r) for r in ranked]
    order = [n for n, _ in ranking]
    reference_order = [e.candidate for e in reference]
    top_k = {k: top_k_overlap(order, reference_order, k) for k in ks}
    tau = kendall_tau(
        {n: r.rank for n, r in ranking}, {e.candidate: e.rank for e in reference}
    )
    models = sorted({r.match.model for r in results.values()})
    return Evaluation(
        scorer=kind,
        model=", ".join(models) or "-",
        results=results,
        ranking=ranking,
        top_k=top_k,
        tau=tau,
    )


def match_recording(candidate: str, folder: Path = DEFAULT_POOL) -> Path:
    """Where a pool candidate's recorded LLM scorer answer is, without loading the pool.

    Parameters
    ----------
    candidate : str
        The candidate's folder name in the pool, such as "astrid-holm".
    folder : Path, optional
        The pool folder, by default the Fjord Grocery pool.

    Returns
    -------
    Path
        The file.
    """
    spec = yaml.safe_load((folder / "pool.yaml").read_text(encoding="utf-8")) or {}
    return folder / candidate / spec.get("match_file", "match.json")


def store_pool(repo: Repository, pool: Pool, job_name: str) -> list[str]:
    """Store a pool in the database as a demo: its job and its candidates.

    The job is created with its approved rubric, marked as a demo, and with the
    pool's `today`, so matching it gives the pool's results on any day. Each
    candidate is stored with their approved, estimated profile as a demo
    candidate named "pool-<folder name>", with `pool` in their settings so the LLM
    scorer replays their recording. Candidates stored by an earlier call are kept
    as they are, so every pool job ranks the same people.

    Parameters
    ----------
    repo : Repository
        The database.
    pool : Pool
        The loaded pool.
    job_name : str
        Name for the new job; must be free.

    Returns
    -------
    list of str
        The candidates' names in the database, sorted.

    Raises
    ------
    ValueError
        If the job name is taken, or a candidate name is taken by someone who
        isn't from the pool.
    """
    repo.create_job(
        job_name,
        demo=True,
        pool=True,
        today=pool.today.isoformat(),
        ad=pool.job.ad_text,
        company=None,
        title=None,
    )
    # A new id, so a second pool job doesn't clash with the first.
    job = pool.job.model_copy(update={"id": uuid4()})
    repo.save_job(job_name, job, "rubric")
    taken = set(repo.candidate_names())
    names = []
    for folder_name, candidate in pool.candidates.items():
        name = DEMO_PREFIX + folder_name
        names.append(name)
        if name in taken:
            if repo.settings(name).get("pool") != folder_name:
                raise ValueError(f"{name!r} is taken by a candidate not from the pool")
            continue
        repo.create_candidate(name, demo=True, pool=folder_name)
        repo.save_profile(name, candidate.profile, "assessed")
    return sorted(names)
