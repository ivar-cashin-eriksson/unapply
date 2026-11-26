"""The LLM scorer: a model scores each criterion, citing the candidate's evidence.

One call per candidate and job. The model sees the rubric's criteria and the
candidate's anonymised profile: headline, roles, skills with their own and estimated
levels, and every evidence quote with an id such as "E3". It never sees the
candidate's name or contact details (see `unapply.matching.anonymise`), nor where
their material is stored. Cited evidence ids are checked to belong to the candidate;
others are dropped.
"""

from __future__ import annotations

from importlib import resources
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, Field

from unapply.llm import StructuredLLM
from unapply.matching.anonymise import redact
from unapply.matching.scoring import ScoringResult
from unapply.schemas import CriterionScore, Profile, Rubric, SourceKind

# The models below are the schema the model answers in. Their field descriptions are
# sent to the model, so they are written as instructions.


class ScoredCriterion(BaseModel):
    """The model's score for one criterion."""

    criterion: str = Field(description="The criterion's id, such as 'C2'.")
    score: float = Field(
        description="From 0 (not met, or no evidence) to 1 (fully met), in steps of "
        "0.05."
    )
    rationale: str = Field(
        description="One or two sentences for the recruiter: what the evidence shows "
        "and what is missing. No names."
    )
    evidence: list[str] = Field(
        description="Ids of the quotes the score rests on, such as 'E3'. Empty if "
        "there is no evidence."
    )


class CriterionScores(BaseModel):
    """The full answer the model gives."""

    criteria: list[ScoredCriterion]


class LLMScorer:
    """Score criteria with a model, from the candidate's anonymised profile.

    Parameters
    ----------
    llm : StructuredLLM
        The model, or a replay of its answer.
    names : list of str or None, optional
        Names to remove from everything sent, such as the candidate's name or
        GitHub username, if known.
    """

    name = "llm"

    def __init__(self, llm: StructuredLLM, names: list[str] | None = None) -> None:
        self.llm = llm
        self.model = llm.model
        self.names = names or []

    def score(self, profile: Profile, rubric: Rubric) -> ScoringResult:
        """Score every criterion of the rubric with one model call.

        Parameters
        ----------
        profile : Profile
            The candidate's profile.
        rubric : Rubric
            The rubric to score against.

        Returns
        -------
        ScoringResult
            One score per criterion the model scored validly, in rubric order, and
            problems with its answer.

        Raises
        ------
        LLMError
            If the model gives no usable answer.
        """
        prompt, evidence, criteria = render_match_prompt(profile, rubric, self.names)
        system = resources.files(__package__).joinpath("prompts/score_match.md")
        answer = self.llm.parse(
            system=system.read_text(encoding="utf-8"),
            prompt=prompt,
            output_type=CriterionScores,
        )
        return apply_scores(rubric, answer, evidence, criteria)


def render_match_prompt(
    profile: Profile, rubric: Rubric, names: list[str] | None = None
) -> tuple[str, dict[str, UUID], dict[str, UUID]]:
    """Render the criteria and the anonymised candidate for the model.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    rubric : Rubric
        The rubric; its hard filters aren't sent, as they are checked in code.
    names : list of str or None, optional
        Names to remove from every text sent.

    Returns
    -------
    str
        The prompt.
    dict of str to UUID
        Evidence id in the prompt, such as "E3", to `Evidence.id`.
    dict of str to UUID
        Criterion id in the prompt, such as "C2", to `Criterion.id`.
    """
    kinds = {s.id: s.kind for s in profile.sources}
    evidence_labels = {e.id: f"E{i}" for i, e in enumerate(profile.evidence, 1)}
    criterion_labels = {c.id: f"C{i}" for i, c in enumerate(rubric.criteria, 1)}

    def text(value: str) -> str:
        return escape(" ".join(redact(value, names).split()))

    def cited(ids: list[UUID]) -> str:
        return " ".join(evidence_labels[i] for i in ids if i in evidence_labels)

    lines = ["<criteria>"]
    for c in rubric.criteria:
        attributes = f"id={quoteattr(criterion_labels[c.id])} kind={quoteattr(c.kind)}"
        if c.skill:
            attributes += f" skill={quoteattr(c.skill)}"
        if c.min_level:
            attributes += f' min_level="{int(c.min_level)}"'
        attributes += f' weight="{c.weight:g}"'
        lines.append(f"<criterion {attributes}>{escape(c.description)}</criterion>")
    lines += ["</criteria>", "", "<candidate>"]
    lines.append(f"<headline>{text(profile.headline)}</headline>")
    lines.append("<roles>")
    for x in profile.experiences:
        start = f"{x.start:%Y-%m}" if x.start else "?"
        end = f"{x.end:%Y-%m}" if x.end else "present"
        lines.append(
            f"<role from={quoteattr(start)} to={quoteattr(end)} "
            f"evidence={quoteattr(cited(x.evidence_ids))}>"
            f"{text(x.title)}, {text(x.organisation)}. {text(x.summary)}"
            f"{' Skills: ' + text(', '.join(x.skills)) + '.' if x.skills else ''}"
            "</role>"
        )
    lines += ["</roles>", "<skills>"]
    for s in profile.skills:
        attributes = f"name={quoteattr(s.name)}"
        if s.self_level:
            attributes += f' own_level="{int(s.self_level)}"'
        if s.estimate:
            attributes += (
                f' estimated_level="{int(s.estimate.level)}"'
                f' confidence="{s.estimate.confidence:.2f}"'
            )
        attributes += f" evidence={quoteattr(cited(s.evidence_ids))}"
        lines.append(f"<skill {attributes}/>")
    lines += ["</skills>", "<evidence>"]
    for e in profile.evidence:
        kind = kinds[e.source_id]
        source = "candidate statement" if kind == SourceKind.INTERVIEW else kind.value
        lines.append(
            f"<quote id={quoteattr(evidence_labels[e.id])} source={quoteattr(source)}>"
            f"{text(e.quote)}</quote>"
        )
    lines += ["</evidence>", "</candidate>"]
    return (
        "\n".join(lines),
        {v: k for k, v in evidence_labels.items()},
        {v: k for k, v in criterion_labels.items()},
    )


def apply_scores(
    rubric: Rubric,
    answer: CriterionScores,
    evidence: dict[str, UUID],
    criteria: dict[str, UUID],
) -> ScoringResult:
    """Check the model's answer and turn it into criterion scores.

    Parameters
    ----------
    rubric : Rubric
        The rubric that was scored.
    answer : CriterionScores
        The model's answer.
    evidence : dict of str to UUID
        Evidence ids from the prompt, as returned by `render_match_prompt`.
    criteria : dict of str to UUID
        Criterion ids from the prompt, as returned by `render_match_prompt`.

    Returns
    -------
    ScoringResult
        Scores in rubric order. Criteria the model skipped get no score (and
        `Match.total` averages over the others); scores outside 0 to 1 are
        clipped; cited ids that aren't the candidate's evidence are dropped. Each
        is listed in `problems`.
    """
    problems: list[str] = []
    by_label: dict[str, ScoredCriterion] = {}
    for scored in answer.criteria:
        if scored.criterion not in criteria:
            problems.append(f"{scored.criterion}: not a criterion; ignored")
        elif scored.criterion in by_label:
            problems.append(f"{scored.criterion}: scored twice; kept the first")
        else:
            by_label[scored.criterion] = scored
    labels = {v: k for k, v in criteria.items()}
    scores = []
    for c in rubric.criteria:
        label = labels[c.id]
        scored = by_label.get(label)
        if scored is None:
            problems.append(f"{label} ({c.description}): not scored")
            continue
        score = scored.score
        if not 0.0 <= score <= 1.0:
            problems.append(f"{label}: score {score} is outside 0-1; clipped")
            score = min(max(score, 0.0), 1.0)
        unknown = [e for e in scored.evidence if e not in evidence]
        if unknown:
            problems.append(f"{label}: cited {unknown}, which aren't the candidate's")
        ids = list(dict.fromkeys(evidence[e] for e in scored.evidence if e in evidence))
        scores.append(
            CriterionScore(
                criterion_id=c.id,
                score=round(score, 2),
                rationale=scored.rationale.strip(),
                evidence_ids=ids,
            )
        )
    return ScoringResult(scores=scores, problems=problems)
