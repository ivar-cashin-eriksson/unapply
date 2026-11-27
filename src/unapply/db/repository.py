"""Saving and loading the schemas in the database.

`Repository` stores what a `Workspace` folder stores, in the same terms: candidates
and jobs by name, their current `Profile` or `Job`, a history of every step, and
interview questions waiting for answers. It adds what folders can't do well: rubric
versions that can't change once a match uses them, matches, an append-only audit log
of matches and rankings, employers' intents (reveals and application requests),
candidates' consents to jobs, and a copy of the skill taxonomy.

Every method runs in its own transaction, so a failed call changes nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from unapply.consent import Consent, ConsentSection
from unapply.db.engine import make_engine
from unapply.db.models import (
    AuditEntryRow,
    CandidateHistoryRow,
    CandidateRow,
    CandidateSkillRow,
    ClaimSupportRow,
    ConsentRow,
    CriterionRow,
    CriterionScoreRow,
    EvidenceRow,
    ExperienceRow,
    IntentRow,
    InterviewQuestionRow,
    JobHistoryRow,
    JobRow,
    MatchRow,
    RubricVersionRow,
    SkillRelationRow,
    SkillSynonymRow,
    SourceRow,
    TaxonomySkillRow,
)
from unapply.matching.audit import AuditEntry, AuditKind
from unapply.matching.shortlist import Intent, IntentKind
from unapply.schemas import Job, Match, Profile, Rubric
from unapply.taxonomy import Taxonomy, TaxonomySkill
from unapply.workspace import NAME


class NotFound(LookupError):
    """No candidate, job or rubric version by that name or id."""


class RubricLocked(ValueError):
    """A rubric version that matches refer to can't be changed."""


class Repository:
    """Candidates, jobs and matches in a database.

    Parameters
    ----------
    engine : Engine
        The database, with its tables created (`unapply.db.engine.init_db`).
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_url(cls, url: str | None = None) -> Repository:
        """Open the database at a URL.

        Parameters
        ----------
        url : str or None, optional
            SQLAlchemy URL, by default `$UNAPPLY_DATABASE_URL` or SQLite in the data
            folder (see `unapply.db.engine.database_url`).

        Returns
        -------
        Repository
            The repository. The tables must exist already.
        """
        return cls(make_engine(url))

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Open a session in a transaction, committed on success.

        For code in `unapply.db` that works on the tables directly, such as the
        workspace import.

        Yields
        ------
        Session
            The session. The transaction is rolled back if the block raises.
        """
        with Session(self.engine) as session, session.begin():
            yield session

    # Candidates

    def create_candidate(self, name: str, **settings: Any) -> None:  # noqa: ANN401
        """Add a candidate without a profile.

        Parameters
        ----------
        name : str
            Lowercase letters, digits, "-" and "_", at most 64, as for workspaces.
        **settings
            Initial settings, such as `demo=True` or `github="johndoe"`.

        Raises
        ------
        ValueError
            If the name isn't valid or is taken.
        """
        _check_name(name)
        with self.transaction() as s:
            if _candidate(s, name, missing_ok=True) is not None:
                raise ValueError(f"a candidate called {name!r} already exists")
            s.add(
                CandidateRow(
                    id=uuid4(), name=name, settings=settings, created_at=datetime.now()
                )
            )

    def candidate_names(self) -> list[str]:
        """List the candidates.

        Returns
        -------
        list of str
            Names, sorted.
        """
        with self.transaction() as s:
            return list(
                s.scalars(select(CandidateRow.name).order_by(CandidateRow.name))
            )

    def settings(self, name: str) -> dict[str, Any]:
        """Read a candidate's settings.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        dict
            The settings.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            return dict(_candidate(s, name).settings)

    def save_settings(self, name: str, settings: dict[str, Any]) -> None:
        """Replace a candidate's settings.

        Parameters
        ----------
        name : str
            The candidate.
        settings : dict
            The new settings. Must be JSON-serialisable.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            _candidate(s, name).settings = dict(settings)

    def profile(self, name: str) -> Profile | None:
        """Read a candidate's current profile.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        Profile or None
            The profile, or None before the first one is saved.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            return _load_profile(s, _candidate(s, name))

    def profile_ids(self, name: str) -> list[UUID]:
        """List every `Profile.id` a candidate has had, oldest first.

        A new extraction gives the profile a new id, and matches and employers'
        intents keep the id they were made with, so this finds them all.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        list of UUID
            Each id once, the current profile's last. Empty before the first
            profile.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            row = _candidate(s, name)
            query = (
                select(CandidateHistoryRow.profile)
                .filter_by(candidate_id=row.id)
                .order_by(CandidateHistoryRow.id)
            )
            ids = [UUID(p["id"]) for p in s.scalars(query) if p.get("id")]
            if row.profile_id is not None:
                ids.append(row.profile_id)
            return list(dict.fromkeys(reversed(ids)))[::-1]

    def candidate_of(self, profile_id: UUID) -> str | None:
        """Find whose current profile has a given `Profile.id`.

        Parameters
        ----------
        profile_id : UUID
            The profile's id, such as `Match.profile_id`.

        Returns
        -------
        str or None
            The candidate's name, or None if no current profile has that id. Not
            for employers, who see candidates anonymised.
        """
        with self.transaction() as s:
            return s.scalar(select(CandidateRow.name).filter_by(profile_id=profile_id))

    def profile_by_id(self, profile_id: UUID) -> Profile | None:
        """Read the current profile with a given `Profile.id`.

        Parameters
        ----------
        profile_id : UUID
            The profile's id, such as `Match.profile_id`.

        Returns
        -------
        Profile or None
            The profile, or None if no candidate's current profile has that id.
        """
        with self.transaction() as s:
            row = s.scalar(select(CandidateRow).filter_by(profile_id=profile_id))
            return _load_profile(s, row) if row else None

    def save_profile(self, name: str, profile: Profile, step: str) -> None:
        """Make `profile` the candidate's current profile and keep it in the history.

        Parameters
        ----------
        name : str
            The candidate.
        profile : Profile
            The profile after `step`.
        step : str
            What produced it, such as "extracted" or "reviewed".

        Raises
        ------
        NotFound
            If there is no such candidate.
        ValueError
            If another candidate's profile has the same id.
        """
        with self.transaction() as s:
            row = _candidate(s, name)
            _store_profile(s, row, profile)
            s.add(
                CandidateHistoryRow(
                    candidate_id=row.id,
                    step=step,
                    profile=profile.model_dump(mode="json"),
                    saved_at=datetime.now(),
                )
            )

    def history(self, name: str) -> list[str]:
        """List the steps a candidate's profile went through, oldest first.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        list of str
            Step names, such as ["extracted", "reviewed", "estimated"].

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            row = _candidate(s, name)
            query = (
                select(CandidateHistoryRow.step)
                .filter_by(candidate_id=row.id)
                .order_by(CandidateHistoryRow.id)
            )
            return list(s.scalars(query))

    def pending_questions(self, name: str) -> list[dict[str, str]] | None:
        """Read the interview questions waiting for answers.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        list of dict or None
            Questions with `skill`, `reason` and `text`, or None if there are none.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            rows = _pending(s, _candidate(s, name))
            if not rows:
                return None
            return [
                {"skill": q.skill, "reason": q.reason, "text": q.text} for q in rows
            ]

    def save_pending_questions(
        self, name: str, questions: list[dict[str, str]] | None
    ) -> None:
        """Replace the questions waiting for answers, or clear them with None.

        Answered questions are kept.

        Parameters
        ----------
        name : str
            The candidate.
        questions : list of dict or None
            Questions with `skill`, `reason` and `text`.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            row = _candidate(s, name)
            for q in _pending(s, row):
                s.delete(q)
            asked = datetime.now()
            for i, q in enumerate(questions or []):
                s.add(
                    InterviewQuestionRow(
                        candidate_id=row.id,
                        position=i,
                        skill=q["skill"],
                        reason=q["reason"],
                        text=q["text"],
                        asked_at=asked,
                    )
                )

    def record_answers(self, name: str, answers: dict[str, str]) -> int:
        """Store the candidate's answers to waiting questions.

        The answers become part of the profile through the interview sheet
        (`unapply.interview.sheet`); this keeps each with its question. Questions
        without an answer stay waiting.

        Parameters
        ----------
        name : str
            The candidate.
        answers : dict of str to str
            Skill name to answer. Empty answers are skipped.

        Returns
        -------
        int
            How many questions were answered.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            n = 0
            answered = datetime.now()
            for q in _pending(s, _candidate(s, name)):
                answer = answers.get(q.skill, "").strip()
                if answer:
                    q.answer, q.answered_at = answer, answered
                    n += 1
            return n

    def answered_questions(self, name: str) -> list[dict[str, str]]:
        """Read the questions the candidate answered, oldest first.

        Parameters
        ----------
        name : str
            The candidate.

        Returns
        -------
        list of dict
            Questions with `skill`, `reason`, `text` and `answer`.

        Raises
        ------
        NotFound
            If there is no such candidate.
        """
        with self.transaction() as s:
            row = _candidate(s, name)
            query = (
                select(InterviewQuestionRow)
                .filter_by(candidate_id=row.id)
                .where(InterviewQuestionRow.answer.is_not(None))
                .order_by(InterviewQuestionRow.answered_at, InterviewQuestionRow.id)
            )
            return [
                {
                    "skill": q.skill,
                    "reason": q.reason,
                    "text": q.text,
                    "answer": q.answer,
                }
                for q in s.scalars(query)
            ]

    # Jobs

    def create_job(self, name: str, **settings: Any) -> None:  # noqa: ANN401
        """Add a job before its ad is extracted.

        Parameters
        ----------
        name : str
            Lowercase letters, digits, "-" and "_", at most 64, as for workspaces.
        **settings
            Initial settings, such as `demo=True`.

        Raises
        ------
        ValueError
            If the name isn't valid or is taken.
        """
        _check_name(name)
        with self.transaction() as s:
            if _job(s, name, missing_ok=True) is not None:
                raise ValueError(f"a job called {name!r} already exists")
            s.add(JobRow(id=uuid4(), name=name, settings=settings))

    def job_names(self) -> list[str]:
        """List the jobs.

        Returns
        -------
        list of str
            Names, sorted.
        """
        with self.transaction() as s:
            return list(s.scalars(select(JobRow.name).order_by(JobRow.name)))

    def job_settings(self, name: str) -> dict[str, Any]:
        """Read a job's settings.

        Parameters
        ----------
        name : str
            The job.

        Returns
        -------
        dict
            The settings.

        Raises
        ------
        NotFound
            If there is no such job.
        """
        with self.transaction() as s:
            return dict(_job(s, name).settings)

    def save_job_settings(self, name: str, settings: dict[str, Any]) -> None:
        """Replace a job's settings.

        Parameters
        ----------
        name : str
            The job.
        settings : dict
            The new settings. Must be JSON-serialisable.

        Raises
        ------
        NotFound
            If there is no such job.
        """
        with self.transaction() as s:
            _job(s, name).settings = dict(settings)

    def job(self, name: str) -> Job | None:
        """Read a job with its current rubric.

        Parameters
        ----------
        name : str
            The job.

        Returns
        -------
        Job or None
            The job, or None before it is saved the first time.

        Raises
        ------
        NotFound
            If there is no such job.
        """
        with self.transaction() as s:
            return _load_job(s, _job(s, name))

    def job_by_id(self, job_id: UUID) -> Job | None:
        """Read the job with a given `Job.id`.

        Parameters
        ----------
        job_id : UUID
            The job's id, such as `Match.job_id`.

        Returns
        -------
        Job or None
            The job with its current rubric, or None if no job has that id.
        """
        with self.transaction() as s:
            row = s.scalar(select(JobRow).filter_by(job_id=job_id))
            return _load_job(s, row) if row else None

    def save_job(self, name: str, job: Job, step: str) -> None:
        """Make `job` the current job, store its rubric version and keep a history.

        Saving a rubric version that is already stored replaces it, unless matches
        refer to it: then it must be unchanged. A job with a new id (the ad was
        extracted again) replaces the job and its rubric versions, unless any of
        them have matches.

        Parameters
        ----------
        name : str
            The job.
        job : Job
            The job after `step`.
        step : str
            What produced it, such as "ad" or "rubric".

        Raises
        ------
        NotFound
            If there is no such job.
        RubricLocked
            If the save would change a rubric version that matches refer to.
        ValueError
            If another job has the same id.
        """
        with self.transaction() as s:
            row = _job(s, name)
            _store_job(s, row, job)
            s.add(
                JobHistoryRow(
                    job_id=row.id,
                    step=step,
                    job=job.model_dump(mode="json"),
                    saved_at=datetime.now(),
                )
            )

    def job_history(self, name: str) -> list[str]:
        """List the steps a job went through, oldest first.

        Parameters
        ----------
        name : str
            The job.

        Returns
        -------
        list of str
            Step names, such as ["ad", "rubric"].

        Raises
        ------
        NotFound
            If there is no such job.
        """
        with self.transaction() as s:
            row = _job(s, name)
            query = (
                select(JobHistoryRow.step)
                .filter_by(job_id=row.id)
                .order_by(JobHistoryRow.id)
            )
            return list(s.scalars(query))

    def rubric(self, job_id: UUID, version: int) -> Rubric | None:
        """Read one version of a job's rubric.

        Parameters
        ----------
        job_id : UUID
            The `Job.id`.
        version : int
            The `Rubric.version`.

        Returns
        -------
        Rubric or None
            That version, or None if it isn't stored.
        """
        with self.transaction() as s:
            version_row = _rubric_row(s, job_id, version)
            return _load_rubric(s, version_row) if version_row else None

    # Matches

    def save_match(self, match: Match, audit: AuditEntry | None = None) -> None:
        """Store a match. Matches are never changed afterwards.

        Parameters
        ----------
        match : Match
            The match. Its job and rubric version must be stored, and every
            criterion score must be for a criterion in that version.
        audit : AuditEntry or None, optional
            The match's audit entry (`unapply.matching.audit.match_entry`), stored
            in the same transaction, so there is no match without its entry.

        Raises
        ------
        NotFound
            If the job or rubric version isn't stored.
        ValueError
            If a match with the same id exists, a score is for an unknown
            criterion, or `audit` isn't this match's entry.
        """
        if audit is not None and (audit.kind, audit.match_id) != (
            AuditKind.MATCH,
            match.id,
        ):
            raise ValueError(f"the audit entry isn't for match {match.id}")
        with self.transaction() as s:
            version_row = _rubric_row(s, match.job_id, match.rubric_version)
            if version_row is None:
                raise NotFound(
                    f"no rubric version {match.rubric_version} for job {match.job_id}"
                )
            if s.get(MatchRow, match.id) is not None:
                raise ValueError(f"match {match.id} is already stored")
            criteria = set(
                s.scalars(
                    select(CriterionRow.criterion_id).filter_by(
                        rubric_version_id=version_row.id
                    )
                )
            )
            unknown = {c.criterion_id for c in match.criterion_scores} - criteria
            if unknown:
                raise ValueError(
                    f"scores for criteria not in rubric version "
                    f"{match.rubric_version}: {sorted(map(str, unknown))}"
                )
            s.add(
                MatchRow(
                    id=match.id,
                    job_id=match.job_id,
                    rubric_version_id=version_row.id,
                    profile_id=match.profile_id,
                    passed_hard_filters=match.passed_hard_filters,
                    model=match.model,
                    scored_at=match.scored_at,
                )
            )
            s.flush()
            for i, c in enumerate(match.criterion_scores):
                s.add(
                    CriterionScoreRow(
                        match_id=match.id,
                        position=i,
                        criterion_id=c.criterion_id,
                        score=c.score,
                        rationale=c.rationale,
                        evidence_ids=[str(e) for e in c.evidence_ids],
                    )
                )
            if audit is not None:
                _store_audit(s, audit)

    def matches(self, job_id: UUID, rubric_version: int | None = None) -> list[Match]:
        """Read a job's matches, oldest first.

        Parameters
        ----------
        job_id : UUID
            The `Job.id`.
        rubric_version : int or None, optional
            Only matches against this rubric version. By default all.

        Returns
        -------
        list of Match
            The matches, possibly none.
        """
        with self.transaction() as s:
            query = (
                select(MatchRow, RubricVersionRow.version)
                .join(RubricVersionRow)
                .where(MatchRow.job_id == job_id)
                .order_by(MatchRow.scored_at, MatchRow.id)
            )
            if rubric_version is not None:
                query = query.where(RubricVersionRow.version == rubric_version)
            return [_load_match(s, m, version) for m, version in s.execute(query)]

    # Audit log

    def append_audit(self, entry: AuditEntry) -> AuditEntry:
        """Add an entry to the audit log. Entries can't be changed or removed.

        Parameters
        ----------
        entry : AuditEntry
            The entry, such as `unapply.matching.audit.ranking_entry(...)`. Its
            `id` must be None.

        Returns
        -------
        AuditEntry
            The entry as stored, with its `id`.

        Raises
        ------
        ValueError
            If the entry has an id already.
        """
        with self.transaction() as s:
            return _store_audit(s, entry)

    def audit_log(
        self, job_id: UUID | None = None, kind: AuditKind | None = None
    ) -> list[AuditEntry]:
        """Read the audit log, oldest first.

        Parameters
        ----------
        job_id : UUID or None, optional
            Only entries for this `Job.id`. By default every job's.
        kind : AuditKind or None, optional
            Only matches or only rankings. By default both.

        Returns
        -------
        list of AuditEntry
            The entries, in the order they were recorded.
        """
        with self.transaction() as s:
            query = select(AuditEntryRow).order_by(AuditEntryRow.id)
            if job_id is not None:
                query = query.where(AuditEntryRow.job_id == job_id)
            if kind is not None:
                query = query.where(AuditEntryRow.kind == kind.value)
            return [_load_audit(row) for row in s.scalars(query)]

    # Employers' intents

    def record_intent(self, intent: Intent) -> tuple[Intent, bool]:
        """Record what an employer asks for about a candidate, once.

        Parameters
        ----------
        intent : Intent
            The request; its `id` must be None.

        Returns
        -------
        Intent
            The intent as stored, with its `id`: the earlier one if the same job,
            candidate and kind were recorded before.
        bool
            True if it was new.

        Raises
        ------
        ValueError
            If the intent has an id already.
        """
        if intent.id is not None:
            raise ValueError(f"intent {intent.id} is already stored")
        with self.transaction() as s:
            row = s.scalar(
                select(IntentRow).filter_by(
                    job_id=intent.job_id,
                    profile_id=intent.profile_id,
                    kind=intent.kind.value,
                )
            )
            if row is not None:
                return _load_intent(row), False
            row = IntentRow(
                job_id=intent.job_id,
                profile_id=intent.profile_id,
                kind=intent.kind.value,
                recorded_at=intent.recorded_at,
            )
            s.add(row)
            s.flush()
            return _load_intent(row), True

    def intents(self, job_id: UUID, kind: IntentKind | None = None) -> list[Intent]:
        """Read a job's intents, oldest first.

        Parameters
        ----------
        job_id : UUID
            The `Job.id`.
        kind : IntentKind or None, optional
            Only reveals or only application requests. By default both.

        Returns
        -------
        list of Intent
            In the order they were recorded.
        """
        with self.transaction() as s:
            query = select(IntentRow).filter_by(job_id=job_id).order_by(IntentRow.id)
            if kind is not None:
                query = query.where(IntentRow.kind == kind.value)
            return [_load_intent(row) for row in s.scalars(query)]

    # Candidates' consents

    def grant_consent(
        self,
        candidate: str,
        job: str,
        sections: list[ConsentSection] | None = None,
    ) -> Consent:
        """Opt a candidate in to a job, or change what its agent may read.

        Parameters
        ----------
        candidate : str
            The candidate.
        job : str
            The job.
        sections : list of ConsentSection or None, optional
            What the job's agent may read; by default every section.

        Returns
        -------
        Consent
            The consent as stored. Granting again replaces the sections and the
            time.

        Raises
        ------
        NotFound
            If there is no such candidate or job.
        """
        consent = Consent(
            candidate=candidate,
            job=job,
            **({} if sections is None else {"sections": sections}),
        )
        with self.transaction() as s:
            candidate_row = _candidate(s, candidate)
            job_row = _job(s, job)
            row = s.get(ConsentRow, (candidate_row.id, job_row.id))
            if row is None:
                row = ConsentRow(candidate_id=candidate_row.id, job_id=job_row.id)
                s.add(row)
            row.sections = [section.value for section in consent.sections]
            row.granted_at = consent.granted_at
        return consent

    def withdraw_consent(self, candidate: str, job: str) -> bool:
        """Opt a candidate out of a job: its agent no longer sees them.

        Parameters
        ----------
        candidate : str
            The candidate.
        job : str
            The job.

        Returns
        -------
        bool
            True if the candidate had opted in.

        Raises
        ------
        NotFound
            If there is no such candidate or job.
        """
        with self.transaction() as s:
            key = (_candidate(s, candidate).id, _job(s, job).id)
            row = s.get(ConsentRow, key)
            if row is None:
                return False
            s.delete(row)
            return True

    def consent(self, candidate: str, job: str) -> Consent | None:
        """Read a candidate's consent to a job.

        Parameters
        ----------
        candidate : str
            The candidate.
        job : str
            The job.

        Returns
        -------
        Consent or None
            The consent, or None if the candidate hasn't opted in.

        Raises
        ------
        NotFound
            If there is no such candidate or job.
        """
        with self.transaction() as s:
            key = (_candidate(s, candidate).id, _job(s, job).id)
            row = s.get(ConsentRow, key)
            return _load_consent(row, candidate, job) if row else None

    def consents(self, job: str) -> list[Consent]:
        """List the candidates who opted in to a job.

        Parameters
        ----------
        job : str
            The job.

        Returns
        -------
        list of Consent
            One per candidate, sorted by candidate name.

        Raises
        ------
        NotFound
            If there is no such job.
        """
        with self.transaction() as s:
            rows = s.execute(
                select(ConsentRow, CandidateRow.name)
                .join(CandidateRow, CandidateRow.id == ConsentRow.candidate_id)
                .where(ConsentRow.job_id == _job(s, job).id)
                .order_by(CandidateRow.name)
            )
            return [_load_consent(row, name, job) for row, name in rows]

    # Skill taxonomy

    def save_taxonomy(self, taxonomy: Taxonomy) -> None:
        """Replace the skill taxonomy in the database.

        Parameters
        ----------
        taxonomy : Taxonomy
            The new taxonomy, usually `unapply.taxonomy.default_taxonomy()`.
        """
        with self.transaction() as s:
            # Children first, so this doesn't rely on ON DELETE CASCADE.
            for table in (SkillRelationRow, SkillSynonymRow, TaxonomySkillRow):
                s.execute(delete(table))
            s.add_all(
                TaxonomySkillRow(
                    name=skill.name,
                    category=skill.category.value if skill.category else None,
                )
                for skill in taxonomy.skills
            )
            s.flush()
            for skill in taxonomy.skills:
                s.add_all(
                    SkillSynonymRow(synonym=synonym, skill=skill.name)
                    for synonym in skill.synonyms
                )
                for kind in ("implies", "broader"):
                    s.add_all(
                        SkillRelationRow(skill=skill.name, kind=kind, related=related)
                        for related in getattr(skill, kind)
                    )

    def taxonomy(self) -> Taxonomy:
        """Read the skill taxonomy.

        Returns
        -------
        Taxonomy
            The taxonomy last saved, or an empty one if none was.
        """
        with self.transaction() as s:
            synonyms: dict[str, list[str]] = {}
            for row in s.scalars(select(SkillSynonymRow)):
                synonyms.setdefault(row.skill, []).append(row.synonym)
            relations: dict[tuple[str, str], list[str]] = {}
            for row in s.scalars(select(SkillRelationRow)):
                relations.setdefault((row.skill, row.kind), []).append(row.related)
            return Taxonomy(
                skills=[
                    TaxonomySkill(
                        name=row.name,
                        category=row.category,
                        synonyms=synonyms.get(row.name, []),
                        implies=relations.get((row.name, "implies"), []),
                        broader=relations.get((row.name, "broader"), []),
                    )
                    for row in s.scalars(select(TaxonomySkillRow))
                ]
            )


def _check_name(name: str) -> None:
    if not NAME.match(name):
        raise ValueError(
            "use lowercase letters, digits, '-' and '_' only, starting with a "
            "letter or digit"
        )


def _candidate(s: Session, name: str, missing_ok: bool = False) -> CandidateRow:
    row = s.scalar(select(CandidateRow).filter_by(name=name))
    if row is None and not missing_ok:
        raise NotFound(f"no candidate called {name!r}")
    return row  # type: ignore[return-value]


def _job(s: Session, name: str, missing_ok: bool = False) -> JobRow:
    row = s.scalar(select(JobRow).filter_by(name=name))
    if row is None and not missing_ok:
        raise NotFound(f"no job called {name!r}")
    return row  # type: ignore[return-value]


def _pending(s: Session, row: CandidateRow) -> list[InterviewQuestionRow]:
    query = (
        select(InterviewQuestionRow)
        .filter_by(candidate_id=row.id)
        .where(InterviewQuestionRow.answer.is_(None))
        .order_by(InterviewQuestionRow.position)
    )
    return list(s.scalars(query))


def _ids(ids: list[UUID]) -> list[str]:
    return [str(i) for i in ids]


def _store_profile(s: Session, row: CandidateRow, profile: Profile) -> None:
    """Replace the candidate's profile rows with `profile`."""
    other = s.scalar(
        select(CandidateRow.name)
        .filter_by(profile_id=profile.id)
        .where(CandidateRow.id != row.id)
    )
    if other is not None:
        raise ValueError(f"profile {profile.id} belongs to candidate {other!r}")
    # Evidence first: it refers to sources.
    for table in (
        EvidenceRow,
        SourceRow,
        ExperienceRow,
        CandidateSkillRow,
        ClaimSupportRow,
    ):
        s.execute(delete(table).filter_by(candidate_id=row.id))

    p = profile.preferences
    row.profile_id = profile.id
    row.headline = profile.headline
    row.approved_by_candidate_at = profile.approved_by_candidate_at
    row.locations = list(p.locations)
    row.work_modes = [m.value for m in p.work_modes]
    row.salary_min = p.salary_min
    row.salary_currency = p.salary_currency
    row.work_permits = list(p.work_permits)
    row.dealbreakers = list(p.dealbreakers)
    s.flush()

    cid = row.id
    s.add_all(
        SourceRow(
            candidate_id=cid,
            id=x.id,
            position=i,
            kind=x.kind.value,
            uri=x.uri,
            uploaded_at=x.uploaded_at,
        )
        for i, x in enumerate(profile.sources)
    )
    s.flush()
    s.add_all(
        EvidenceRow(
            candidate_id=cid,
            id=e.id,
            position=i,
            source_id=e.source_id,
            quote=e.quote,
            locator=e.locator,
        )
        for i, e in enumerate(profile.evidence)
    )
    s.add_all(
        ExperienceRow(
            candidate_id=cid,
            id=x.id,
            position=i,
            title=x.title,
            organisation=x.organisation,
            start=x.start,
            end=x.end,
            start_precision=x.start_precision.value,
            end_precision=x.end_precision.value,
            summary=x.summary,
            skills=list(x.skills),
            evidence_ids=_ids(x.evidence_ids),
        )
        for i, x in enumerate(profile.experiences)
    )
    for i, k in enumerate(profile.skills):
        est = k.estimate
        s.add(
            CandidateSkillRow(
                candidate_id=cid,
                name=k.name,
                position=i,
                category=k.category.value if k.category else None,
                self_level=int(k.self_level) if k.self_level is not None else None,
                evidence_ids=_ids(k.evidence_ids),
                estimate_level=int(est.level) if est else None,
                estimate_confidence=est.confidence if est else None,
                estimate_rationale=est.rationale if est else None,
                estimate_evidence_ids=_ids(est.evidence_ids) if est else None,
                estimate_model=est.model if est else None,
                estimated_at=est.estimated_at if est else None,
            )
        )
    c = profile.claim_support
    if c is not None:
        s.add(
            ClaimSupportRow(
                candidate_id=cid,
                rated=c.rated,
                overclaims=list(c.overclaims),
                underclaims=list(c.underclaims),
                unverified=list(c.unverified),
                unsupported_claims=list(c.unsupported_claims),
                inconsistencies=list(c.inconsistencies),
                score=c.score,
                computed_at=c.computed_at,
            )
        )
    s.flush()


def _rows(s: Session, table: type, candidate_id: UUID) -> list[Any]:
    query = select(table).filter_by(candidate_id=candidate_id).order_by(table.position)
    return list(s.scalars(query))


def _load_profile(s: Session, row: CandidateRow) -> Profile | None:
    if row.profile_id is None:
        return None
    skills = []
    for k in _rows(s, CandidateSkillRow, row.id):
        estimate = None
        if k.estimate_level is not None:
            estimate = {
                "level": k.estimate_level,
                "confidence": k.estimate_confidence,
                "rationale": k.estimate_rationale,
                "evidence_ids": k.estimate_evidence_ids or [],
                "model": k.estimate_model,
                "estimated_at": k.estimated_at,
            }
        skills.append(
            {
                "name": k.name,
                "category": k.category,
                "self_level": k.self_level,
                "estimate": estimate,
                "evidence_ids": k.evidence_ids,
            }
        )
    claims = s.get(ClaimSupportRow, row.id)
    return Profile.model_validate(
        {
            "id": row.profile_id,
            "headline": row.headline,
            "sources": [
                {"id": x.id, "kind": x.kind, "uri": x.uri, "uploaded_at": x.uploaded_at}
                for x in _rows(s, SourceRow, row.id)
            ],
            "evidence": [
                {
                    "id": e.id,
                    "source_id": e.source_id,
                    "quote": e.quote,
                    "locator": e.locator,
                }
                for e in _rows(s, EvidenceRow, row.id)
            ],
            "experiences": [
                {
                    "id": x.id,
                    "title": x.title,
                    "organisation": x.organisation,
                    "start": x.start,
                    "end": x.end,
                    "start_precision": x.start_precision,
                    "end_precision": x.end_precision,
                    "summary": x.summary,
                    "skills": x.skills,
                    "evidence_ids": x.evidence_ids,
                }
                for x in _rows(s, ExperienceRow, row.id)
            ],
            "skills": skills,
            "preferences": {
                "locations": row.locations,
                "work_modes": row.work_modes,
                "salary_min": row.salary_min,
                "salary_currency": row.salary_currency,
                "work_permits": row.work_permits,
                "dealbreakers": row.dealbreakers,
            },
            "claim_support": None
            if claims is None
            else {
                "rated": claims.rated,
                "overclaims": claims.overclaims,
                "underclaims": claims.underclaims,
                "unverified": claims.unverified,
                "unsupported_claims": claims.unsupported_claims,
                "inconsistencies": claims.inconsistencies,
                "score": claims.score,
                "computed_at": claims.computed_at,
            },
            "approved_by_candidate_at": row.approved_by_candidate_at,
        }
    )


def _matched(s: Session, version_row: RubricVersionRow) -> bool:
    query = select(func.count()).where(MatchRow.rubric_version_id == version_row.id)
    return bool(s.scalar(query))


def _store_job(s: Session, row: JobRow, job: Job) -> None:
    """Make `job` the job's current state, storing its rubric version."""
    other = s.scalar(
        select(JobRow.name).filter_by(job_id=job.id).where(JobRow.id != row.id)
    )
    if other is not None:
        raise ValueError(f"job {job.id} is stored as {other!r}")
    versions = list(s.scalars(select(RubricVersionRow).filter_by(job_id=row.id)))
    if row.job_id is not None and row.job_id != job.id:
        # Extracted again: a new job under the same name.
        if any(_matched(s, v) for v in versions):
            raise RubricLocked(
                f"job {row.name!r} has matches, so it can't be replaced by a new "
                "extraction; create a new job instead"
            )
        for v in versions:
            s.delete(v)
        versions = []
        s.flush()

    row.job_id = job.id
    row.company = job.company
    row.title = job.title
    row.ad_text = job.ad_text
    row.reveal_quota = job.reveal_quota
    row.vacancies = job.vacancies
    row.created_at = job.created_at
    row.rubric_version = job.rubric.version

    rubric = job.rubric
    existing = next((v for v in versions if v.version == rubric.version), None)
    if existing is not None:
        if _matched(s, existing):
            if _load_rubric(s, existing) != rubric:
                raise RubricLocked(
                    f"rubric version {rubric.version} of job {row.name!r} has "
                    "matches and can't change; save the edit as a new version"
                )
            return
        s.delete(existing)
        s.flush()
    version_row = RubricVersionRow(
        job_id=row.id,
        version=rubric.version,
        hard_filters=rubric.hard_filters.model_dump(mode="json"),
        approved_at=rubric.approved_at,
    )
    s.add(version_row)
    s.flush()
    s.add_all(
        CriterionRow(
            rubric_version_id=version_row.id,
            criterion_id=c.id,
            position=i,
            kind=c.kind.value,
            description=c.description,
            skill=c.skill,
            min_level=int(c.min_level) if c.min_level is not None else None,
            weight=c.weight,
            source_quote=c.source_quote,
        )
        for i, c in enumerate(rubric.criteria)
    )
    s.flush()


def _rubric_row(s: Session, job_id: UUID, version: int) -> RubricVersionRow | None:
    query = (
        select(RubricVersionRow)
        .join(JobRow, RubricVersionRow.job_id == JobRow.id)
        .where(JobRow.job_id == job_id, RubricVersionRow.version == version)
    )
    return s.scalar(query)


def _load_rubric(s: Session, version_row: RubricVersionRow) -> Rubric:
    query = (
        select(CriterionRow)
        .filter_by(rubric_version_id=version_row.id)
        .order_by(CriterionRow.position)
    )
    return Rubric.model_validate(
        {
            "version": version_row.version,
            "hard_filters": version_row.hard_filters,
            "criteria": [
                {
                    "id": c.criterion_id,
                    "kind": c.kind,
                    "description": c.description,
                    "skill": c.skill,
                    "min_level": c.min_level,
                    "weight": c.weight,
                    "source_quote": c.source_quote,
                }
                for c in s.scalars(query)
            ],
            "approved_at": version_row.approved_at,
        }
    )


def _load_job(s: Session, row: JobRow) -> Job | None:
    if row.job_id is None or row.rubric_version is None:
        return None
    version_row = s.scalar(
        select(RubricVersionRow).filter_by(job_id=row.id, version=row.rubric_version)
    )
    return Job.model_validate(
        {
            "id": row.job_id,
            "company": row.company,
            "title": row.title,
            "ad_text": row.ad_text,
            "rubric": _load_rubric(s, version_row),
            "reveal_quota": row.reveal_quota,
            "vacancies": row.vacancies,
            "created_at": row.created_at,
        }
    )


def _load_match(s: Session, m: MatchRow, rubric_version: int) -> Match:
    query = (
        select(CriterionScoreRow)
        .filter_by(match_id=m.id)
        .order_by(CriterionScoreRow.position)
    )
    return Match.model_validate(
        {
            "id": m.id,
            "job_id": m.job_id,
            "profile_id": m.profile_id,
            "rubric_version": rubric_version,
            "passed_hard_filters": m.passed_hard_filters,
            "criterion_scores": [
                {
                    "criterion_id": c.criterion_id,
                    "score": c.score,
                    "rationale": c.rationale,
                    "evidence_ids": c.evidence_ids,
                }
                for c in s.scalars(query)
            ],
            "model": m.model,
            "scored_at": m.scored_at,
        }
    )


_AUDIT_FIELDS = (
    "kind",
    "job_id",
    "rubric_version",
    "rubric_hash",
    "scorer",
    "model",
    "match_id",
    "profile_id",
    "profile_hash",
    "payload",
    "recorded_at",
)


def _store_audit(s: Session, entry: AuditEntry) -> AuditEntry:
    if entry.id is not None:
        raise ValueError(f"audit entry {entry.id} is already stored")
    values = {f: getattr(entry, f) for f in _AUDIT_FIELDS}
    row = AuditEntryRow(**{**values, "kind": entry.kind.value})
    s.add(row)
    s.flush()
    return entry.model_copy(update={"id": row.id})


def _load_audit(row: AuditEntryRow) -> AuditEntry:
    return AuditEntry.model_validate(
        {"id": row.id, **{f: getattr(row, f) for f in _AUDIT_FIELDS}}
    )


def _load_intent(row: IntentRow) -> Intent:
    return Intent(
        id=row.id,
        job_id=row.job_id,
        profile_id=row.profile_id,
        kind=IntentKind(row.kind),
        recorded_at=row.recorded_at,
    )


def _load_consent(row: ConsentRow, candidate: str, job: str) -> Consent:
    return Consent(
        candidate=candidate,
        job=job,
        sections=[ConsentSection(v) for v in row.sections],
        granted_at=row.granted_at,
    )
