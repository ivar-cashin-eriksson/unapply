"""Convert between profiles and the tables the app shows and edits.

Edits made in the app become a review or interview sheet and go through the same
`apply_review_sheet` / `apply_interview_sheet` as the command line, so both check
input the same way.
"""

from __future__ import annotations

import math
from pathlib import PurePosixPath
from typing import Any

import yaml

from unapply.dates import format_partial_date
from unapply.interview.questions import Question, Reason
from unapply.interview.sheet import export_interview_sheet
from unapply.schemas import Experience, Job, Profile, SourceKind

LEVEL_NAMES = {1: "aware", 2: "basic", 3: "working", 4: "advanced", 5: "expert"}
# How levels are shown and chosen in the app, such as "4 · advanced".
LEVEL_LABELS = [f"{n} · {name}" for n, name in LEVEL_NAMES.items()]
# The choice for no level, so tables never show an empty cell as "None".
NO_LEVEL = "—"


def level_label(level: int | None) -> str | None:
    """Write a level as shown in the app, such as "4 · advanced".

    Parameters
    ----------
    level : int or None
        A level from 1 to 5.

    Returns
    -------
    str or None
        The label, or None for no level.
    """
    return LEVEL_LABELS[int(level) - 1] if level else None


def candidate_view(profile: Profile) -> Profile:
    """Return the profile without the assessment, as the candidate sees it.

    Estimates and claim support are not shown to candidates. They remain part of
    the candidate's data and are provided on a data access request.

    Parameters
    ----------
    profile : Profile
        The full profile.

    Returns
    -------
    Profile
        A copy without estimates or claim support.
    """
    return profile.model_copy(
        update={
            "skills": [s.model_copy(update={"estimate": None}) for s in profile.skills],
            "claim_support": None,
        }
    )


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


def evidence_details(profile: Profile, ids: list) -> list[dict[str, str]]:
    """Describe evidence in full, for a detail view the review table can't fit.

    Parameters
    ----------
    profile : Profile
        The profile the evidence belongs to.
    ids : list of UUID
        Evidence ids.

    Returns
    -------
    list of dict
        One per piece of evidence, in order: "source", such as "cv · cv.md · page
        2" or "your statement", and "quote", the quote exactly as written, line
        breaks included.
    """
    sources = {s.id: s for s in profile.sources}
    evidence = {e.id: e for e in profile.evidence}
    details = []
    for i in ids:
        e = evidence[i]
        source = sources[e.source_id]
        if source.kind == SourceKind.INTERVIEW:
            parts = ["your statement"]
        else:
            parts = [source.kind.value]
            if source.uri:
                parts.append(PurePosixPath(source.uri.rstrip("/")).name)
        if e.locator:
            parts.append(e.locator)
        details.append({"source": " · ".join(parts), "quote": e.quote.strip()})
    return details


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
            "level": level_label(s.self_level) or NO_LEVEL,
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
            "start": format_partial_date(x.start, x.start_precision),
            "end": format_partial_date(x.end, x.end_precision),
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


def period(experience: Experience) -> str:
    """Describe when something happened, such as "2019-08 to now"; empty if unknown.

    Each date is written as precisely as it is known: "2019" or "2019-08".

    Parameters
    ----------
    experience : Experience
        The entry; its `end` None means now (when there is a start).

    Returns
    -------
    str
        The period, or "" when neither date is known.
    """
    x = experience
    if x.start is None and x.end is None:
        return ""
    start = format_partial_date(x.start, x.start_precision) or "?"
    end = format_partial_date(x.end, x.end_precision) or "now"
    return f"{start} to {end}"


def _missing(value: Any) -> bool:  # noqa: ANN401
    return value is None or (isinstance(value, float) and math.isnan(value))


def _text(value: Any) -> str:  # noqa: ANN401
    return "" if _missing(value) else str(value).strip()


def _blank(value: Any) -> str | None:  # noqa: ANN401
    text = _text(value)
    return text or None


def _level(value: Any) -> int | None:  # noqa: ANN401
    """Read a level from a number or a label such as "4 · advanced"."""
    if _missing(value) or str(value).strip() in ("", NO_LEVEL):
        return None
    if isinstance(value, str):
        return int(value.strip().split()[0])
    return int(value)


# How criterion kinds are shown and chosen in the app.
KIND_LABELS = {"must_have": "Must have", "nice_to_have": "Nice to have"}


def criterion_rows(job: Job) -> list[dict[str, Any]]:
    """Rows for the rubric editor's table of criteria.

    Parameters
    ----------
    job : Job
        The job whose rubric is edited.

    Returns
    -------
    list of dict
        One row per criterion: id, kind, description, skill, level, weight, quote.
    """
    return [
        {
            "id": str(c.id),
            "kind": KIND_LABELS[c.kind.value],
            "description": c.description,
            "skill": c.skill or "",
            "level": level_label(c.min_level) or NO_LEVEL,
            "weight": int(round(c.weight)),
            "quote": c.source_quote or "",
        }
        for c in job.rubric.criteria
    ]


def rubric_sheet(
    job: Job,
    *,
    company: str,
    title: str,
    filters: dict[str, Any],
    rows: list[dict[str, Any]],
    approve: bool,
) -> str:
    """Build a rubric sheet from the app's edited rubric.

    Rows deleted in the table are removed from the rubric; rows added have no id
    and become new criteria. Rows with no description are ignored.

    Parameters
    ----------
    job : Job
        The job being edited.
    company : str
        Company name.
    title : str
        Job title.
    filters : dict
        Hard filters, with the keys of `HardFilters`.
    rows : list of dict
        Rows from `criterion_rows`, as edited.
    approve : bool
        Whether the recruiter approves the rubric.

    Returns
    -------
    str
        A sheet for `apply_rubric_sheet`.
    """
    kinds = {label: value for value, label in KIND_LABELS.items()}
    criteria = []
    for r in rows:
        description = _text(r.get("description"))
        if not description:
            continue
        row = {
            "kind": kinds.get(_text(r.get("kind")), "must_have"),
            "description": description,
            "skill": _blank(r.get("skill")),
            "min_level": _level(r.get("level")),
            "weight": 3 if _missing(r.get("weight")) else int(r["weight"]),
        }
        if _blank(r.get("id")):
            row = {"id": _text(r["id"]), **row}
        criteria.append(row)
    sheet = {
        "job": str(job.id),
        "approve": approve,
        "company": company,
        "title": title,
        "hard_filters": filters,
        "criteria": criteria,
    }
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False)
