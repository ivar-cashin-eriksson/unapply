"""Matching routes: score a job's candidates, read the ranking and the shortlist.

Employer routes. Candidates are anonymised: the ranking names profiles by id, never
by the candidate's name, and the shortlist shows them by an alias with names and
contact details removed, and no quotes until the employer reveals them. Only
candidates connected to the job (on the job board) who approved their profile are
matched, and only against an approved rubric, which matching locks. From the
shortlist, the employer reveals a candidate and then requests an application (see
`unapply.api.hiring`).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from unapply.api.candidates import demos, free_name
from unapply.api.deps import AllowAPI, Context, Ctx
from unapply.api.hiring import contact, employer_progress
from unapply.api.models import (
    HardFilterCheck,
    RankedCandidate,
    Ranking,
    Shortlist,
    ShortlistCandidate,
    ShortlistDemo,
)
from unapply.app import demo
from unapply.evaluation.pool import load_pool, match_recording, store_pool
from unapply.jobs.board import count
from unapply.llm import (
    API_SWITCH,
    APICallsDisabled,
    LLMError,
    ReplayLLM,
    StructuredLLM,
    api_calls_allowed,
)
from unapply.matching import (
    BaselineScorer,
    LLMScorer,
    Ranked,
    Scorer,
    check_hard_filters,
    own_and_estimated,
    rank,
)
from unapply.matching.overview import Overview, job_overview, stored_matches
from unapply.matching.run import MatchingError, match_job, record_ranking
from unapply.matching.shortlist import (
    Intent,
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
    """Match every candidate connected to the job with an approved profile, and rank.

    Every candidate is scored; those who fail a hard filter are ranked after
    everyone who passes. The matches are stored, which locks the rubric version. With the LLM scorer, paid calls are
    refused before anyone is scored unless allowed; a demo candidate matched to a
    demo job replays a recording.
    """
    job_settings = ctx.repo.job_settings(name)
    job_demo = bool(job_settings.get("demo"))
    if scorer == "llm" and job_settings.get("llm") is False:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This demo job has no recorded LLM scorer answers; match it with the "
            "baseline scorer, which is free.",
        )

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

    Only candidates still connected to the job are ranked. No model is called.
    Hard filter outcomes, and the baseline's totals on own and on estimated levels
    only, are worked out again for candidates whose profile hasn't changed since.
    The ranking shown is recorded in the audit log, like every ranking.
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
    number, unique on this shortlist, their roles with names and contact details
    removed, their own and estimated levels in the rubric's skills, to compare
    candidates on, and how far they got (revealed, asked to apply, applied or
    declined). Until the employer reveals a candidate, their quotes are left out:
    each criterion score says how many support it. Once revealed, their name,
    contact details and quotes are included. No model is called.
    """
    job, ranked = _stored(ctx, name, scorer, version)
    ranking = _ranking(ctx, name, job, scorer, ranked, {})
    known_as = identities(r.profile_id for r in ranking.candidates)
    progress = {
        pid: p
        for p in ctx.repo.progresses(job=name)
        for pid in ctx.repo.profile_ids(p.candidate)
    }
    candidates = []
    for r in ranking.candidates:
        profile = ctx.repo.profile_by_id(r.profile_id)
        if profile is None:
            continue
        found = progress.get(profile.id)
        revealed = found is not None and found.revealed_at is not None
        shown = anonymous_candidate(
            profile,
            job.rubric,
            _names(ctx, profile.id),
            known_as=known_as[profile.id],
            quotes=revealed,
        )
        candidates.append(
            ShortlistCandidate(
                **dict(shown),
                progress=employer_progress(found, profile.id),
                contact=contact(ctx, found.candidate) if found and revealed else None,
            )
        )
    return Shortlist(
        ranking=ranking,
        rubric=job.rubric,
        skills=rubric_skills(job.rubric),
        candidates=candidates,
        intents=ctx.repo.intents(job.id),
        reveal_quota=job.reveal_quota,
        counts=count(ctx.repo, name),
        vacancies=job.vacancies,
    )


@router.get("/{name}/overview")
def overview(name: str, ctx: Ctx, scorer: ScorerName = "baseline") -> Overview:
    """Sum up the job's candidates on the current rubric version, in aggregate.

    How many connected and were matched, how many meet every hard filter and which
    filters fail most, how the scorer's totals and the baseline's own and estimated
    scores are spread, which skills candidates have compared with the rubric's, and
    how far they got against the vacancies. Counts only: no quote, name, alias or
    profile id. Matches come from `POST /jobs/<name>/match`; nothing is recorded and
    no model is called.
    """
    _need_job(ctx, name)
    return job_overview(
        ctx.repo, name, scorer, today=_today(ctx.repo.job_settings(name))
    )


@router.get("/{name}/intents")
def list_intents(name: str, ctx: Ctx) -> list[Intent]:
    """List the early reveal and application requests on this job, kept as history.

    They only recorded intent; reveals and application requests now go through
    `POST /jobs/<name>/candidates/<profile id>/reveal` and `.../request-application`.
    """
    return ctx.repo.intents(_need_job(ctx, name).id)


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
    matches = stored_matches(ctx.repo, name, job, rubric, scorer)
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
