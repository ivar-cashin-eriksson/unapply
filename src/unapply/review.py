"""The candidate's review of their draft profile.

`export_review_sheet` writes a YAML sheet the candidate edits in any editor: their
own level per skill, what to remove, corrections to experiences, skills to add and
whether they approve. `apply_review_sheet` checks the sheet and returns the reviewed
profile. Skills the candidate adds are recorded as their own statements, in a source
of kind `interview`, so they stay distinguishable from evidence found in documents.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from unapply.dates import format_partial_date, parse_partial_date
from unapply.schemas import (
    DatePrecision,
    Evidence,
    Preferences,
    Profile,
    Skill,
    SkillCategory,
    SkillLevel,
    Source,
    SourceKind,
)
from unapply.taxonomy import canonical_skill, normalise_skill_name

LEVELS = "1 aware, 2 basic, 3 working, 4 advanced, 5 expert"
CATEGORIES = ", ".join(c.value for c in SkillCategory)


class ReviewError(ValueError):
    """The review sheet can't be applied. The message says what to fix."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ExperienceRow(_Strict):
    id: str
    keep: bool = True
    title: str
    organisation: str
    # YAML reads a bare year such as 2019 as a number.
    start: int | str | None = None
    end: int | str | None = None
    summary: str = ""


class _SkillRow(_Strict):
    name: str
    category: SkillCategory | None = None
    level: int | None = Field(default=None, ge=1, le=5)
    keep: bool = True


class _NewSkill(_Strict):
    name: str
    category: SkillCategory
    level: int | None = Field(default=None, ge=1, le=5)
    note: str

    @field_validator("note")
    @classmethod
    def _note_given(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("say where you used the skill")
        return v


class _Sheet(_Strict):
    profile: str
    approve: bool = False
    headline: str
    preferences: Preferences
    experiences: list[_ExperienceRow] = Field(default_factory=list)
    skills: list[_SkillRow] = Field(default_factory=list)
    add_skills: list[_NewSkill] | None = None


def export_review_sheet(profile: Profile) -> str:
    """Write a profile as a YAML review sheet for the candidate to edit.

    Parameters
    ----------
    profile : Profile
        The profile to review, usually a fresh draft.

    Returns
    -------
    str
        The sheet, with instructions and each item's evidence as YAML comments.
    """
    quotes = _quotes_by_id(profile)
    out = [
        "# Review your profile.",
        "#",
        f"# skills: set `level` to your own level ({LEVELS}), or leave it empty.",
        "#   Set `keep: false` on anything that is wrong. Evidence is shown for",
        "#   reference: lines starting with # are ignored.",
        "# experiences: correct anything, dates as YYYY or YYYY-MM.",
        "# add_skills: skills that are missing. Give each a `note` saying where you",
        "#   used it; notes are kept as your own statements.",
        "# approve: set to true when the profile is right. Employers only see",
        "#   approved profiles.",
        "",
        f"profile: {profile.id}",
        "approve: false",
        f"headline: {_s(profile.headline)}",
        "",
        "preferences:",
    ]
    for key, value in profile.preferences.model_dump(mode="json").items():
        out.append(f"  {key}: {json.dumps(value, ensure_ascii=False)}")

    out += ["", "experiences:"]
    for x in profile.experiences:
        out += [
            f"  - id: {x.id}",
            "    keep: true",
            f"    title: {_s(x.title)}",
            f"    organisation: {_s(x.organisation)}",
            f"    start: {_d(x.start, x.start_precision)}",
            f"    end: {_d(x.end, x.end_precision)}",
            f"    summary: {_s(x.summary)}",
        ]
        out += [f"    # {q}" for q in _evidence_lines(x.evidence_ids, quotes)]

    out += ["", f"# Categories: {CATEGORIES}.", "skills:"]
    for s in profile.skills:
        out += [
            f"  - name: {_s(s.name)}",
            f"    category: {s.category.value if s.category else ''}",
            f"    level: {int(s.self_level) if s.self_level else ''}",
            "    keep: true",
        ]
        out += [f"    # {q}" for q in _evidence_lines(s.evidence_ids, quotes)]

    out += [
        "",
        "add_skills:",
        "  # - name: matlab",
        "  #   category: technology",
        "  #   level: 3",
        "  #   note: Used for signal processing coursework at KTH, 2016-2018.",
        "",
    ]
    return "\n".join(out)


def apply_review_sheet(profile: Profile, sheet_text: str) -> Profile:
    """Apply an edited review sheet to the profile it was exported from.

    Parameters
    ----------
    profile : Profile
        The profile the sheet was exported from.
    sheet_text : str
        The edited sheet.

    Returns
    -------
    Profile
        A new profile with the candidate's levels, removals, corrections and added
        skills. It is approved, with the current time, if the sheet says
        `approve: true`; otherwise any earlier approval is cleared. Evidence no
        longer referenced is dropped; every source is kept. Skill names are
        canonical (see `unapply.taxonomy`): skills that turn out to be synonyms are
        merged, and an added skill that is a synonym of a kept one is refused.

    Raises
    ------
    ReviewError
        If the sheet isn't valid YAML, is for another profile, or has invalid
        values, unknown items or duplicate skills.
    """
    sheet = _parse(sheet_text)
    if sheet.profile != str(profile.id):
        raise ReviewError(
            f"this sheet is for profile {sheet.profile}, not {profile.id}"
        )

    experiences = {str(x.id): x for x in profile.experiences}
    unknown = [row.id for row in sheet.experiences if row.id not in experiences]
    if unknown:
        raise ReviewError(f"unknown experience ids: {unknown}")
    new_experiences = []
    for row in sheet.experiences:
        if not row.keep:
            continue
        x = experiences[row.id]
        start, start_precision = _parse_date(row.start, f"start of {row.title}")
        end, end_precision = _parse_date(row.end, f"end of {row.title}")
        new_experiences.append(
            x.model_copy(
                update={
                    "title": row.title,
                    "organisation": row.organisation,
                    "start": start,
                    "end": end,
                    "start_precision": start_precision,
                    "end_precision": end_precision,
                    "summary": row.summary,
                    "skills": sorted({canonical_skill(s) for s in x.skills}),
                }
            )
        )

    # Rows are matched to the profile's skills by the names the sheet was written
    # with; the taxonomy's canonical names are applied after that, below.
    skills = {normalise_skill_name(s.name): s for s in profile.skills}
    names = [normalise_skill_name(r.name) for r in sheet.skills]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ReviewError(f"skills listed more than once: {duplicates}")
    # Rows deleted from the sheet count as removed, like keep: false.
    rows = dict(zip(names, sheet.skills, strict=True))
    unknown = [name for name in rows if name not in skills]
    if unknown:
        raise ReviewError(
            f"unknown skills: {unknown}. Skill names can't be changed; "
            "remove the skill and add it under add_skills instead."
        )
    new_skills = _merged(
        [
            skills[name].model_copy(
                update={
                    "category": row.category,
                    "self_level": SkillLevel(row.level) if row.level else None,
                }
            )
            for name, row in rows.items()
            if row.keep
        ]
    )

    sources = list(profile.sources)
    evidence = list(profile.evidence)
    if sheet.add_skills:
        statement = Source(kind=SourceKind.INTERVIEW, uri="review sheet")
        sources.append(statement)
        kept = {s.name for s in new_skills}
        for new in sheet.add_skills:
            name = canonical_skill(new.name)
            if name in kept:
                raise ReviewError(f"{name!r} is already in skills; set its level there")
            kept.add(name)
            note = Evidence(source_id=statement.id, quote=new.note.strip())
            evidence.append(note)
            new_skills.append(
                Skill(
                    name=name,
                    category=new.category,
                    self_level=SkillLevel(new.level) if new.level else None,
                    evidence_ids=[note.id],
                )
            )

    return _pruned(
        profile.model_copy(
            update={
                "headline": sheet.headline,
                "preferences": sheet.preferences,
                "experiences": new_experiences,
                "skills": sorted(new_skills, key=lambda s: s.name),
                "sources": sources,
                "evidence": evidence,
                "approved_by_candidate_at": datetime.now() if sheet.approve else None,
            }
        )
    )


def _merged(skills: list[Skill]) -> list[Skill]:
    """Rename skills to their canonical names, merging those that become one.

    Two skills merge only in a profile extracted before the taxonomy knew they are
    the same, such as "sklearn" and "scikit-learn". The merged skill keeps all their
    evidence and the higher of the candidate's levels, and loses its estimate, so the
    skill is estimated again from the combined evidence.
    """
    merged: dict[str, Skill] = {}
    for s in skills:
        name = canonical_skill(s.name)
        first = merged.get(name)
        if first is None:
            merged[name] = s.model_copy(update={"name": name})
            continue
        levels = [x for x in (first.self_level, s.self_level) if x is not None]
        merged[name] = first.model_copy(
            update={
                "category": first.category or s.category,
                "self_level": max(levels) if levels else None,
                "evidence_ids": first.evidence_ids
                + [i for i in s.evidence_ids if i not in first.evidence_ids],
                "estimate": None,
            }
        )
    return list(merged.values())


def _parse(sheet_text: str) -> _Sheet:
    try:
        data: Any = yaml.safe_load(sheet_text)
    except yaml.YAMLError as e:
        raise ReviewError(f"the sheet isn't valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ReviewError("the sheet is empty or not a mapping")
    try:
        return _Sheet.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{_where(data, err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise ReviewError(f"invalid values: {problems}") from e


def _where(data: dict, loc: tuple) -> str:
    """Name the item an error is in, e.g. 'skills "python" level', not 'skills.120'."""
    parts = [str(p) for p in loc]
    if len(loc) >= 2 and isinstance(loc[1], int):
        items = data.get(loc[0]) or []
        item = items[loc[1]] if loc[1] < len(items) else None
        label = (
            (item.get("name") or item.get("title")) if isinstance(item, dict) else None
        )
        if label:
            parts[1] = json.dumps(label, ensure_ascii=False)
    return " ".join(parts)


def _pruned(profile: Profile) -> Profile:
    """Drop evidence nothing refers to any more.

    Sources are kept even when unused: they record what the profile was built from.
    """
    used = {i for x in profile.experiences for i in x.evidence_ids}
    used |= {i for s in profile.skills for i in s.evidence_ids}
    used |= {i for s in profile.skills if s.estimate for i in s.estimate.evidence_ids}
    evidence = [e for e in profile.evidence if e.id in used]
    return Profile.model_validate(
        profile.model_copy(update={"evidence": evidence}).model_dump()
    )


def _quotes_by_id(profile: Profile) -> dict:
    kinds = {s.id: s.kind.value for s in profile.sources}
    return {e.id: f"{kinds[e.source_id]}: {e.quote}" for e in profile.evidence}


def _evidence_lines(ids: list, quotes: dict) -> list[str]:
    return [" ".join(quotes[i].split()) for i in ids if i in quotes]


def _s(value: str) -> str:
    """Quote a string as YAML, on one line."""
    return json.dumps(value, ensure_ascii=False)


def _d(value: date | None, precision: DatePrecision) -> str:
    """Write a date as 'YYYY' or as a quoted 'YYYY-MM', as precise as it is known."""
    text = format_partial_date(value, precision)
    return f'"{text}"' if "-" in text else text


def _parse_date(
    value: str | int | None, what: str
) -> tuple[date | None, DatePrecision]:
    """Read a sheet date and its precision; an empty date is unknown."""
    try:
        parsed = parse_partial_date(value)
    except ValueError:
        raise ReviewError(f"{what}: {value!r} isn't YYYY or YYYY-MM") from None
    return parsed or (None, DatePrecision.MONTH)
