"""Convert between profiles and the tables the app shows and edits.

Edits made in the app become a review or interview sheet and go through the same
`apply_review_sheet` / `apply_interview_sheet` as the command line, so both check
input the same way.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import yaml

from unapply.interview.questions import Question, Reason
from unapply.interview.sheet import export_interview_sheet
from unapply.schemas import Profile, SourceKind

LEVEL_NAMES = {1: "aware", 2: "basic", 3: "working", 4: "advanced", 5: "expert"}


def evidence_lines(profile: Profile, ids: list) -> list[str]:
    """Describe evidence as 'source: quote' lines.

    Parameters
    ----------
    profile : Profile
        The profile the evidence belongs to.
    ids : list of UUID
        Evidence ids.

    Returns
    -------
    list of str
        One line per piece of evidence; candidate statements are labelled
        "your statement".
    """
    kinds = {s.id: s.kind for s in profile.sources}
    evidence = {e.id: e for e in profile.evidence}
    lines = []
    for i in ids:
        e = evidence[i]
        kind = kinds[e.source_id]
        label = "your statement" if kind == SourceKind.INTERVIEW else kind.value
        lines.append(f"{label}: {' '.join(e.quote.split())}")
    return lines


def skill_rows(profile: Profile) -> list[dict[str, Any]]:
    """Rows for the review table of skills.

    Parameters
    ----------
    profile : Profile
        The profile to review.

    Returns
    -------
    list of dict
        One row per skill: keep, name, category, level, evidence.
    """
    return [
        {
            "keep": True,
            "name": s.name,
            "category": s.category.value if s.category else None,
            "level": int(s.self_level) if s.self_level else None,
            "evidence": " | ".join(evidence_lines(profile, s.evidence_ids)),
        }
        for s in profile.skills
    ]


def experience_rows(profile: Profile) -> list[dict[str, Any]]:
    """Rows for the review table of experiences.

    Parameters
    ----------
    profile : Profile
        The profile to review.

    Returns
    -------
    list of dict
        One row per experience: id, keep, title, organisation, start, end, summary.
    """
    return [
        {
            "id": str(x.id),
            "keep": True,
            "title": x.title,
            "organisation": x.organisation,
            "start": month(x.start),
            "end": month(x.end),
            "summary": x.summary,
        }
        for x in profile.experiences
    ]


def review_sheet(
    profile: Profile,
    *,
    headline: str,
    preferences: dict[str, Any],
    experiences: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    added: list[dict[str, Any]],
    approve: bool,
) -> str:
    """Build a review sheet from the app's edited tables.

    Parameters
    ----------
    profile : Profile
        The profile being reviewed.
    headline : str
        The edited headline.
    preferences : dict
        Edited preferences, with the keys of `Preferences`.
    experiences : list of dict
        Rows from `experience_rows`, as edited.
    skills : list of dict
        Rows from `skill_rows`, as edited.
    added : list of dict
        New skills with name, category, level and note. Rows with no name are
        ignored.
    approve : bool
        Whether the candidate approves the profile.

    Returns
    -------
    str
        A sheet for `apply_review_sheet`.
    """
    sheet = {
        "profile": str(profile.id),
        "approve": approve,
        "headline": headline,
        "preferences": preferences,
        "experiences": [
            {
                "id": r["id"],
                "keep": bool(r["keep"]),
                "title": _text(r["title"]),
                "organisation": _text(r["organisation"]),
                "start": _blank(r["start"]),
                "end": _blank(r["end"]),
                "summary": _text(r["summary"]),
            }
            for r in experiences
        ],
        "skills": [
            {
                "name": r["name"],
                "category": _blank(r["category"]),
                "level": _level(r["level"]),
                "keep": bool(r["keep"]),
            }
            for r in skills
        ],
        "add_skills": [
            {
                "name": _text(r.get("name")),
                "category": _blank(r.get("category")),
                "level": _level(r.get("level")),
                "note": _text(r.get("note")),
            }
            for r in added
            if _text(r.get("name"))
        ]
        or None,
    }
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False)


def finding_rows(profile: Profile) -> list[dict[str, Any]]:
    """Rows comparing the candidate's levels with the estimates.

    Parameters
    ----------
    profile : Profile
        An estimated profile.

    Returns
    -------
    list of dict
        One row per skill: skill, category, yours, estimate, confidence, finding,
        reason.
    """
    support = profile.claim_support
    finding = {}
    if support is not None:
        finding |= {n: "overclaim" for n in support.overclaims}
        finding |= {n: "unverified" for n in support.unverified}
        finding |= {n: "underclaim" for n in support.underclaims}
        finding |= {n: "only your statement" for n in support.unsupported_claims}
    return [
        {
            "skill": s.name,
            "category": s.category.value if s.category else "",
            "yours": int(s.self_level) if s.self_level else None,
            "estimate": int(s.estimate.level) if s.estimate else None,
            "confidence": s.estimate.confidence if s.estimate else None,
            "finding": finding.get(s.name, ""),
            "reason": s.estimate.rationale if s.estimate else "not estimated yet",
        }
        for s in profile.skills
    ]


def interview_sheet(
    profile: Profile, questions: list[dict[str, str]], answers: dict[str, str]
) -> str:
    """Build an answered interview sheet.

    Parameters
    ----------
    profile : Profile
        The profile the questions are about.
    questions : list of dict
        Questions with skill, reason and text, as stored by the workspace.
    answers : dict of str to str
        Answers by skill; missing or blank answers are skipped.

    Returns
    -------
    str
        A sheet for `apply_interview_sheet`.
    """
    asked = [Question(q["skill"], Reason(q["reason"]), q["text"]) for q in questions]
    sheet = yaml.safe_load(export_interview_sheet(profile, asked))
    for row in sheet["questions"]:
        row["answer"] = answers.get(row["skill"], "") or ""
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False)


def month(value: date | None) -> str:
    """Write a date as YYYY, or YYYY-MM when it isn't January; empty for None."""
    if value is None:
        return ""
    return str(value.year) if value.month == 1 else f"{value:%Y-%m}"


def _missing(value: Any) -> bool:  # noqa: ANN401
    return value is None or (isinstance(value, float) and math.isnan(value))


def _text(value: Any) -> str:  # noqa: ANN401
    return "" if _missing(value) else str(value).strip()


def _blank(value: Any) -> str | None:  # noqa: ANN401
    text = _text(value)
    return text or None


def _level(value: Any) -> int | None:  # noqa: ANN401
    if _missing(value) or value == "":
        return None
    return int(value)
