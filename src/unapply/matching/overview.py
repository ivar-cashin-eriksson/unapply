"""A job's overview for its employer: aggregates over the candidates, never one of them.

How many candidates connected and were matched, how many meet every hard filter and
which filters fail most, how the totals and the own and estimated scores are spread,
which skills the candidates have compared with the rubric's, and how far candidates
got against the vacancies. Counts only: no quote, name, alias or profile id. Worked
out from stored matches and the baseline, so no model is called.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from unapply.db.repository import Repository
from unapply.jobs.board import ListingCounts, connected_profiles, count
from unapply.matching.baseline import BASELINE_MODEL, own_and_estimated
from unapply.matching.filters import Outcome, check_hard_filters
from unapply.matching.scoring import latest, rank
from unapply.matching.shortlist import rubric_skills
from unapply.schemas import Job, Match, Rubric
from unapply.taxonomy import Taxonomy, default_taxonomy

# Score bins: tenths from 0 to 1, the last one including 1.
BINS = 10
# How many skills outside the rubric are listed.
OTHER_SKILLS = 10

ScorerName = Literal["baseline", "llm"]


class FilterCount(BaseModel):
    """How the matched candidates did on one hard filter.

    Parameters
    ----------
    name : str
        "location", "work_mode", "work_permit" or "min_years_experience".
    passed, failed, unknown : int
        Candidates who meet it, who don't, and whose profile doesn't say.
    """

    name: str
    passed: int = 0
    failed: int = 0
    unknown: int = 0


class Distribution(BaseModel):
    """How one score is spread over the matched candidates.

    Parameters
    ----------
    bins : list of int
        Candidates per tenth: `bins[i]` counts scores from i/10 up to (i+1)/10,
        the last bin including 1.
    median : float or None
        The median score, None without candidates.
    """

    bins: list[int] = Field(default_factory=lambda: [0] * BINS)
    median: float | None = None


class RubricSkillCount(BaseModel):
    """How many matched candidates have a skill the rubric asks for.

    Parameters
    ----------
    skill : str
        Canonical name.
    candidates : int
        Candidates with the skill itself.
    related : int
        Candidates without it but with a skill whose evidence counts for it
        through the taxonomy ("dbt" for "sql").
    """

    skill: str
    candidates: int = 0
    related: int = 0


class SkillCount(BaseModel):
    """How many matched candidates have a skill.

    Parameters
    ----------
    skill : str
        Canonical name.
    candidates : int
        Candidates with it.
    """

    skill: str
    candidates: int


class Overview(BaseModel):
    """A job's candidates in aggregate, for its employer.

    Parameters
    ----------
    job : str
        The job.
    rubric_version : int
        The rubric version matched against.
    scorer : {"baseline", "llm"}
        Whose matches the totals come from.
    connected : int
        Candidates connected to the job.
    matched : int
        Of those, candidates with a match on this rubric version by this scorer.
    passed_hard_filters : int
        Matched candidates who fail no hard filter.
    filters : list of FilterCount
        One per hard filter the rubric sets, those failed most first.
    totals : Distribution
        The scorer's totals, which set the rank.
    own : Distribution
        The baseline on the candidates' own levels only.
    estimated : Distribution
        The baseline on the estimated levels only.
    rubric_skills : list of RubricSkillCount
        The rubric's skills, in rubric order.
    other_skills : list of SkillCount
        The skills outside the rubric most candidates have, most common first.
    counts : ListingCounts
        Connected, revealed, asked to apply and applied.
    vacancies : int
        The job's vacancies.
    """

    job: str
    rubric_version: int
    scorer: ScorerName
    connected: int
    matched: int
    passed_hard_filters: int
    filters: list[FilterCount]
    totals: Distribution
    own: Distribution
    estimated: Distribution
    rubric_skills: list[RubricSkillCount]
    other_skills: list[SkillCount]
    counts: ListingCounts
    vacancies: int


def stored_matches(
    repo: Repository, name: str, job: Job, rubric: Rubric, scorer: ScorerName
) -> list[Match]:
    """Find each connected candidate's latest match on a rubric version by a scorer.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The job's name.
    job : Job
        The job.
    rubric : Rubric
        The rubric version.
    scorer : {"baseline", "llm"}
        Which scorer's matches.

    Returns
    -------
    list of Match
        Candidates who withdrew are left out; their earlier audit entries stay.
    """
    allowed = connected_profiles(repo, name)
    return latest(
        [
            m
            for m in repo.matches(job.id, rubric.version)
            if m.profile_id in allowed
            and (m.model == BASELINE_MODEL) == (scorer == "baseline")
        ]
    )


def distribution(scores: Iterable[float]) -> Distribution:
    """Count scores per tenth, and find their median.

    Parameters
    ----------
    scores : iterable of float
        Scores from 0 to 1.

    Returns
    -------
    Distribution
        Scores outside 0 to 1 are clamped into the first or last bin.
    """
    values = sorted(scores)
    bins = [0] * BINS
    for v in values:
        bins[min(BINS - 1, max(0, int(v * BINS)))] += 1
    if not values:
        return Distribution(bins=bins)
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return Distribution(bins=bins, median=round(median, 4))


def job_overview(
    repo: Repository,
    name: str,
    scorer: ScorerName = "baseline",
    today: date | None = None,
    taxonomy: Taxonomy | None = None,
) -> Overview:
    """Sum up a job's candidates for its employer, from stored matches.

    Parameters
    ----------
    repo : Repository
        The database.
    name : str
        The job; it must have a rubric.
    scorer : {"baseline", "llm"}, optional
        Whose totals to use, by default the baseline. The own and estimated scores
        always come from the baseline.
    today : date or None, optional
        The date years of experience are counted to, by default today.
    taxonomy : Taxonomy or None, optional
        By default `default_taxonomy()`.

    Returns
    -------
    Overview
        Only candidates still connected, with a current match on the current rubric
        version, are counted. Nothing is recorded: no ranking is shown.

    Raises
    ------
    NotFound
        If there is no such job.
    ValueError
        If the job has no rubric yet.
    """
    taxonomy = taxonomy or default_taxonomy()
    job = repo.job(name)
    if job is None:
        repo.job_settings(name)  # NotFound if there is no such job.
        raise ValueError("The job has no rubric yet.")
    rubric = job.rubric
    ranked = rank(stored_matches(repo, name, job, rubric, scorer), rubric)

    filters: dict[str, FilterCount] = {}
    totals, own, estimated = [], [], []
    passed = 0
    skill_sets: list[set[str]] = []
    for r in ranked:
        totals.append(r.total)
        passed += r.match.passed_hard_filters
        profile = repo.profile_by_id(r.match.profile_id)
        if profile is None:
            continue
        for check in check_hard_filters(profile, rubric.hard_filters, today).checks:
            f = filters.setdefault(check.name, FilterCount(name=check.name))
            if check.outcome == Outcome.PASS:
                f.passed += 1
            elif check.outcome == Outcome.FAIL:
                f.failed += 1
            else:
                f.unknown += 1
        o, e = own_and_estimated(profile, rubric, taxonomy)
        own.append(o)
        estimated.append(e)
        skill_sets.append({taxonomy.canonical(s.name) for s in profile.skills})

    wanted = rubric_skills(rubric, taxonomy)
    rubric_counts = []
    for skill in wanted:
        related = taxonomy.supporting(skill)
        rubric_counts.append(
            RubricSkillCount(
                skill=skill,
                candidates=sum(skill in s for s in skill_sets),
                related=sum(skill not in s and bool(s & related) for s in skill_sets),
            )
        )
    others = Counter(s for skills in skill_sets for s in skills if s not in wanted)
    # Most common first, then by name, so the list is the same every time.
    common = sorted(others.items(), key=lambda kv: (-kv[1], kv[0]))[:OTHER_SKILLS]

    counts = count(repo, name)
    return Overview(
        job=name,
        rubric_version=rubric.version,
        scorer=scorer,
        connected=counts.connected,
        matched=len(ranked),
        passed_hard_filters=passed,
        filters=sorted(filters.values(), key=lambda f: -f.failed),
        totals=distribution(totals),
        own=distribution(own),
        estimated=distribution(estimated),
        rubric_skills=rubric_counts,
        other_skills=[SkillCount(skill=s, candidates=n) for s, n in common],
        counts=counts,
        vacancies=job.vacancies,
    )
