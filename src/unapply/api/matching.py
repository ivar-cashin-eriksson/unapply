"""Matching routes: score a job's candidates and read the ranking.

Employer routes. Candidates are anonymised: the ranking names profiles by id, never
by the candidate's name. Only candidates who approved their profile are matched, and
only against an approved rubric, which matching locks.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status

from unapply.api.deps import AllowAPI, Context, Ctx
from unapply.api.models import HardFilterCheck, RankedCandidate, Ranking
from unapply.app import demo
from unapply.llm import API_SWITCH, APICallsDisabled, api_calls_allowed
from unapply.matching import (
    BASELINE_MODEL,
    BaselineScorer,
    LLMScorer,
    Ranked,
    Scorer,
    check_hard_filters,
    latest,
    rank,
)
from unapply.matching.run import MatchingError, match_job, record_ranking
from unapply.schemas import Job

router = APIRouter(prefix="/jobs", tags=["matching"])

ScorerName = Annotated[
    Literal["baseline", "llm"],
    Query(
        description="baseline: plain code, free. llm: one model call per candidate "
        "(paid, unless the job and candidate are both demos)."
    ),
]


@router.post("/{name}/match")
def match(
    name: str, ctx: Ctx, scorer: ScorerName = "baseline", allow_api: AllowAPI = False
) -> Ranking:
    """Match every candidate with an approved profile to the job, and rank them.

    Hard filters first: candidates who fail one aren't scored. The matches are
    stored, which locks the rubric version. With the LLM scorer, paid calls are
    refused before anyone is scored unless allowed; a demo candidate matched to a
    demo job replays a recording.
    """
    job_demo = bool(ctx.repo.job_settings(name).get("demo"))

    def scorer_for(candidate: str, settings: dict[str, Any]) -> Scorer:
        if scorer == "baseline":
            return BaselineScorer()
        names = [settings["github"]] if settings.get("github") else []
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
        matching = match_job(ctx.repo, name, scorer_for)
    except MatchingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    problems = {r.match.id: r.problems for r in matching.results.values()}
    return _ranking(ctx, name, matching.job, scorer, matching.ranking, problems)


@router.get("/{name}/ranking")
def ranking(
    name: str,
    ctx: Ctx,
    scorer: ScorerName = "baseline",
    version: Annotated[
        int | None, Query(description="Rubric version, by default the current one.")
    ] = None,
) -> Ranking:
    """Read the job's ranking from stored matches: each candidate's latest match.

    No model is called. Hard filter outcomes are worked out again for candidates
    whose profile hasn't changed since. The ranking shown is recorded in the audit
    log, like every ranking.
    """
    job = ctx.repo.job(name)
    if job is None:
        ctx.repo.job_settings(name)  # 404 if there is no such job.
        raise HTTPException(status.HTTP_409_CONFLICT, "The job has no rubric yet.")
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
    return _ranking(ctx, name, scored, scorer, ranked, {})


def _ranking(
    ctx: Context,
    name: str,
    job: Job,
    scorer: str,
    ranked: list[Ranked],
    problems: dict[Any, list[str]],
) -> Ranking:
    candidates = []
    for r in ranked:
        profile = ctx.repo.profile_by_id(r.match.profile_id)
        filters = (
            [
                HardFilterCheck(name=c.name, outcome=c.outcome.value, reason=c.reason)
                for c in check_hard_filters(profile, job.rubric.hard_filters).checks
            ]
            if profile is not None
            else None
        )
        candidates.append(
            RankedCandidate(
                rank=r.rank,
                total=r.total,
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
