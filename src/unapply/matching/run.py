"""Match a job's candidates from the database, save the matches and rank them.

Used by `unapply match` and the API. Only candidates who approved their profile are
matched, and only against an approved rubric: matching locks the rubric version, so
a draft would be frozen before the recruiter is done with it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from unapply.db.repository import NotFound, Repository
from unapply.matching.scoring import MatchResult, Ranked, Scorer, match_candidate, rank
from unapply.schemas import Job, Profile

# Makes the scorer for one candidate, given their name and settings. Called for
# every candidate before any is scored, so a refused paid call changes nothing.
ScorerFor = Callable[[str, dict[str, Any]], Scorer]


class MatchingError(ValueError):
    """The job or a candidate isn't ready to match. The message says why."""


@dataclass
class JobMatching:
    """A job's candidates, matched and ranked.

    Parameters
    ----------
    job : Job
        The job, with the rubric version used.
    results : dict of str to MatchResult
        Each candidate's match, by candidate name.
    ranking : list of Ranked
        The matches, best first.
    """

    job: Job
    results: dict[str, MatchResult]
    ranking: list[Ranked]

    def name_of(self, ranked: Ranked) -> str:
        """Return the candidate name of a ranked match.

        Parameters
        ----------
        ranked : Ranked
            An entry of `ranking`.

        Returns
        -------
        str
            The candidate's name in the database. Not for employers: they see
            candidates anonymised.
        """
        return next(n for n, r in self.results.items() if r.match.id == ranked.match.id)


def approved_job(repo: Repository, name: str) -> Job:
    """Read a job that is ready to match.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The job.

    Returns
    -------
    Job
        The job, with its current rubric.

    Raises
    ------
    NotFound
        If there is no such job.
    MatchingError
        If it has no rubric yet, or the rubric isn't approved.
    """
    job = repo.job(name)
    if job is None:
        if name not in repo.job_names():
            raise NotFound(f"no job called {name!r}")
        raise MatchingError(f"job {name!r} has no rubric yet; extract one first")
    if job.rubric.approved_at is None:
        raise MatchingError(
            f"rubric version {job.rubric.version} of job {name!r} isn't approved; "
            "approve it first, as matching locks it"
        )
    return job


def approved_candidates(
    repo: Repository, names: list[str] | None = None
) -> dict[str, Profile]:
    """Read the candidates whose approved profile can be matched.

    Parameters
    ----------
    repo : Repository
        The database.
    names : list of str or None, optional
        Only these candidates; each must have an approved profile. By default
        every candidate who has one.

    Returns
    -------
    dict of str to Profile
        Profiles by candidate name, sorted by name.

    Raises
    ------
    NotFound
        If a named candidate doesn't exist.
    MatchingError
        If a named candidate has no approved profile.
    """
    profiles = {}
    for name in names if names is not None else repo.candidate_names():
        profile = repo.profile(name)
        if profile is None or profile.approved_by_candidate_at is None:
            if names is not None:
                raise MatchingError(f"candidate {name!r} has no approved profile")
            continue
        profiles[name] = profile
    return dict(sorted(profiles.items()))


def match_job(
    repo: Repository,
    job_name: str,
    scorer_for: ScorerFor,
    candidates: list[str] | None = None,
    today: date | None = None,
) -> JobMatching:
    """Match candidates to a job, save the matches and rank them.

    Parameters
    ----------
    repo : Repository
        The database. The matches are saved in it, which locks the rubric version.
    job_name : str
        The job; its rubric must be approved.
    scorer_for : callable
        Makes each candidate's scorer from their name and settings. All are made
        before anyone is scored.
    candidates : list of str or None, optional
        Only these candidates, by default everyone with an approved profile.
    today : date or None, optional
        The date current roles run to, for years of experience; by default today.

    Returns
    -------
    JobMatching
        Each candidate's match and the ranking.

    Raises
    ------
    NotFound, MatchingError
        If the job or a named candidate isn't ready; nothing is saved.
    APICallsDisabled
        If a scorer would make a paid call that isn't allowed; nothing is saved.
    """
    job = approved_job(repo, job_name)
    profiles = approved_candidates(repo, candidates)
    scorers = {name: scorer_for(name, repo.settings(name)) for name in profiles}
    results = {
        name: match_candidate(profile, job, scorers[name], today)
        for name, profile in profiles.items()
    }
    for result in results.values():
        repo.save_match(result.match)
    ranking = rank([r.match for r in results.values()], job.rubric)
    return JobMatching(job=job, results=results, ranking=ranking)
