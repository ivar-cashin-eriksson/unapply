"""SQLAlchemy tables: candidates, profiles, jobs, rubrics, matches, audit and more.

The others are intents (employers' reveals and application requests) and consents
(which jobs a candidate opted in to).

The tables mirror the Pydantic schemas in `unapply.schemas`; `unapply.db.repository`
converts between the two, so nothing else needs to know about the tables.

Choices that keep the same tables working on SQLite and Postgres:

- Only portable types: `Uuid` (native on Postgres, 32 characters on SQLite), `JSON`,
  strings for enum values and integers for skill levels. No database enums, so a new
  enum value needs no migration.
- Datetimes are naive local time, like the schemas.
- Lists of ids and names that are only read together with their row (such as a
  skill's `evidence_ids`) are JSON lists, in order. Lists of things with their own
  fields are tables with a `position` column, so loading keeps the order.
- Rows that belong to a profile are keyed by the candidate and their schema id, so
  two candidates can hold copies of the same evidence without clashing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

# Stable constraint names, so migrations can refer to them on every database.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

CASCADE = "CASCADE"


class Base(DeclarativeBase):
    """Base class of every table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}


class CandidateRow(Base):
    """A candidate and their current profile (`Profile`).

    A candidate exists before their first profile, so the profile columns are empty
    until then (`profile_id` is None). A new extraction replaces the profile, with a
    new `profile_id`; earlier versions are kept in `candidate_history`.
    """

    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    profile_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    headline: Mapped[str] = mapped_column(Text, default="")
    approved_by_candidate_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Preferences, as columns so hard filters can query them.
    locations: Mapped[list[str]] = mapped_column(default=list)
    work_modes: Mapped[list[str]] = mapped_column(default=list)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    work_permits: Mapped[list[str]] = mapped_column(default=list)
    dealbreakers: Mapped[list[str]] = mapped_column(default=list)


class SourceRow(Base):
    """A piece of material in a candidate's profile (`Source`)."""

    __tablename__ = "sources"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    uri: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)


class EvidenceRow(Base):
    """A snippet from a source (`Evidence`)."""

    __tablename__ = "evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["candidate_id", "source_id"],
            ["sources.candidate_id", "sources.id"],
            name="fk_evidence_source",
            ondelete=CASCADE,
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    quote: Mapped[str] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(Text)


class ExperienceRow(Base):
    """A job, project or education entry (`Experience`)."""

    __tablename__ = "experiences"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    organisation: Mapped[str] = mapped_column(Text)
    start: Mapped[date | None] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)
    # "year" or "month" (`DatePrecision`): how much of `start` and `end` is known.
    start_precision: Mapped[str] = mapped_column(
        String(8), default="month", server_default="month"
    )
    end_precision: Mapped[str] = mapped_column(
        String(8), default="month", server_default="month"
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list[str]] = mapped_column(default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(default=list)


class CandidateSkillRow(Base):
    """A skill with the candidate's own level and the estimate (`Skill`).

    The `estimate_*` columns are all empty, or all set except `estimate_evidence_ids`
    which may be an empty list.
    """

    __tablename__ = "candidate_skills"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(32))
    self_level: Mapped[int | None] = mapped_column(Integer)
    evidence_ids: Mapped[list[str]] = mapped_column(default=list)
    estimate_level: Mapped[int | None] = mapped_column(Integer)
    estimate_confidence: Mapped[float | None] = mapped_column(Float)
    estimate_rationale: Mapped[str | None] = mapped_column(Text)
    estimate_evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    estimate_model: Mapped[str | None] = mapped_column(String(200))
    estimated_at: Mapped[datetime | None] = mapped_column(DateTime)


class ClaimSupportRow(Base):
    """How well a candidate's self-reports are supported (`ClaimSupport`)."""

    __tablename__ = "claim_support"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    rated: Mapped[int] = mapped_column(Integer, default=0)
    overclaims: Mapped[list[str]] = mapped_column(default=list)
    underclaims: Mapped[list[str]] = mapped_column(default=list)
    unverified: Mapped[list[str]] = mapped_column(default=list)
    unsupported_claims: Mapped[list[str]] = mapped_column(default=list)
    inconsistencies: Mapped[list[str]] = mapped_column(default=list)
    score: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime)


class InterviewQuestionRow(Base):
    """A follow-up question to a candidate, and their answer once given.

    Questions without an answer are the ones waiting. The answer itself becomes part
    of the profile as an interview source; it is kept here too, with its question.
    """

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    skill: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(DateTime)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)


class CandidateHistoryRow(Base):
    """The profile after one step, such as "extracted" or "reviewed"."""

    __tablename__ = "candidate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), index=True
    )
    step: Mapped[str] = mapped_column(String(64))
    profile: Mapped[dict[str, Any]] = mapped_column()
    saved_at: Mapped[datetime] = mapped_column(DateTime)


class JobRow(Base):
    """A job (`Job`). Its rubric is in `rubric_versions`.

    A job exists before its ad is extracted, so the job columns are empty until then
    (`job_id` is None). `id` is the row's own id; `job_id` is `Job.id`, which changes
    if the ad is extracted again.
    """

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    job_id: Mapped[UUID | None] = mapped_column(Uuid, unique=True)
    company: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    ad_text: Mapped[str | None] = mapped_column(Text)
    reveal_quota: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    # The `Rubric.version` the job uses now. None before the job is first saved.
    rubric_version: Mapped[int | None] = mapped_column(Integer)


class RubricVersionRow(Base):
    """One version of a job's rubric (`Rubric`, without its criteria).

    A version that a match refers to can't change any more.
    """

    __tablename__ = "rubric_versions"
    __table_args__ = (UniqueConstraint("job_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete=CASCADE))
    version: Mapped[int] = mapped_column(Integer)
    hard_filters: Mapped[dict[str, Any]] = mapped_column()
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)


class CriterionRow(Base):
    """One criterion in one rubric version (`Criterion`).

    A criterion keeps its id when the recruiter edits the rubric, so the same
    `criterion_id` appears in several versions.
    """

    __tablename__ = "criteria"
    __table_args__ = (UniqueConstraint("rubric_version_id", "criterion_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rubric_version_id: Mapped[int] = mapped_column(
        ForeignKey("rubric_versions.id", ondelete=CASCADE)
    )
    criterion_id: Mapped[UUID] = mapped_column(Uuid)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    skill: Mapped[str | None] = mapped_column(String(200))
    min_level: Mapped[int | None] = mapped_column(Integer)
    weight: Mapped[float] = mapped_column(Float)
    source_quote: Mapped[str | None] = mapped_column(Text)


class JobHistoryRow(Base):
    """The job after one step, such as "ad" or "rubric"."""

    __tablename__ = "job_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete=CASCADE), index=True
    )
    step: Mapped[str] = mapped_column(String(64))
    job: Mapped[dict[str, Any]] = mapped_column()
    saved_at: Mapped[datetime] = mapped_column(DateTime)


class MatchRow(Base):
    """One candidate scored against one rubric version (`Match`).

    `job_id` and `profile_id` are the `Job.id` and `Profile.id` scored. They are not
    foreign keys: the candidate's profile may have been replaced since, and the match
    must stay. The rubric version links the match to its job, and can't be deleted
    while a match refers to it.
    """

    __tablename__ = "matches"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    rubric_version_id: Mapped[int] = mapped_column(
        ForeignKey("rubric_versions.id"), index=True
    )
    profile_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    passed_hard_filters: Mapped[bool] = mapped_column()
    model: Mapped[str] = mapped_column(String(200))
    scored_at: Mapped[datetime] = mapped_column(DateTime)


class CriterionScoreRow(Base):
    """How well a match meets one criterion (`CriterionScore`)."""

    __tablename__ = "criterion_scores"

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete=CASCADE), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    criterion_id: Mapped[UUID] = mapped_column(Uuid)
    score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(default=list)


class TaxonomySkillRow(Base):
    """One canonical skill in the skill taxonomy (`unapply.taxonomy.TaxonomySkill`).

    The taxonomy is configuration (`config/skills.yaml`); `unapply db init` copies it
    here, replacing what was there, so queries can join on it.
    """

    __tablename__ = "taxonomy_skills"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    category: Mapped[str | None] = mapped_column(String(32))


class SkillSynonymRow(Base):
    """Another name for a canonical skill, such as "sklearn" for "scikit-learn"."""

    __tablename__ = "skill_synonyms"

    synonym: Mapped[str] = mapped_column(String(200), primary_key=True)
    skill: Mapped[str] = mapped_column(
        ForeignKey("taxonomy_skills.name", ondelete=CASCADE), index=True
    )


class SkillRelationRow(Base):
    """One skill implying, or being a kind of, another.

    `kind` is "implies" ("dbt" implies "sql") or "broader" ("lightgbm" is a kind of
    "gradient boosting"); both point from the specific skill to the general one.
    """

    __tablename__ = "skill_relations"

    skill: Mapped[str] = mapped_column(
        ForeignKey("taxonomy_skills.name", ondelete=CASCADE), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    related: Mapped[str] = mapped_column(
        ForeignKey("taxonomy_skills.name", ondelete=CASCADE),
        primary_key=True,
        index=True,
    )


class AuditEntryRow(Base):
    """One entry in the append-only audit log (`unapply.matching.audit.AuditEntry`).

    An entry records a match (one candidate scored) or a ranking (a job's matches
    put in order), with what is needed to check and reproduce it later. Like
    matches, `job_id`, `match_id` and `profile_id` are plain ids rather than foreign
    keys, so the log outlives profiles and jobs that are replaced. Entries are never
    changed or deleted: the ORM refuses to (see `_refuse_changes`), and the
    repository has no method that would.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))
    job_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    rubric_version: Mapped[int] = mapped_column(Integer)
    rubric_hash: Mapped[str] = mapped_column(String(80))
    scorer: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    match_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    profile_id: Mapped[UUID | None] = mapped_column(Uuid)
    profile_hash: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(DateTime)


@event.listens_for(AuditEntryRow, "before_update")
@event.listens_for(AuditEntryRow, "before_delete")
def _refuse_changes(
    mapper: Mapper[AuditEntryRow],
    connection: object,
    target: AuditEntryRow,
) -> None:
    """Refuse to change or delete an audit entry through the ORM.

    Raises
    ------
    ValueError
        Always: the audit log is append-only.
    """
    raise ValueError(f"audit log entry {target.id} can't be changed or deleted")


class IntentRow(Base):
    """An employer's request about a shortlisted candidate (`Intent`).

    "reveal" or "request_application", recorded once per job and candidate: asking
    again changes nothing. Like matches, `job_id` and `profile_id` are plain ids
    rather than foreign keys, so the record outlives a profile that is replaced.
    """

    __tablename__ = "intents"
    __table_args__ = (UniqueConstraint("job_id", "profile_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    profile_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime)


class ConsentRow(Base):
    """A candidate's opt-in to one job (`unapply.consent.Consent`).

    Keyed by the candidate's and the job's own row ids, which don't change when a
    profile or an ad is extracted again, so consent outlives both; it goes with
    the candidate or the job. Withdrawing consent deletes the row.
    """

    __tablename__ = "consents"

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete=CASCADE), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete=CASCADE), primary_key=True, index=True
    )
    # `ConsentSection` values, in that order.
    sections: Mapped[list[str]] = mapped_column(default=list)
    granted_at: Mapped[datetime] = mapped_column(DateTime)
