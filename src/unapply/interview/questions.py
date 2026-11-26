"""Choose what to ask the candidate (rules), and word the questions (a model).

Rules decide which skills to ask about, in what order and how many, so the choice is
predictable and explainable. A model writes each question so it fits what the
documents already show; a template question stands in for any skill the model
skips, so a round never fails because of the model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, Field

from unapply.estimation.skills import render_roles
from unapply.llm import StructuredLLM
from unapply.schemas import Profile, SourceKind

log = logging.getLogger(__name__)

MAX_QUESTIONS = 8
# Marks interview sources, so the same skill isn't asked about twice.
INTERVIEW_URI = "interview"


class Reason(StrEnum):
    """Why a skill is asked about, in the order they are asked."""

    UNVERIFIED = "unverified"  # The documents don't show the level either way
    STATEMENT_ONLY = "statement_only"  # Only the candidate's own statement backs it
    OVERCLAIM = "overclaim"  # Rated higher than the documents show


# Shown to the candidate. Deliberately neutral: the assessment behind the choice of
# question (an unverified level, an overclaim) is not shown to candidates.
WHY = {
    Reason.UNVERIFIED: "Your documents say little about how you've used this.",
    Reason.STATEMENT_ONLY: "Nothing in your documents shows this yet.",
    Reason.OVERCLAIM: "Your documents say little about how you've used this.",
}

TEMPLATES = {
    Reason.UNVERIFIED: (
        "Your documents list {skill} but don't show how you've used it. What is the "
        "most substantial work you've done with {skill}: what did you do, at roughly "
        "what scale, and in which role?"
    ),
    Reason.STATEMENT_ONLY: (
        "Nothing in your documents shows {skill} yet. Where have you used it, what "
        "did you do with it, and for how long?"
    ),
    Reason.OVERCLAIM: (
        "Your documents show less {skill} than your own rating. Is there work with "
        "{skill} they leave out? Describe one example: what you did, at what scale "
        "and in which role."
    ),
}


@dataclass(frozen=True)
class Question:
    """A question about one skill.

    Parameters
    ----------
    skill : str
        The skill's name in the profile.
    reason : Reason
        Why it is asked about.
    text : str
        The question.
    """

    skill: str
    reason: Reason
    text: str


def select_topics(
    profile: Profile, limit: int = MAX_QUESTIONS
) -> list[tuple[str, Reason]]:
    """Choose which skills to ask about.

    Unverified skills come first, then skills backed only by the candidate's own
    statement, then overclaims; within each, the skills the candidate rates highest.
    Skills already asked about in an earlier interview are skipped.

    Parameters
    ----------
    profile : Profile
        A profile with claim support (see `unapply estimate`).
    limit : int, optional
        The most questions to ask, by default `MAX_QUESTIONS`.

    Returns
    -------
    list of (str, Reason)
        Skill names with the reason for asking, in the order to ask them.

    Raises
    ------
    ValueError
        If the profile has no claim support yet.
    """
    support = profile.claim_support
    if support is None:
        raise ValueError(
            "the profile has no claim support; run `unapply estimate` first"
        )
    asked = _already_asked(profile)
    topics: list[tuple[str, Reason]] = []
    for reason, names in [
        (Reason.UNVERIFIED, support.unverified),
        (Reason.STATEMENT_ONLY, support.unsupported_claims),
        (Reason.OVERCLAIM, support.overclaims),
    ]:
        candidates = [n for n in names if n not in asked and profile.skill(n)]
        candidates.sort(key=lambda n: -int(profile.skill(n).self_level or 0))
        topics += [(n, reason) for n in candidates]
    return topics[:limit]


class WrittenQuestion(BaseModel):
    """One question the model wrote. Field descriptions are sent to the model."""

    skill: str = Field(description="The skill's name exactly as given.")
    question: str


class WrittenQuestions(BaseModel):
    """The full answer the model gives."""

    questions: list[WrittenQuestion]


def write_questions(
    profile: Profile, topics: list[tuple[str, Reason]], llm: StructuredLLM
) -> list[Question]:
    """Word one question per topic, with the model, falling back to templates.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    topics : list of (str, Reason)
        What to ask about, from `select_topics`.
    llm : StructuredLLM
        The model that writes the questions.

    Returns
    -------
    list of Question
        One question per topic, in the same order. Topics the model skipped get a
        template question.
    """
    if not topics:
        return []
    system = resources.files(__package__).joinpath("prompts/write_questions.md")
    answer = llm.parse(
        system=system.read_text(encoding="utf-8"),
        prompt=render_topics(profile, topics),
        output_type=WrittenQuestions,
    )
    written = {}
    for q in answer.questions:
        if q.question.strip() and q.skill not in written:
            written[q.skill] = q.question.strip()
    questions = []
    for skill, reason in topics:
        text = written.get(skill)
        if text is None:
            log.warning("no question written for %s; using a template", skill)
            text = TEMPLATES[reason].format(skill=skill)
        questions.append(Question(skill=skill, reason=reason, text=text))
    return questions


def render_topics(profile: Profile, topics: list[tuple[str, Reason]]) -> str:
    """Render the roles and each topic's skill, reason and evidence for the model.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    topics : list of (str, Reason)
        What to ask about.

    Returns
    -------
    str
        The prompt.
    """
    kinds = {s.id: s.kind for s in profile.sources}
    evidence = {e.id: e for e in profile.evidence}
    lines = [render_roles(profile), "", "<skills>"]
    for name, reason in topics:
        s = profile.skill(name)
        lines.append(f"<skill name={quoteattr(name)} reason={quoteattr(reason.value)}>")
        for i in s.evidence_ids:
            kind = kinds[evidence[i].source_id]
            label = "candidate statement" if kind == SourceKind.INTERVIEW else kind
            quote = escape(" ".join(evidence[i].quote.split()))
            lines.append(f'  <evidence source="{label}">{quote}</evidence>')
        lines.append("</skill>")
    lines.append("</skills>")
    return "\n".join(lines)


def _already_asked(profile: Profile) -> set[str]:
    interviews = {
        s.id
        for s in profile.sources
        if s.kind == SourceKind.INTERVIEW and s.uri == INTERVIEW_URI
    }
    from_interview = {e.id for e in profile.evidence if e.source_id in interviews}
    return {s.name for s in profile.skills if from_interview & set(s.evidence_ids)}
