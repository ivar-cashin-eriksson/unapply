"""The rubric sheet: the recruiter's review of a draft rubric, in any editor.

`export_rubric_sheet` writes the job's hard filters and criteria as YAML, with each
criterion's quote from the ad as a comment. The recruiter corrects, removes, adds and
reweights criteria and approves; `apply_rubric_sheet` checks the sheet and returns the
updated job. Any change to the rubric raises its version, so matches can say which
version they used.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from unapply.jobs.extract import MAX_WEIGHT, MIN_WEIGHT
from unapply.schemas import (
    Criterion,
    CriterionKind,
    HardFilters,
    Job,
    SkillLevel,
    WorkMode,
)
from unapply.taxonomy import canonical_skill


class RubricError(ValueError):
    """The rubric sheet can't be applied. The message says what to fix."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _CriterionRow(_Strict):
    id: str | None = None
    keep: bool = True
    kind: CriterionKind
    description: str
    skill: str | None = None
    min_level: int | None = Field(default=None, ge=1, le=5)
    weight: int = Field(default=3, ge=MIN_WEIGHT, le=MAX_WEIGHT)

    @field_validator("description")
    @classmethod
    def _described(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("say what the criterion asks for")
        return v


class _Filters(_Strict):
    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    required_work_permits: list[str] = Field(default_factory=list)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)


class _Sheet(_Strict):
    job: str
    approve: bool = False
    company: str
    title: str
    hard_filters: _Filters
    criteria: list[_CriterionRow] = Field(default_factory=list)


def export_rubric_sheet(job: Job) -> str:
    """Write a job's rubric as a YAML sheet for the recruiter to edit.

    Parameters
    ----------
    job : Job
        The job to review.

    Returns
    -------
    str
        The sheet, with instructions and each criterion's quote as YAML comments.
    """
    f = job.rubric.hard_filters
    out = [
        "# Review the rubric candidates are scored against. Candidates never see it.",
        "#",
        "# hard_filters: pass/fail. A candidate who fails one is still scored, but",
        "#   ranks after everyone who passes. Leave a filter empty to not filter on it.",
        "# criteria: kind is must_have or nice_to_have; weight 1 (minor) to 5",
        "#   (essential); min_level 1 aware, 2 basic, 3 working, 4 advanced, 5 expert,",
        "#   or empty. Set `keep: false` to remove one. Add new criteria at the end,",
        "#   without an id. Lines starting with # are ignored.",
        "# approve: set to true when the rubric is right.",
        "",
        f"job: {job.id}",
        "approve: false",
        f"company: {_s(job.company)}",
        f"title: {_s(job.title)}",
        "",
        "hard_filters:",
        f"  locations: {_s(f.locations)}",
        f"  work_modes: {_s([m.value for m in f.work_modes])}",
        f"  required_work_permits: {_s(f.required_work_permits)}",
        f"  min_years_experience: {'' if f.min_years_experience is None else f.min_years_experience}",
        "",
        "criteria:",
    ]
    for c in job.rubric.criteria:
        out += [
            f"  - id: {c.id}",
            "    keep: true",
            f"    kind: {c.kind.value}",
            f"    description: {_s(c.description)}",
            f"    skill: {_s(c.skill) if c.skill else ''}",
            f"    min_level: {int(c.min_level) if c.min_level else ''}",
            f"    weight: {int(round(c.weight))}",
        ]
        if c.source_quote:
            out.append(f"    # from the ad: {' '.join(c.source_quote.split())}")
    out += [
        "  # - kind: nice_to_have",
        '  #   description: "Experience with Kubernetes"',
        "  #   skill: kubernetes",
        "  #   min_level:",
        "  #   weight: 1",
        "",
    ]
    return "\n".join(out)


def apply_rubric_sheet(job: Job, sheet_text: str) -> Job:
    """Apply an edited rubric sheet to the job it was exported from.

    Parameters
    ----------
    job : Job
        The job the sheet was exported from.
    sheet_text : str
        The edited sheet.

    Returns
    -------
    Job
        The updated job. If the rubric changed, its version is one higher and any
        earlier approval is cleared; it is approved, with the current time, if the
        sheet says `approve: true`.

    Raises
    ------
    RubricError
        If the sheet isn't valid YAML, is for another job, has invalid values,
        unknown criterion ids, or no criteria left.
    """
    sheet = _parse(sheet_text)
    if sheet.job != str(job.id):
        raise RubricError(f"this sheet is for job {sheet.job}, not {job.id}")
    existing = {str(c.id): c for c in job.rubric.criteria}
    unknown = [r.id for r in sheet.criteria if r.id and r.id not in existing]
    if unknown:
        raise RubricError(f"unknown criterion ids: {unknown}")

    criteria = []
    for row in sheet.criteria:
        if not row.keep:
            continue
        values = {
            "kind": row.kind,
            "description": " ".join(row.description.split()),
            "skill": canonical_skill(row.skill)
            if row.skill and row.skill.strip()
            else None,
            "min_level": SkillLevel(row.min_level) if row.min_level else None,
            "weight": float(row.weight),
        }
        if row.id:
            criteria.append(existing[row.id].model_copy(update=values))
        else:
            criteria.append(Criterion(**values))
    if not criteria:
        raise RubricError("keep or add at least one criterion")

    f = sheet.hard_filters
    filters = HardFilters(
        locations=[x.strip() for x in f.locations if x.strip()],
        work_modes=list(dict.fromkeys(f.work_modes)),
        required_work_permits=[x.strip() for x in f.required_work_permits if x.strip()],
        min_years_experience=f.min_years_experience,
    )
    old = job.rubric
    changed = filters != old.hard_filters or _content(criteria) != _content(
        old.criteria
    )
    rubric = old.model_copy(
        update={
            "hard_filters": filters,
            "criteria": criteria,
            "version": old.version + 1 if changed else old.version,
            "approved_at": datetime.now() if sheet.approve else None,
        }
    )
    return job.model_copy(
        update={
            "company": sheet.company.strip(),
            "title": sheet.title.strip(),
            "rubric": rubric,
        }
    )


def _content(criteria: list[Criterion]) -> list[tuple]:
    """List what a match depends on, to tell whether the rubric changed."""
    return [
        (c.id, c.kind, c.description, c.skill, c.min_level, c.weight) for c in criteria
    ]


def _parse(sheet_text: str) -> _Sheet:
    try:
        data: Any = yaml.safe_load(sheet_text)
    except yaml.YAMLError as e:
        raise RubricError(f"the sheet isn't valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise RubricError("the sheet is empty or not a mapping")
    try:
        return _Sheet.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(_describe(data, err) for err in e.errors())
        raise RubricError(f"invalid values: {problems}") from e


def _describe(data: dict, err: dict) -> str:
    """Name the criterion an error is in, e.g. 'criteria "Strong Python" weight'."""
    loc = [str(p) for p in err["loc"]]
    if len(err["loc"]) >= 2 and err["loc"][0] == "criteria":
        rows = data.get("criteria") or []
        i = err["loc"][1]
        if isinstance(i, int) and i < len(rows) and isinstance(rows[i], dict):
            loc[1] = json.dumps(str(rows[i].get("description") or f"#{i + 1}"))
    return f"{' '.join(loc)}: {err['msg']}"


def _s(value: Any) -> str:  # noqa: ANN401
    """Write a value as YAML on one line."""
    return json.dumps(value, ensure_ascii=False)
