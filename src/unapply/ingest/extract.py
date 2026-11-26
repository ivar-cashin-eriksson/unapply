"""Extract a `Profile` from source documents with a language model.

The model answers in the `Extracted*` schemas below, which refer to sources by short
ids and quote them verbatim. `extract_profile` then checks every quote against the
source text, keeps only the quotes it finds, and builds the `Profile`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from typing import Literal

from pydantic import BaseModel, Field

from unapply.ingest.documents import SourceDocument
from unapply.llm import StructuredLLM
from unapply.schemas import (
    Evidence,
    Experience,
    Preferences,
    Profile,
    Skill,
    SkillCategory,
    SkillLevel,
    WorkMode,
)

# The Extracted* models are the schema the model answers in. Their field
# descriptions are sent to the model, so they are written as instructions.


class ExtractedQuote(BaseModel):
    """A verbatim quote from one source."""

    source: str = Field(description="Source id, such as 'S1'.")
    quote: str = Field(description="Verbatim text copied from that source.")


class ExtractedExperience(BaseModel):
    """A job, project or education entry as the model extracted it."""

    title: str
    organisation: str
    start: str | None = Field(description="'YYYY-MM' or 'YYYY', or null if unknown.")
    end: str | None = Field(
        description="'YYYY-MM' or 'YYYY'; null if current or unknown."
    )
    summary: str = Field(
        description="What the candidate did, in one to three sentences."
    )
    skills: list[str] = Field(description="Names of skills used in this role.")
    evidence: list[ExtractedQuote]


class ExtractedSkill(BaseModel):
    """A skill as the model extracted it."""

    name: str = Field(
        description=(
            "The most specific conventional name the material supports, such as "
            "'sparse gaussian processes' rather than 'gaussian processes'."
        )
    )
    category: Literal[
        "technology", "method", "domain", "soft_skill", "language", "certification"
    ]
    self_level: int | None = Field(
        description=(
            "Only if the candidate states a level themselves: 1 aware, 2 basic, "
            "3 working, 4 advanced, 5 expert or native. Otherwise null."
        )
    )
    evidence: list[ExtractedQuote]


class ExtractedPreferences(BaseModel):
    """Job preferences stated in the material."""

    locations: list[str] = Field(description="Cities or regions, such as 'Copenhagen'.")
    work_modes: list[Literal["onsite", "hybrid", "remote"]]
    work_permits: list[str] = Field(description="ISO country codes, or 'EU'.")
    dealbreakers: list[str]


class ExtractedProfile(BaseModel):
    """The full answer the model gives."""

    headline: str = Field(
        description="One line describing the candidate professionally, without names."
    )
    experiences: list[ExtractedExperience]
    skills: list[ExtractedSkill]
    preferences: ExtractedPreferences


@dataclass
class ExtractionResult:
    """A profile and what was dropped while building it.

    Parameters
    ----------
    profile : Profile
        The draft profile, not yet approved by the candidate.
    rejected_quotes : list of ExtractedQuote
        Quotes that were not found in the source they cite.
    unsupported : list of str
        Experiences and skills dropped because none of their quotes were found.
    """

    profile: Profile
    rejected_quotes: list[ExtractedQuote] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


def render_sources(documents: list[SourceDocument]) -> str:
    """Render documents as `<source>` elements with ids S1, S2, ...

    Parameters
    ----------
    documents : list of SourceDocument
        The candidate's material.

    Returns
    -------
    str
        The prompt text listing every document.
    """
    return "\n\n".join(
        f'<source id="S{i}" kind="{d.source.kind}" name="{d.name}">\n{d.text}\n</source>'
        for i, d in enumerate(documents, start=1)
    )


def extract_profile(
    documents: list[SourceDocument], llm: StructuredLLM
) -> ExtractionResult:
    """Extract a draft profile from a candidate's documents.

    Parameters
    ----------
    documents : list of SourceDocument
        The candidate's material. Must not be empty.
    llm : StructuredLLM
        The model to extract with.

    Returns
    -------
    ExtractionResult
        The draft profile, with every claim backed by a quote found in its source,
        and a record of what was dropped.

    Raises
    ------
    ValueError
        If `documents` is empty.
    """
    if not documents:
        raise ValueError("no documents to extract from")
    system = resources.files(__package__).joinpath("prompts/extract_profile.md")
    extracted = llm.parse(
        system=system.read_text(encoding="utf-8"),
        prompt=render_sources(documents),
        output_type=ExtractedProfile,
    )
    return build_profile(extracted, documents)


def build_profile(
    extracted: ExtractedProfile, documents: list[SourceDocument]
) -> ExtractionResult:
    """Check the model's quotes and turn its answer into a `Profile`.

    Parameters
    ----------
    extracted : ExtractedProfile
        The model's answer.
    documents : list of SourceDocument
        The documents it was given, in the same order, so `S1` is the first.

    Returns
    -------
    ExtractionResult
        The profile and what was dropped. Experiences and skills with no verified
        quote are dropped; skills with the same canonical name are merged.
    """
    by_id = {f"S{i}": d for i, d in enumerate(documents, start=1)}
    normalised = {sid: _normalise(d.text) for sid, d in by_id.items()}
    evidence: dict[tuple[str, str], Evidence] = {}
    result = ExtractionResult(profile=Profile())

    def verified(quotes: list[ExtractedQuote]) -> list[Evidence]:
        found: list[Evidence] = []
        for q in quotes:
            text = normalised.get(q.source)
            if text is None or not q.quote.strip() or _normalise(q.quote) not in text:
                result.rejected_quotes.append(q)
                continue
            key = (q.source, _normalise(q.quote))
            if key not in evidence:
                evidence[key] = Evidence(
                    source_id=by_id[q.source].source.id, quote=q.quote.strip()
                )
            found.append(evidence[key])
        return found

    experiences: list[Experience] = []
    for x in extracted.experiences:
        ev = verified(x.evidence)
        if not ev:
            result.unsupported.append(f"experience: {x.title} at {x.organisation}")
            continue
        experiences.append(
            Experience(
                title=x.title,
                organisation=x.organisation,
                start=_parse_date(x.start),
                end=_parse_date(x.end),
                summary=x.summary,
                skills=sorted({canonical_skill(s) for s in x.skills}),
                evidence_ids=[e.id for e in ev],
            )
        )

    skills: dict[str, Skill] = {}
    for s in extracted.skills:
        name = canonical_skill(s.name)
        ev = verified(s.evidence)
        if not ev:
            result.unsupported.append(f"skill: {s.name}")
            continue
        level = SkillLevel(s.self_level) if s.self_level in range(1, 6) else None
        if name in skills:
            existing = skills[name]
            ids = existing.evidence_ids + [
                e.id for e in ev if e.id not in existing.evidence_ids
            ]
            existing.evidence_ids = ids
            existing.self_level = existing.self_level or level
        else:
            skills[name] = Skill(
                name=name,
                category=SkillCategory(s.category),
                self_level=level,
                evidence_ids=[e.id for e in ev],
            )

    p = extracted.preferences
    result.profile = Profile(
        headline=extracted.headline,
        sources=[d.source for d in documents],
        evidence=list(evidence.values()),
        experiences=experiences,
        skills=sorted(skills.values(), key=lambda s: s.name),
        preferences=Preferences(
            locations=p.locations,
            work_modes=[WorkMode(m) for m in p.work_modes],
            work_permits=p.work_permits,
            dealbreakers=p.dealbreakers,
        ),
    )
    return result


def canonical_skill(name: str) -> str:
    """Normalise a skill name: lowercase, with single spaces.

    Parameters
    ----------
    name : str
        Skill name as written, such as " Scikit-Learn ".

    Returns
    -------
    str
        Canonical name, such as "scikit-learn".
    """
    return " ".join(name.lower().split())


def _normalise(text: str) -> str:
    """Normalise text for quote matching: Unicode, case, quotes, dashes, whitespace."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[‘’‚′]", "'", text)
    text = re.sub(r"[“”„″]", '"', text)
    text = re.sub(r"[‐‑‒–—―−]", "-", text)
    return " ".join(text.split())


def _parse_date(value: str | None) -> date | None:
    """Parse 'YYYY-MM' or 'YYYY' to the first day of that month or year."""
    if not value:
        return None
    m = re.fullmatch(r"\s*(\d{4})(?:-(\d{1,2}))?\s*", value)
    if not m:
        return None
    month = int(m.group(2)) if m.group(2) else 1
    return date(int(m.group(1)), month if 1 <= month <= 12 else 1, 1)
