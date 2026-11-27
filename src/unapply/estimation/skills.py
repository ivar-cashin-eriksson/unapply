"""Estimate the level of every skill in a profile from its evidence.

The model sees each skill's quotes and the candidate's roles, but not the candidate's
own levels, so it can't anchor on them. It answers in `SkillEstimates`; this module
checks the answer and records it as each skill's `SkillEstimate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, Field

from unapply.dates import format_partial_date
from unapply.llm import StructuredLLM
from unapply.schemas import Profile, SkillEstimate, SkillLevel, SourceKind

# Estimates resting only on the candidate's own statements can't be confident.
STATEMENT_ONLY_MAX_CONFIDENCE = 0.3

# The models below are the schema the model answers in. Their field descriptions are
# sent to the model, so they are written as instructions.


class EstimatedSkill(BaseModel):
    """The model's estimate for one skill."""

    skill: str = Field(description="The skill's name exactly as given.")
    level: int = Field(description="1 aware, 2 basic, 3 working, 4 advanced, 5 expert.")
    confidence: float = Field(description="From 0 (guess) to 1 (certain).")
    rationale: str = Field(description="One or two sentences for the candidate.")
    evidence: list[str] = Field(description="Ids of the quotes used, such as 'E3'.")


class SkillEstimates(BaseModel):
    """The full answer the model gives."""

    skills: list[EstimatedSkill]


@dataclass
class EstimationResult:
    """A profile with estimates, and what went wrong on the way.

    Parameters
    ----------
    profile : Profile
        The profile, with `estimate` set on every skill the model estimated.
    problems : list of str
        Skills the model skipped, invented or estimated twice, levels outside the
        scale, and quotes cited for the wrong skill. Empty when all went well.
    """

    profile: Profile
    problems: list[str] = field(default_factory=list)


def render_estimation_prompt(
    profile: Profile, names: set[str] | None = None
) -> tuple[str, dict[str, UUID]]:
    """Render the roles and each skill's evidence for the model.

    Parameters
    ----------
    profile : Profile
        The profile to estimate.
    names : set of str or None, optional
        Only these skills; by default all.

    Returns
    -------
    str
        The prompt. It does not include the candidate's own levels.
    dict of str to UUID
        Evidence id in the prompt, such as "E3", to `Evidence.id`.
    """
    kinds = {s.id: s.kind for s in profile.sources}
    evidence = {e.id: e for e in profile.evidence}
    ids: dict[UUID, str] = {}
    for e in profile.evidence:
        ids[e.id] = f"E{len(ids) + 1}"

    lines = [render_roles(profile), "", "<skills>"]
    for s in _targets(profile, names):
        category = s.category.value if s.category else "unknown"
        lines.append(f"<skill name={quoteattr(s.name)} category={quoteattr(category)}>")
        for i in s.evidence_ids:
            source = kinds[evidence[i].source_id]
            label = "candidate statement" if source == SourceKind.INTERVIEW else source
            quote = " ".join(evidence[i].quote.split())
            # Interview answers keep their question as the locator, for context.
            asked = (
                f" question={quoteattr(evidence[i].locator)}"
                if source == SourceKind.INTERVIEW and evidence[i].locator
                else ""
            )
            lines.append(
                f'  <evidence id="{ids[i]}" source="{label}"{asked}>'
                f"{escape(quote)}</evidence>"
            )
        lines.append("</skill>")
    lines.append("</skills>")
    return "\n".join(lines), {v: k for k, v in ids.items()}


def render_roles(profile: Profile) -> str:
    """Render the candidate's roles, with dates and skills, as a `<roles>` element.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.

    Returns
    -------
    str
        One line per experience, such as "- Data Scientist, Acme, 2019-08 to
        present. Skills used: python."
    """
    lines = ["<roles>"]
    for x in profile.experiences:
        start = format_partial_date(x.start, x.start_precision) or "?"
        end = format_partial_date(x.end, x.end_precision) or "present"
        skills = f" Skills used: {', '.join(x.skills)}." if x.skills else ""
        lines.append(
            f"- {escape(x.title)}, {escape(x.organisation)}, {start} to {end}."
            f"{escape(skills)}"
        )
    lines.append("</roles>")
    return "\n".join(lines)


def estimate_skills(
    profile: Profile, llm: StructuredLLM, names: set[str] | None = None
) -> EstimationResult:
    """Estimate skill levels from their evidence.

    Parameters
    ----------
    profile : Profile
        The profile to estimate. Estimates of the chosen skills are replaced.
    llm : StructuredLLM
        The model to estimate with.
    names : set of str or None, optional
        Only estimate these skills and leave the others as they are; by default all.
        Re-estimating only what changed keeps other estimates from drifting between
        runs, and costs less.

    Returns
    -------
    EstimationResult
        The profile with estimates and any problems with the model's answer. Skills
        the model didn't estimate validly keep no estimate.
    """
    prompt, by_label = render_estimation_prompt(profile, names)
    system = resources.files(__package__).joinpath("prompts/estimate_skills.md")
    answer = llm.parse(
        system=system.read_text(encoding="utf-8"),
        prompt=prompt,
        output_type=SkillEstimates,
    )
    return apply_estimates(profile, answer, by_label, llm.model, names)


def skills_without_estimate(profile: Profile) -> set[str]:
    """Names of skills that have no estimate, such as new or newly answered ones.

    Parameters
    ----------
    profile : Profile
        The profile.

    Returns
    -------
    set of str
        Skill names.
    """
    return {s.name for s in profile.skills if s.estimate is None}


def apply_estimates(
    profile: Profile,
    answer: SkillEstimates,
    by_label: dict[str, UUID],
    model: str,
    names: set[str] | None = None,
) -> EstimationResult:
    """Check the model's answer and record it on the profile's skills.

    Parameters
    ----------
    profile : Profile
        The profile that was estimated.
    answer : SkillEstimates
        The model's answer.
    by_label : dict of str to UUID
        Evidence ids from the prompt, as returned by `render_estimation_prompt`.
    model : str
        Model that produced the answer, recorded on each estimate.
    names : set of str or None, optional
        The skills that were estimated; by default all. Others are left as they are.

    Returns
    -------
    EstimationResult
        The profile with estimates, and problems found in the answer.
    """
    problems: list[str] = []
    kinds = {s.id: s.kind for s in profile.sources}
    source_of = {e.id: kinds[e.source_id] for e in profile.evidence}
    by_name: dict[str, EstimatedSkill] = {}
    for est in answer.skills:
        if est.skill in by_name:
            problems.append(f"{est.skill}: estimated twice; kept the first")
        else:
            by_name[est.skill] = est
    targets = {s.name for s in _targets(profile, names)}
    problems += [f"{n}: not asked for; ignored" for n in by_name if n not in targets]

    skills = []
    for s in profile.skills:
        if s.name not in targets:
            skills.append(s)
            continue
        est = by_name.get(s.name)
        if est is None:
            problems.append(f"{s.name}: not estimated")
            skills.append(s.model_copy(update={"estimate": None}))
            continue
        if not 1 <= est.level <= 5:
            problems.append(f"{s.name}: level {est.level} is outside 1-5; not kept")
            skills.append(s.model_copy(update={"estimate": None}))
            continue
        cited = [by_label.get(label) for label in est.evidence]
        wrong = [
            label
            for label, i in zip(est.evidence, cited, strict=True)
            if i not in s.evidence_ids
        ]
        if wrong:
            problems.append(f"{s.name}: cited {wrong}, which aren't its evidence")
        evidence_ids = [i for i in cited if i in s.evidence_ids]
        confidence = min(max(est.confidence, 0.0), 1.0)
        if s.evidence_ids and all(
            source_of[i] == SourceKind.INTERVIEW for i in s.evidence_ids
        ):
            confidence = min(confidence, STATEMENT_ONLY_MAX_CONFIDENCE)
        estimate = SkillEstimate(
            level=SkillLevel(est.level),
            confidence=round(confidence, 2),
            rationale=est.rationale.strip(),
            evidence_ids=evidence_ids,
            model=model,
        )
        skills.append(s.model_copy(update={"estimate": estimate}))
    return EstimationResult(
        profile=profile.model_copy(update={"skills": skills}), problems=problems
    )


def _targets(profile: Profile, names: set[str] | None) -> list:
    return [s for s in profile.skills if names is None or s.name in names]
