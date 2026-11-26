"""Extract a rubric from a job ad with a language model.

The model answers in the `Extracted*` schemas below. Every criterion quotes the ad;
`extract_job` checks each quote against the ad text, drops criteria whose quote isn't
found, normalises the rest and returns a draft `Job` for the recruiter to review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Literal

from pydantic import BaseModel, Field

from unapply.ingest.extract import canonical_skill, normalise_quote
from unapply.llm import StructuredLLM
from unapply.schemas import (
    Criterion,
    CriterionKind,
    HardFilters,
    Job,
    Rubric,
    SkillLevel,
    WorkMode,
)

# Weights the app and review sheet use: 1 (minor) to 5 (essential).
MIN_WEIGHT, MAX_WEIGHT = 1, 5

# The Extracted* models are the schema the model answers in. Their field
# descriptions are sent to the model, so they are written as instructions.


class ExtractedFilters(BaseModel):
    """Hard filters as the model extracted them."""

    locations: list[str] = Field(description="Cities or regions, such as 'Copenhagen'.")
    work_modes: list[Literal["onsite", "hybrid", "remote"]]
    required_work_permits: list[str] = Field(description="ISO country codes, or 'EU'.")
    min_years_experience: int | None


class ExtractedCriterion(BaseModel):
    """A criterion as the model extracted it."""

    kind: Literal["must_have", "nice_to_have"]
    description: str
    skill: str | None
    min_level: int | None = Field(description="1 to 5, or null.")
    weight: int = Field(description="1 (minor) to 5 (essential).")
    quote: str = Field(description="Verbatim words from the ad.")


class ExtractedJob(BaseModel):
    """The full answer the model gives."""

    company: str
    title: str
    hard_filters: ExtractedFilters
    criteria: list[ExtractedCriterion]


@dataclass
class RubricResult:
    """A draft job and what was dropped while building it.

    Parameters
    ----------
    job : Job
        The job with its draft rubric, not yet approved.
    dropped : list of str
        Criteria dropped because their quote isn't in the ad, or because they
        repeat another criterion.
    """

    job: Job
    dropped: list[str] = field(default_factory=list)


def extract_job(
    ad_text: str,
    llm: StructuredLLM,
    *,
    company: str | None = None,
    title: str | None = None,
) -> RubricResult:
    """Extract a draft rubric from a job ad.

    Parameters
    ----------
    ad_text : str
        The job ad as posted. Must not be empty.
    llm : StructuredLLM
        The model to extract with.
    company : str or None, optional
        Company name, overriding what the model reads from the ad.
    title : str or None, optional
        Job title, overriding what the model reads from the ad.

    Returns
    -------
    RubricResult
        The draft job and anything dropped.

    Raises
    ------
    ValueError
        If `ad_text` is empty.
    """
    if not ad_text.strip():
        raise ValueError("the job ad is empty")
    system = resources.files(__package__).joinpath("prompts/extract_rubric.md")
    answer = llm.parse(
        system=system.read_text(encoding="utf-8"),
        prompt=f"<job_ad>\n{ad_text}\n</job_ad>",
        output_type=ExtractedJob,
    )
    return build_job(answer, ad_text, company=company, title=title)


def build_job(
    answer: ExtractedJob,
    ad_text: str,
    *,
    company: str | None = None,
    title: str | None = None,
) -> RubricResult:
    """Check the model's answer against the ad and turn it into a `Job`.

    Parameters
    ----------
    answer : ExtractedJob
        The model's answer.
    ad_text : str
        The ad it was given.
    company : str or None, optional
        Company name, overriding the model's.
    title : str or None, optional
        Job title, overriding the model's.

    Returns
    -------
    RubricResult
        The job, with criteria whose quote is in the ad. Skills are canonical,
        levels outside 1 to 5 are dropped and weights are clamped to 1 to 5.
    """
    ad = normalise_quote(ad_text)
    dropped: list[str] = []
    seen: set[tuple[str, str]] = set()
    criteria: list[Criterion] = []
    for c in answer.criteria:
        description = " ".join(c.description.split())
        if not c.quote.strip() or normalise_quote(c.quote) not in ad:
            dropped.append(f"{description} (quote not found in the ad)")
            continue
        skill = canonical_skill(c.skill) if c.skill and c.skill.strip() else None
        key = (c.kind, skill or description.lower())
        if key in seen:
            dropped.append(f"{description} (repeats another criterion)")
            continue
        seen.add(key)
        criteria.append(
            Criterion(
                kind=CriterionKind(c.kind),
                description=description,
                skill=skill,
                min_level=SkillLevel(c.min_level)
                if c.min_level in range(1, 6)
                else None,
                weight=float(min(max(c.weight, MIN_WEIGHT), MAX_WEIGHT)),
                source_quote=" ".join(c.quote.split()),
            )
        )
    f = answer.hard_filters
    years = f.min_years_experience
    rubric = Rubric(
        hard_filters=HardFilters(
            locations=[x.strip() for x in f.locations if x.strip()],
            work_modes=[WorkMode(m) for m in dict.fromkeys(f.work_modes)],
            required_work_permits=[
                x.strip() for x in f.required_work_permits if x.strip()
            ],
            min_years_experience=years if years is not None and years >= 0 else None,
        ),
        criteria=criteria,
    )
    job = Job(
        company=(company or answer.company).strip(),
        title=(title or answer.title).strip(),
        ad_text=ad_text,
        rubric=rubric,
    )
    return RubricResult(job=job, dropped=dropped)
