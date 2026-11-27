"""The baseline scorer: scores criteria in plain code, without a model.

It is fully deterministic and free, so it is the reference the LLM scorer is
compared with, and a fallback. For each criterion that names a skill it finds the
candidate's skill, or skills whose evidence counts for it through the taxonomy
("dbt" for "sql"), and scores:

    score = level fit x evidence factor (x RELATED_FACTOR for a related skill)

- **Level fit** compares the candidate's level with the criterion's `min_level`
  (WORKING if it sets none): `min(1, level / min_level) ** 2`. The level blends the
  estimate and the candidate's own level by the estimate's confidence, so a sure
  estimate counts and an unsure one leaves room for the candidate's word.
- **Evidence factor** counts the quotes from the candidate's documents behind the
  skill: none (only their own statements) 0.5, one 0.9, two or more 1.

Criteria that name no skill, such as "retail experience", aren't scored: the
baseline can't read them. `Match.total` then averages over the others.

With `levels="own"` or `levels="estimated"` it uses only one of the two levels, so
the shortlist can show a candidate's score on their own rating beside their score
on the estimate from their evidence (`own_and_estimated`).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from unapply.matching.scoring import ScoringResult
from unapply.schemas import (
    Criterion,
    CriterionScore,
    Profile,
    Rubric,
    Skill,
    SkillLevel,
    SourceKind,
)
from unapply.taxonomy import Taxonomy, default_taxonomy

BASELINE_MODEL = "baseline-v1"
# The level asked for when a criterion sets none: "experience with X".
DEFAULT_MIN_LEVEL = SkillLevel.WORKING
# Evidence factor by number of document quotes: 0, 1, 2 or more.
EVIDENCE_FACTORS = (0.5, 0.9, 1.0)
# Evidence for a related skill ("dbt" for "sql") counts for less than direct evidence.
RELATED_FACTOR = 0.75

# Which levels the baseline uses: both, blended by the estimate's confidence, or one.
Levels = Literal["blend", "own", "estimated"]
LEVELS: tuple[Levels, ...] = ("blend", "own", "estimated")


class BaselineScorer:
    """Score criteria from skill levels and evidence counts, without a model.

    Parameters
    ----------
    taxonomy : Taxonomy or None, optional
        For skills whose evidence counts for a criterion's skill, by default
        `default_taxonomy()`.
    levels : {"blend", "own", "estimated"}, optional
        Which levels to use (see `level`): by default both, blended by the
        estimate's confidence. Only "blend" is used for rankings; the others give
        the shortlist's own and estimated scores.
    """

    name = "baseline"
    model = BASELINE_MODEL

    def __init__(
        self, taxonomy: Taxonomy | None = None, levels: Levels = "blend"
    ) -> None:
        if levels not in LEVELS:
            raise ValueError(
                f"unknown levels {levels!r}; use one of {', '.join(LEVELS)}"
            )
        self.taxonomy = taxonomy or default_taxonomy()
        self.levels = levels

    def score(self, profile: Profile, rubric: Rubric) -> ScoringResult:
        """Score every criterion that names a skill.

        Parameters
        ----------
        profile : Profile
            The candidate's profile.
        rubric : Rubric
            The rubric to score against.

        Returns
        -------
        ScoringResult
            One score per criterion with a skill, in rubric order, and a problem
            for each criterion it couldn't score.
        """
        scores, problems = [], []
        for c in rubric.criteria:
            if not c.skill:
                problems.append(
                    f"{c.description}: names no skill, so the baseline doesn't score it"
                )
                continue
            scores.append(self.score_criterion(profile, c))
        return ScoringResult(scores=scores, problems=problems)

    def score_criterion(self, profile: Profile, criterion: Criterion) -> CriterionScore:
        """Score one criterion that names a skill.

        Parameters
        ----------
        profile : Profile
            The candidate's profile.
        criterion : Criterion
            The criterion; its `skill` must be set.

        Returns
        -------
        CriterionScore
            The best score of the skill itself and the skills whose evidence counts
            for it, with the evidence it rests on.
        """
        wanted = self.taxonomy.canonical(criterion.skill or "")
        need = int(criterion.min_level or DEFAULT_MIN_LEVEL)
        related = self.taxonomy.supporting(wanted)
        documents = _document_evidence(profile)
        best: tuple[float, Skill, bool] | None = None
        for s in profile.skills:
            name = self.taxonomy.canonical(s.name)
            if name != wanted and name not in related:
                continue
            direct = name == wanted
            score = _fit(level(s, self.levels), need) * _evidence_factor(s, documents)
            if not direct:
                score *= RELATED_FACTOR
            # Ties go to the skill itself, then to the first in the profile.
            if (
                best is None
                or score > best[0]
                or (score == best[0] and direct > best[2])
            ):
                best = (score, s, direct)
        if best is None:
            return CriterionScore(
                criterion_id=criterion.id,
                score=0.0,
                rationale=f"No {wanted} or related skill in the profile.",
            )
        score, skill, direct = best
        return CriterionScore(
            criterion_id=criterion.id,
            score=round(score, 2),
            rationale=_rationale(skill, wanted, need, direct, documents, self.levels),
            evidence_ids=_evidence(skill),
        )


def level(skill: Skill, levels: Levels = "blend") -> float:
    """Work out the level the baseline uses for a skill.

    Parameters
    ----------
    skill : Skill
        The candidate's skill.
    levels : {"blend", "own", "estimated"}, optional
        Which levels to use, by default both.

    Returns
    -------
    float
        From 1 to 5. "blend": the estimate and the candidate's own level weighted
        by the estimate's confidence, either alone if only one is there. "own"
        or "estimated": only that level. 1 (aware) if the level used is missing.
    """
    own = int(skill.self_level) if skill.self_level else None
    if levels == "own":
        return float(own or SkillLevel.AWARE)
    if levels == "estimated":
        return float(int(skill.estimate.level) if skill.estimate else SkillLevel.AWARE)
    if skill.estimate is None:
        return float(own or SkillLevel.AWARE)
    estimated = int(skill.estimate.level)
    if own is None:
        return float(estimated)
    c = skill.estimate.confidence
    return c * estimated + (1 - c) * own


def _fit(level: float, need: int) -> float:
    return min(1.0, level / need) ** 2


def _document_evidence(profile: Profile) -> set[UUID]:
    """Evidence from the candidate's documents, not their own interview statements."""
    statements = {s.id for s in profile.sources if s.kind == SourceKind.INTERVIEW}
    return {e.id for e in profile.evidence if e.source_id not in statements}


def _evidence(skill: Skill) -> list[UUID]:
    ids = list(skill.evidence_ids)
    if skill.estimate:
        ids += [i for i in skill.estimate.evidence_ids if i not in ids]
    return ids


def _evidence_factor(skill: Skill, documents: set[UUID]) -> float:
    n = sum(i in documents for i in _evidence(skill))
    return EVIDENCE_FACTORS[min(n, len(EVIDENCE_FACTORS) - 1)]


def _rationale(
    skill: Skill,
    wanted: str,
    need: int,
    direct: bool,
    documents: set[UUID],
    levels: Levels = "blend",
) -> str:
    own = f"own level {int(skill.self_level)}" if skill.self_level else "no own level"
    if skill.estimate:
        estimate = (
            f"estimated {int(skill.estimate.level)} "
            f"(confidence {skill.estimate.confidence:.2f})"
        )
    else:
        estimate = "not estimated"
    n = sum(i in documents for i in _evidence(skill))
    quotes = f"{n} quote{'s' if n != 1 else ''} from documents"
    via = "" if direct else f" (counts for {wanted}, discounted)"
    return (
        f"{skill.name}{via}: {own}, {estimate}, needs {need}; {quotes}; "
        f"level used {level(skill, levels):.1f}"
        f"{'' if levels == 'blend' else f' ({levels} only)'}."
    )


def own_and_estimated(
    profile: Profile, rubric: Rubric, taxonomy: Taxonomy | None = None
) -> tuple[float, float]:
    """Score a candidate with the baseline on their own levels, then on the estimate.

    Free and deterministic. Shown beside the ranking's total, which still sets the
    rank: how the candidate fits on their own rating, and on what their evidence
    supports.

    Parameters
    ----------
    profile : Profile
        The candidate's profile, with estimates.
    rubric : Rubric
        The rubric to score against.
    taxonomy : Taxonomy or None, optional
        By default `default_taxonomy()`.

    Returns
    -------
    tuple of float
        The own and the estimated total, each from 0 to 1 and rounded to 4
        places, weighted as `Match.total` is.
    """
    taxonomy = taxonomy or default_taxonomy()
    return (
        _total(BaselineScorer(taxonomy, "own").score(profile, rubric), rubric),
        _total(BaselineScorer(taxonomy, "estimated").score(profile, rubric), rubric),
    )


def _total(result: ScoringResult, rubric: Rubric) -> float:
    weights = {c.id: c.weight for c in rubric.criteria}
    scored = [(weights[s.criterion_id], s.score) for s in result.scores]
    weight = sum(w for w, _ in scored)
    return round(sum(w * s for w, s in scored) / weight, 4) if weight else 0.0
