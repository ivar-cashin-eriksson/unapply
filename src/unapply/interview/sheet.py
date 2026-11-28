"""The interview sheet: questions the candidate answers in any editor.

`export_interview_sheet` writes the questions; `apply_interview_sheet` adds the answers
to the profile as the candidate's own statements, each keeping its question, and
clears the estimates they make outdated.
"""

from __future__ import annotations

import json
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from unapply.interview.questions import INTERVIEW_URI, WHY, Question
from unapply.schemas import Evidence, Profile, Source, SourceKind


class InterviewError(ValueError):
    """The interview sheet can't be applied. The message says what to fix."""


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    why: str = ""
    question: str
    answer: str | None = None


class _Sheet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    questions: list[_Row]


def export_interview_sheet(profile: Profile, questions: list[Question]) -> str:
    """Write questions as a YAML sheet for the candidate to answer.

    Parameters
    ----------
    profile : Profile
        The profile the questions are about.
    questions : list of Question
        The questions, from `write_questions`.

    Returns
    -------
    str
        The sheet, with instructions as YAML comments.
    """
    out = [
        "# Answer the questions you can; leave an answer empty to skip it.",
        "# Specific answers help most: what you did, at roughly what scale, in which",
        "# role and when. Answers are kept as your own statements, next to the",
        "# question, and used to re-estimate your levels (run `unapply estimate`).",
        "# For an answer over several lines, write `answer: |` and indent the lines",
        "# below it.",
        "",
        f"profile: {profile.id}",
        "questions:",
    ]
    for q in questions:
        out += [
            f"  - skill: {json.dumps(q.skill, ensure_ascii=False)}",
            f"    why: {json.dumps(WHY[q.reason], ensure_ascii=False)}",
            f"    question: {json.dumps(q.text, ensure_ascii=False)}",
            '    answer: ""',
        ]
    return "\n".join(out) + "\n"


def apply_interview_sheet(profile: Profile, sheet_text: str) -> tuple[Profile, int]:
    """Add the candidate's answers to the profile.

    Parameters
    ----------
    profile : Profile
        The profile the sheet was exported from.
    sheet_text : str
        The answered sheet.

    Returns
    -------
    Profile
        The profile with each answer as evidence from an interview source, its
        question as the evidence's locator. Answered skills lose their estimate and
        the profile its claim support, until estimated again.
    int
        How many questions were answered.

    Raises
    ------
    InterviewError
        If the sheet isn't valid YAML, is for another profile, or names a skill
        that isn't in the profile, or the same skill twice.
    """
    sheet = _parse(sheet_text)
    if sheet.profile != str(profile.id):
        raise InterviewError(
            f"this sheet is for profile {sheet.profile}, not {profile.id}"
        )
    names = [row.skill for row in sheet.questions]
    unknown = [n for n in names if profile.skill(n) is None]
    if unknown:
        raise InterviewError(f"skills not in the profile: {unknown}")
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise InterviewError(f"skills asked about more than once: {duplicates}")

    answered = [r for r in sheet.questions if r.answer and r.answer.strip()]
    if not answered:
        return profile, 0
    interview = Source(kind=SourceKind.INTERVIEW, uri=INTERVIEW_URI)
    evidence = list(profile.evidence)
    new_ids: dict[str, list] = {}
    for row in answered:
        e = Evidence(
            source_id=interview.id,
            quote=row.answer.strip(),
            locator=" ".join(row.question.split()),
        )
        evidence.append(e)
        new_ids[row.skill] = [e.id]
    skills = [
        s.model_copy(
            update={"evidence_ids": s.evidence_ids + new_ids[s.name], "estimate": None}
        )
        if s.name in new_ids
        else s
        for s in profile.skills
    ]
    updated = profile.model_copy(
        update={
            "sources": [*profile.sources, interview],
            "evidence": evidence,
            "skills": skills,
            "claim_support": None,
        }
    )
    return Profile.model_validate(updated.model_dump()), len(answered)


def _parse(sheet_text: str) -> _Sheet:
    # Every value in the sheet is text, so it's read as written: an answer of `Yes`,
    # `No` or `2019` stays that text instead of becoming a boolean or a number.
    try:
        data: Any = yaml.load(sheet_text, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise InterviewError(f"the sheet isn't valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise InterviewError("the sheet is empty or not a mapping")
    try:
        return _Sheet.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{' '.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in e.errors()
        )
        raise InterviewError(f"invalid values: {problems}") from e
