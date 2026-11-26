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
"""

from __future__ import annotations

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


class BaselineScorer:
    """Score criteria from skill levels and evidence counts, without a model.

    Parameters
    ----------
    taxonomy : Taxonomy or None, optional
        For skills whose evidence counts for a criterion's skill, by default
        `default_taxonomy()`.
    """

    model = BASELINE_MODEL

    def __init__(self, taxonomy: Taxonomy | None = None) -> None:
        self.taxonomy = taxonomy or default_taxonomy()

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
            score = _fit(level(s), need) * _evidence_factor(s, documents)
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
            rationale=_rationale(skill, wanted, need, direct, documents),
            evidence_ids=_evidence(skill),
        )


def level(skill: Skill) -> float:
    """Work out the level the baseline uses for a skill.

    Parameters
    ----------
    skill : Skill
        The candidate's skill.

    Returns
    -------
    float
        From 1 to 5: the estimate and the candidate's own level weighted by the
        estimate's confidence; either alone if only one is there; 1 (aware) if
        neither is.
    """
    own = int(skill.self_level) if skill.self_level else None
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
    skill: Skill, wanted: str, need: int, direct: bool, documents: set[UUID]
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
        f"level used {level(skill):.1f}."
    )
