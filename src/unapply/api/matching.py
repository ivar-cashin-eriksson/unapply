"""Matching routes: score a job's candidates, read the ranking and the shortlist.

Employer routes. Candidates are anonymised: the ranking names profiles by id, never
by the candidate's name, and the shortlist shows them by an alias with names and
contact details removed. Only candidates who approved their profile are matched, and
only against an approved rubric, which matching locks. From the shortlist, the
employer can ask to reveal a candidate or request an application; both only record
the intent, as there is no payment yet.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from unapply.api.candidates import demos, free_name
from unapply.api.deps import AllowAPI, Context, Ctx
from unapply.api.models import (
    HardFilterCheck,
    NewIntent,
    RankedCandidate,
    Ranking,
    Shortlist,
    ShortlistDemo,
)
from unapply.app import demo
from unapply.evaluation.pool import load_pool, match_recording, store_pool
from unapply.llm import (
    API_SWITCH,
    APICallsDisabled,
    LLMError,
    ReplayLLM,
    StructuredLLM,
    api_calls_allowed,
)
from unapply.matching import (
    BASELINE_MODEL,
    BaselineScorer,
    LLMScorer,
    Ranked,
    Scorer,
    check_hard_filters,
    latest,
    own_and_estimated,
    rank,
)
from unapply.matching.run import MatchingError, match_job, record_ranking
from unapply.matching.shortlist import (
    Intent,
    IntentKind,
    anonymous_candidate,
    identities,
    rubric_skills,
)
from unapply.schemas import Job

router = APIRouter(prefix="/jobs", tags=["matching"])

ScorerName = Annotated[
    Literal["baseline", "llm"],
    Query(
        description="baseline: plain code, free. llm: one model call per candidate "
        "(paid, unless the job and candidate are both demos)."
    ),
]
Version = Annotated[
    int | None, Query(description="Rubric version, by default the current one.")
]


@router.post("/{name}/match")
def match(
    name: str, ctx: Ctx, scorer: ScorerName = "baseline", allow_api: AllowAPI = False
) -> Ranking:
    """Match every candidate with an approved profile to the job, and rank them.

    Every candidate is scored; those who fail a hard filter are ranked after
    everyone who passes. The matches are stored, which locks the rubric version. With the LLM scorer, paid calls are
    refused before anyone is scored unless allowed; a demo candidate matched to a
    demo job replays a recording.
    """
    job_settings = ctx.repo.job_settings(name)
    job_demo = bool(job_settings.get("demo"))

    def scorer_for(candidate: str, settings: dict[str, Any]) -> Scorer:
        if scorer == "baseline":
            return BaselineScorer()
        names = [settings["github"]] if settings.get("github") else []
        if job_demo and settings.get("pool"):
            return LLMScorer(_pool_llm(settings["pool"]), names)
        if job_demo and settings.get("demo"):
            return LLMScorer(demo.demo_llm("match"), names)
        # A demo job doesn't make a real candidate free: only both together replay.
        if not (allow_api or api_calls_allowed()):
            raise APICallsDisabled(
                "scoring with the LLM would make paid API calls, which are off. Add "
                f"?allow_api=true to the request to allow them, or set {API_SWITCH}=1."
            )
        return LLMScorer(ctx.llm_factory("match", True), names)

    try:
        matching = match_job(ctx.repo, name, scorer_for, today=_today(job_settings))
    except MatchingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    problems = {r.match.id: r.problems for r in matching.results.values()}
    return _ranking(ctx, name, matching.job, scorer, matching.ranking, problems)


@router.get("/{name}/ranking")
def ranking(
    name: str, ctx: Ctx, scorer: ScorerName = "baseline", version: Version = None
) -> Ranking:
    """Read the job's ranking from stored matches: each candidate's latest match.

    No model is called. Hard filter outcomes, and the baseline's totals on own and
    on estimated levels only, are worked out again for candidates whose profile
    hasn't changed since. The ranking shown is recorded in the audit
    log, like every ranking.
    """
    job, ranked = _stored(ctx, name, scorer, version)
    return _ranking(ctx, name, job, scorer, ranked, {})


@router.get("/{name}/shortlist")
def shortlist(
    name: str, ctx: Ctx, scorer: ScorerName = "baseline", version: Version = None
) -> Shortlist:
    """Read the job's anonymised shortlist: the ranking, and who is on it.

    The ranking is the one `GET /jobs/<name>/ranking` gives, and is recorded in the
    audit log the same way. Each ranked candidate comes with an alias and avatar
    number, unique on this shortlist, their roles
    and quotes with names and contact details removed (so cited evidence can be
    read), and their own and estimated levels in the rubric's skills, to compare
    candidates on. No model is called.
    """
    job, ranked = _stored(ctx, name, scorer, version)
    ranking = _ranking(ctx, name, job, scorer, ranked, {})
    known_as = identities(r.profile_id for r in ranking.candidates)
    candidates = []
    for r in ranking.candidates:
        profile = ctx.repo.profile_by_id(r.profile_id)
        if profile is not None:
            candidates.append(
                anonymous_candidate(
                    profile,
                    job.rubric,
                    _names(ctx, profile.id),
                    known_as=known_as[profile.id],
                )
            )
    return Shortlist(
        ranking=ranking,
        rubric=job.rubric,
        skills=rubric_skills(job.rubric),
        candidates=candidates,
        intents=ctx.repo.intents(job.id),
        reveal_quota=job.reveal_quota,
    )


@router.get("/{name}/intents")
def list_intents(name: str, ctx: Ctx) -> list[Intent]:
    """List what the employer asked for on this job: reveals and applications."""
    return ctx.repo.intents(_need_job(ctx, name).id)


@router.post("/{name}/intents", status_code=status.HTTP_201_CREATED)
def record_intent(name: str, body: NewIntent, ctx: Ctx, response: Response) -> Intent:
    """Ask to reveal a shortlisted candidate, or to request their application.

    Only the intent is recorded: no payment is taken, the candidate's identity
    isn't shown and they aren't contacted yet. Asking again for the same candidate
    returns the earlier record (200). Only candidates matched to this job can be
    asked about, and reveals are limited to the job's reveal quota.
    """
    job = _need_job(ctx, name)
    if not any(m.profile_id == body.profile_id for m in ctx.repo.matches(job.id)):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such candidate on this job's shortlist."
        )
    earlier = ctx.repo.intents(job.id, body.kind)
    again = any(i.profile_id == body.profile_id for i in earlier)
    if (
        body.kind == IntentKind.REVEAL
        and not again
        and len(earlier) >= job.reveal_quota
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"All {job.reveal_quota} reveals for this job are used.",
        )
    intent, new = ctx.repo.record_intent(
        Intent(job_id=job.id, profile_id=body.profile_id, kind=body.kind)
    )
    if not new:
        response.status_code = status.HTTP_200_OK
    return intent


@demos.post("/shortlist", status_code=status.HTTP_201_CREATED, tags=["demos"])
def create_shortlist_demo(ctx: Ctx) -> ShortlistDemo:
    """Create a Fjord Grocery demo job with its rubric approved, and its pool.

    The job is named "fjord-grocery-shortlist", or with a number if taken. The 12
    synthetic candidates of `tests/fixtures/pool` are stored once, as demo
    candidates with approved profiles, so the job can be matched right away; both
    scorers replay recordings and cost nothing.
    """
    if not demo.available():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo isn't installed.")
    name = free_name(ctx.repo.job_names(), "fjord-grocery-shortlist")
    candidates = store_pool(ctx.repo, load_pool(), name)
    return ShortlistDemo(name=name, candidates=len(candidates))


def _stored(
    ctx: Context, name: str, scorer: str, version: int | None
) -> tuple[Job, list[Ranked]]:
    """Rank a job's stored matches by one scorer, and record the ranking shown."""
    job = _need_job(ctx, name)
    rubric = job.rubric if version is None else ctx.repo.rubric(job.id, version)
    if rubric is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rubric version {version}.")
    matches = latest(
        [
            m
            for m in ctx.repo.matches(job.id, rubric.version)
            if (m.model == BASELINE_MODEL) == (scorer == "baseline")
        ]
    )
    scored = job.model_copy(update={"rubric": rubric})
    ranked = rank(matches, rubric)
    record_ranking(ctx.repo, scored, ranked, scorer)
    return scored, ranked


def _ranking(
    ctx: Context,
    name: str,
    job: Job,
    scorer: str,
    ranked: list[Ranked],
    problems: dict[Any, list[str]],
) -> Ranking:
    today = _today(ctx.repo.job_settings(name))
    candidates = []
    for r in ranked:
        profile = ctx.repo.profile_by_id(r.match.profile_id)
        filters = (
            [
                HardFilterCheck(name=c.name, outcome=c.outcome.value, reason=c.reason)
                for c in check_hard_filters(
                    profile, job.rubric.hard_filters, today
                ).checks
            ]
            if profile is not None
            else None
        )
        own, estimated = (
            own_and_estimated(profile, job.rubric)
            if profile is not None
            else (None, None)
        )
        candidates.append(
            RankedCandidate(
                rank=r.rank,
                total=r.total,
                own_total=own,
                estimated_total=estimated,
                profile_id=r.match.profile_id,
                match_id=r.match.id,
                passed_hard_filters=r.match.passed_hard_filters,
                hard_filters=filters,
                criterion_scores=r.match.criterion_scores,
                model=r.match.model,
                scored_at=r.match.scored_at,
                problems=problems.get(r.match.id, []),
            )
        )
    return Ranking(
        job=name,
        rubric_version=job.rubric.version,
        scorer=scorer,
        candidates=candidates,
    )


def _today(settings: dict[str, Any]) -> date | None:
    """Return the date a job counts years of experience to: fixed for the pool demo."""
    return date.fromisoformat(settings["today"]) if settings.get("today") else None


def _pool_llm(candidate: str) -> StructuredLLM:
    """Replay a pool candidate's recorded LLM scorer answer, if they have one."""
    path = match_recording(candidate)
    return ReplayLLM(path) if path.is_file() else _NoRecording(candidate)


class _NoRecording:
    """Stands in for the model for a pool candidate without a recorded answer.

    Every pool candidate has a recording; this fails clearly if that stops being
    true.
    """

    model = "replay:none"

    def __init__(self, candidate: str) -> None:
        self.candidate = candidate

    def parse(self, **_kwargs: Any) -> Any:  # noqa: ANN401
        raise LLMError(f"no recorded LLM scorer answer for {self.candidate}")


def _names(ctx: Context, profile_id: UUID) -> list[str]:
    """Names to remove from a candidate's texts: their GitHub username, if set."""
    name = ctx.repo.candidate_of(profile_id)
    github = ctx.repo.settings(name).get("github") if name else None
    return [github] if github else []


def _need_job(ctx: Context, name: str) -> Job:
    job = ctx.repo.job(name)
    if job is None:
        ctx.repo.job_settings(name)  # 404 if there is no such job.
        raise HTTPException(status.HTTP_409_CONFLICT, "The job has no rubric yet.")
    return job
