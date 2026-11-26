"""Matching one candidate to one job, and ranking the candidates.

A match runs the hard filters first (`unapply.matching.filters`); a candidate who
fails one isn't scored, so their total is 0 and no paid call is spent on them.
Otherwise a scorer, the baseline or the LLM scorer, scores each criterion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from unapply.matching.filters import FilterReport, check_hard_filters
from unapply.schemas import CriterionScore, Job, Match, Profile, Rubric


@dataclass
class ScoringResult:
    """A scorer's scores for one candidate, and what went wrong on the way.

    Parameters
    ----------
    scores : list of CriterionScore
        One per criterion the scorer could score, in rubric order.
    problems : list of str
        Criteria it couldn't score, and anything wrong with a model's answer.
    """

    scores: list[CriterionScore] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


class Scorer(Protocol):
    """Scores a candidate's profile against a rubric's criteria.

    Attributes
    ----------
    name : str
        The kind of scorer, recorded in the audit log: "baseline" or "llm".
    model : str
        Model or method, recorded on the match, such as "baseline-v1".
    """

    name: str
    model: str

    def score(self, profile: Profile, rubric: Rubric) -> ScoringResult:
        """Score each criterion of `rubric` for `profile`.

        Parameters
        ----------
        profile : Profile
            The candidate's profile.
        rubric : Rubric
            The rubric to score against.

        Returns
        -------
        ScoringResult
            The scores and any problems.
        """
        ...


@dataclass
class MatchResult:
    """One candidate matched to one job.

    Parameters
    ----------
    match : Match
        The match, to store.
    filters : FilterReport
        Each hard filter's outcome and reason. Not part of `Match`; it is cheap to
        compute again.
    problems : list of str
        From the scorer.
    """

    match: Match
    filters: FilterReport
    problems: list[str] = field(default_factory=list)


def match_candidate(
    profile: Profile, job: Job, scorer: Scorer, today: date | None = None
) -> MatchResult:
    """Match a candidate to a job: hard filters, then scores per criterion.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    job : Job
        The job, with the rubric to use.
    scorer : Scorer
        Scores the criteria, such as `BaselineScorer()`.
    today : date or None, optional
        The date current roles run to, for years of experience; by default today.

    Returns
    -------
    MatchResult
        The match against the job's current rubric version. If a hard filter
        failed, it has no scores and the scorer isn't called.
    """
    filters = check_hard_filters(profile, job.rubric.hard_filters, today)
    result = scorer.score(profile, job.rubric) if filters.passed else ScoringResult()
    match = Match(
        job_id=job.id,
        profile_id=profile.id,
        rubric_version=job.rubric.version,
        passed_hard_filters=filters.passed,
        criterion_scores=result.scores,
        model=scorer.model,
    )
    return MatchResult(match=match, filters=filters, problems=result.problems)


@dataclass(frozen=True)
class Ranked:
    """One match's place in a ranking.

    Parameters
    ----------
    rank : int
        1 for the best. Equal totals share a rank, and the next rank skips
        ("1, 2, 2, 4").
    total : float
        `Match.total`, from 0 to 1.
    match : Match
        The match.
    """

    rank: int
    total: float
    match: Match


def rank(matches: list[Match], rubric: Rubric) -> list[Ranked]:
    """Rank matches against one rubric version, best first.

    Parameters
    ----------
    matches : list of Match
        Matches against `rubric`, at most one per candidate (see `latest`).
    rubric : Rubric
        The rubric, for the criterion weights.

    Returns
    -------
    list of Ranked
        By total, highest first; candidates who failed a hard filter last. Equal
        totals are ordered by profile id, so the order is reproducible.
    """
    totals = [(round(m.total(rubric), 4), m) for m in matches]
    totals.sort(
        key=lambda t: (not t[1].passed_hard_filters, -t[0], str(t[1].profile_id))
    )
    ranked: list[Ranked] = []
    for i, (total, m) in enumerate(totals):
        previous = ranked[-1] if ranked else None
        same = (
            previous is not None
            and previous.total == total
            and previous.match.passed_hard_filters == m.passed_hard_filters
        )
        ranked.append(
            Ranked(rank=previous.rank if same else i + 1, total=total, match=m)
        )
    return ranked


def latest(matches: list[Match], model: str | None = None) -> list[Match]:
    """Keep each candidate's newest match, as a job is matched again over time.

    Parameters
    ----------
    matches : list of Match
        Matches for one job and rubric version, in any order.
    model : str or None, optional
        Only matches by this scorer (`Match.model`). By default any.

    Returns
    -------
    list of Match
        One per profile, the latest by `scored_at`.
    """
    newest: dict[object, Match] = {}
    for m in matches:
        if model is not None and m.model != model:
            continue
        kept = newest.get(m.profile_id)
        if kept is None or m.scored_at >= kept.scored_at:
            newest[m.profile_id] = m
    return list(newest.values())
