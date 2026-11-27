"""What a job's matching agent may read about candidates, checked against consent.

`AgentTools` holds the logic behind the MCP tools in `unapply.mcp_server.server`,
so it can be tested without MCP. It is scoped to one job, and only sees candidates
who opted in to that job (`unapply.consent`) with an approved profile, and only the
sections each shared. Consent is read again on every call, so a withdrawal takes
effect at once.

The agent never learns who a candidate is. Candidates are known by their profile
id and an alias (as on the employer's shortlist), every text from the profile goes
through `anonymise.redact`, and nothing reveals the candidate's name in the
database, their source files or contact details. Claim support (overclaims and
the like) isn't offered either, as on the shortlist. A candidate who doesn't exist
and one who hasn't opted in get the same answer, so the agent can't tell them apart.
"""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel

from unapply.consent import Consent, ConsentSection
from unapply.dates import format_partial_date
from unapply.db.repository import Repository
from unapply.matching.anonymise import redact
from unapply.matching.shortlist import alias
from unapply.schemas import (
    CriterionKind,
    HardFilters,
    Profile,
    SkillCategory,
    SkillLevel,
    SourceKind,
    WorkMode,
)
from unapply.taxonomy import Taxonomy, default_taxonomy

#: Most quotes `search_evidence` returns in one call.
MAX_RESULTS = 50


class ToolRefused(LookupError):
    """The agent asked for something this job may not read, or that doesn't exist.

    The message is written for the agent, and says nothing about candidates who
    haven't opted in.
    """


class CriterionView(BaseModel):
    """One criterion of the job's rubric.

    Parameters
    ----------
    id : str
        The criterion's id.
    kind : CriterionKind
        "must_have" or "nice_to_have".
    description : str
        What the job asks for, in the employer's words.
    skill : str or None
        The canonical skill it is about, if any.
    min_level : SkillLevel or None
        The lowest level that meets it, from 1 to 5, if given.
    weight : float
        How much it counts, from 1 to 5.
    """

    id: str
    kind: CriterionKind
    description: str
    skill: str | None
    min_level: SkillLevel | None
    weight: float


class RubricView(BaseModel):
    """The job the agent is matching for, and its rubric.

    Parameters
    ----------
    title : str
        The job's title.
    company : str
        The employer.
    rubric_version : int
        The rubric's version; it changes whenever the employer edits it.
    approved : bool
        Whether the employer approved this version.
    hard_filters : HardFilters
        Location, work mode, work permit and years of experience, which are
        checked in code before any scoring.
    criteria : list of CriterionView
        What candidates are scored on, in the employer's order.
    """

    title: str
    company: str
    rubric_version: int
    approved: bool
    hard_filters: HardFilters
    criteria: list[CriterionView]


class CandidateEntry(BaseModel):
    """A candidate who opted in to the job.

    Parameters
    ----------
    candidate_id : str
        Their profile id: what every other tool takes.
    alias : str
        What to call them, such as "Candidate 3F2A".
    shared : list of ConsentSection
        The sections they shared with this job; the tools for the others refuse.
    """

    candidate_id: str
    alias: str
    shared: list[ConsentSection]


class ExperienceView(BaseModel):
    """A role, project or education entry, anonymised.

    Parameters
    ----------
    id : str
        The experience's id.
    title : str
        Role or programme title.
    organisation : str
        Employer, client or institution.
    start : str or None
        "YYYY" or "YYYY-MM", as precisely as known; None if unknown.
    end : str or None
        The same; None means current or unknown.
    summary : str
        What the candidate did.
    skills : list of str
        Canonical names of the skills used.
    evidence_ids : list of str
        Evidence for the entry (see `search_evidence`).
    """

    id: str
    title: str
    organisation: str
    start: str | None
    end: str | None
    summary: str
    skills: list[str]
    evidence_ids: list[str]


class ExperiencesView(BaseModel):
    """A candidate's headline and experience.

    Parameters
    ----------
    candidate_id : str
        Their profile id.
    headline : str
        One-line summary, anonymised.
    experiences : list of ExperienceView
        In the candidate's order, usually newest first.
    """

    candidate_id: str
    headline: str
    experiences: list[ExperienceView]


class SkillView(BaseModel):
    """One of a candidate's skills, with both levels.

    Parameters
    ----------
    name : str
        Canonical name.
    category : SkillCategory or None
        What kind of skill it is, if known.
    own_level : SkillLevel or None
        The level the candidate gives themselves, from 1 to 5.
    estimated_level : SkillLevel or None
        The level their evidence supports, from 1 to 5, once estimated.
    confidence : float or None
        How sure the estimate is, from 0 to 1; None without an estimate.
    evidence_ids : list of str
        Evidence that mentions the skill.
    """

    name: str
    category: SkillCategory | None
    own_level: SkillLevel | None
    estimated_level: SkillLevel | None
    confidence: float | None
    evidence_ids: list[str]


class SkillsView(BaseModel):
    """A candidate's skills.

    Parameters
    ----------
    candidate_id : str
        Their profile id.
    skills : list of SkillView
        In the candidate's order.
    """

    candidate_id: str
    skills: list[SkillView]


class EvidenceHit(BaseModel):
    """A quote from a candidate's material that matches a search.

    Parameters
    ----------
    id : str
        The evidence id, as skills, experiences and scores cite it.
    source : str
        "cv", "linkedin", "github", "free_text", or "candidate statement" for an
        answer to a follow-up question.
    quote : str
        The quote, anonymised.
    skills : list of str
        The candidate's skills that cite it.
    """

    id: str
    source: str
    quote: str
    skills: list[str]


class EvidenceResults(BaseModel):
    """What `search_evidence` found, best match first.

    Parameters
    ----------
    candidate_id : str
        Their profile id.
    query : str
        The search, as given.
    results : list of EvidenceHit
        Quotes cited for the skill the query names (or a skill that counts for
        it, such as "dbt" for "sql") first, then quotes with more of the query's
        words.
    """

    candidate_id: str
    query: str
    results: list[EvidenceHit]


class PreferencesView(BaseModel):
    """What a candidate wants from a job.

    Parameters
    ----------
    candidate_id : str
        Their profile id.
    locations : list of str
        Acceptable cities or regions; empty means not given.
    work_modes : list of WorkMode
        Acceptable work modes; empty means any.
    salary_min : int or None
        Lowest yearly gross salary they accept, in `salary_currency`.
    salary_currency : str or None
        ISO 4217 code, such as "DKK".
    work_permits : list of str
        Where they may work: ISO country codes, or "EU".
    dealbreakers : list of str
        What they won't accept, in their words, anonymised.
    """

    candidate_id: str
    locations: list[str]
    work_modes: list[WorkMode]
    salary_min: int | None
    salary_currency: str | None
    work_permits: list[str]
    dealbreakers: list[str]


class AgentTools:
    """The reads a job's matching agent may make, scoped by consent.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job's name in the database.
    taxonomy : Taxonomy or None, optional
        For skills named in searches, by default `default_taxonomy()`.

    Raises
    ------
    NotFound
        If there is no such job.
    """

    def __init__(
        self, repo: Repository, job: str, taxonomy: Taxonomy | None = None
    ) -> None:
        repo.job_settings(job)  # Raises NotFound for an unknown job.
        self.repo = repo
        self.job = job
        self.taxonomy = taxonomy or default_taxonomy()

    def rubric(self) -> RubricView:
        """Describe the job and its current rubric.

        Returns
        -------
        RubricView
            The rubric's version, hard filters and criteria.

        Raises
        ------
        ToolRefused
            If the job has no rubric yet.
        """
        job = self.repo.job(self.job)
        if job is None:
            raise ToolRefused("this job has no rubric yet")
        return RubricView(
            title=job.title,
            company=job.company,
            rubric_version=job.rubric.version,
            approved=job.rubric.approved_at is not None,
            hard_filters=job.rubric.hard_filters,
            criteria=[
                CriterionView(
                    id=str(c.id),
                    kind=c.kind,
                    description=c.description,
                    skill=self.taxonomy.canonical(c.skill) if c.skill else None,
                    min_level=c.min_level,
                    weight=c.weight,
                )
                for c in job.rubric.criteria
            ],
        )

    def candidates(self) -> list[CandidateEntry]:
        """List the candidates who opted in to this job with an approved profile.

        Returns
        -------
        list of CandidateEntry
            Ordered by candidate id, which says nothing about the candidates.
        """
        entries = []
        for consent in self.repo.consents(self.job):
            profile = self.repo.profile(consent.candidate)
            if profile is not None and profile.approved_by_candidate_at is not None:
                entries.append(
                    CandidateEntry(
                        candidate_id=str(profile.id),
                        alias=alias(profile.id),
                        shared=consent.sections,
                    )
                )
        return sorted(entries, key=lambda e: e.candidate_id)

    def experiences(self, candidate_id: str) -> ExperiencesView:
        """Read a candidate's headline and experience.

        Parameters
        ----------
        candidate_id : str
            Their profile id, from `candidates`.

        Returns
        -------
        ExperiencesView
            Anonymised.

        Raises
        ------
        ToolRefused
            If the candidate isn't available to this job, or didn't share their
            experience with it.
        """
        profile, names = self._read(candidate_id, ConsentSection.EXPERIENCES)
        return ExperiencesView(
            candidate_id=str(profile.id),
            headline=redact(profile.headline, names),
            experiences=[
                ExperienceView(
                    id=str(x.id),
                    title=redact(x.title, names),
                    organisation=redact(x.organisation, names),
                    start=format_partial_date(x.start, x.start_precision) or None,
                    end=format_partial_date(x.end, x.end_precision) or None,
                    summary=redact(x.summary, names),
                    skills=list(x.skills),
                    evidence_ids=[str(i) for i in x.evidence_ids],
                )
                for x in profile.experiences
            ],
        )

    def skills(self, candidate_id: str) -> SkillsView:
        """Read a candidate's skills with their own and estimated levels.

        Parameters
        ----------
        candidate_id : str
            Their profile id, from `candidates`.

        Returns
        -------
        SkillsView
            Every skill; levels from 1 to 5.

        Raises
        ------
        ToolRefused
            If the candidate isn't available to this job, or didn't share their
            skills with it.
        """
        profile, _ = self._read(candidate_id, ConsentSection.SKILLS)
        return SkillsView(
            candidate_id=str(profile.id),
            skills=[
                SkillView(
                    name=s.name,
                    category=s.category,
                    own_level=s.self_level,
                    estimated_level=s.estimate.level if s.estimate else None,
                    confidence=s.estimate.confidence if s.estimate else None,
                    evidence_ids=[str(i) for i in s.evidence_ids],
                )
                for s in profile.skills
            ],
        )

    def search_evidence(
        self, candidate_id: str, query: str, limit: int = 10
    ) -> EvidenceResults:
        """Find quotes from a candidate's material about a skill or topic.

        Parameters
        ----------
        candidate_id : str
            Their profile id, from `candidates`.
        query : str
            A skill (any name the taxonomy knows, such as "scikit learn"), or
            words to look for, such as "demand forecasting".
        limit : int, optional
            Most quotes to return, from 1 to `MAX_RESULTS`; by default 10.

        Returns
        -------
        EvidenceResults
            Quotes cited for the skill the query names, or for a skill that counts
            for it, first; then quotes containing more of the query's words as
            whole words, ignoring case. Ties keep the profile's order. Quotes
            matching nothing are left out.

        Raises
        ------
        ToolRefused
            If the candidate isn't available to this job or didn't share their
            evidence with it, the query has no words, or `limit` is out of range.
        """
        if not 1 <= limit <= MAX_RESULTS:
            raise ToolRefused(f"limit must be from 1 to {MAX_RESULTS}")
        words = list(dict.fromkeys(re.findall(r"\w[\w+#.-]*", query.lower())))
        words = [w.rstrip(".-") for w in words]
        if not words:
            raise ToolRefused("give a skill or some words to search for")
        profile, names = self._read(candidate_id, ConsentSection.EVIDENCE)

        wanted = self.taxonomy.canonical(query)
        related = {wanted} | self.taxonomy.supporting(wanted)
        cited_for: dict[UUID, list[str]] = {}
        linked: set[UUID] = set()
        for s in profile.skills:
            for i in s.evidence_ids:
                cited_for.setdefault(i, []).append(s.name)
            if self.taxonomy.canonical(s.name) in related:
                linked.update(s.evidence_ids)
        for x in profile.experiences:
            if any(self.taxonomy.canonical(k) in related for k in x.skills):
                linked.update(x.evidence_ids)

        kinds = {s.id: s.kind for s in profile.sources}
        scored = []
        for position, e in enumerate(profile.evidence):
            found = sum(
                bool(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", e.quote, re.I))
                for w in words
            )
            # Cited for the skill outranks any number of words found.
            score = 2 * (e.id in linked) + found / len(words)
            if score > 0:
                scored.append((-score, position, e))
        scored.sort(key=lambda t: t[:2])
        return EvidenceResults(
            candidate_id=str(profile.id),
            query=query,
            results=[
                EvidenceHit(
                    id=str(e.id),
                    source=_source(kinds.get(e.source_id)),
                    quote=redact(e.quote, names),
                    skills=cited_for.get(e.id, []),
                )
                for _, _, e in scored[:limit]
            ],
        )

    def preferences(self, candidate_id: str) -> PreferencesView:
        """Read what a candidate wants from a job.

        Parameters
        ----------
        candidate_id : str
            Their profile id, from `candidates`.

        Returns
        -------
        PreferencesView
            Locations, work modes, salary, work permits and dealbreakers.

        Raises
        ------
        ToolRefused
            If the candidate isn't available to this job, or didn't share their
            preferences with it.
        """
        profile, names = self._read(candidate_id, ConsentSection.PREFERENCES)
        p = profile.preferences
        return PreferencesView(
            candidate_id=str(profile.id),
            locations=list(p.locations),
            work_modes=list(p.work_modes),
            salary_min=p.salary_min,
            salary_currency=p.salary_currency,
            work_permits=list(p.work_permits),
            dealbreakers=[redact(d, names) for d in p.dealbreakers],
        )

    def _read(
        self, candidate_id: str, section: ConsentSection
    ) -> tuple[Profile, list[str]]:
        """Load a candidate's profile if they shared `section` with this job.

        Returns the profile and the names to redact from it. Unknown ids, old
        profile ids, candidates who haven't opted in and unapproved profiles all
        get the same refusal.
        """
        unknown = ToolRefused(
            f"no candidate {candidate_id!r} has opted in to this job; "
            "list_candidates gives the ids"
        )
        try:
            profile_id = UUID(candidate_id)
        except ValueError:
            raise unknown from None
        name = self.repo.candidate_of(profile_id)
        consent: Consent | None = self.repo.consent(name, self.job) if name else None
        profile = self.repo.profile(name) if consent else None
        if (
            consent is None
            or profile is None
            or profile.id != profile_id
            or profile.approved_by_candidate_at is None
        ):
            raise unknown
        if not consent.allows(section):
            raise ToolRefused(
                f"{alias(profile_id)} hasn't shared their {section.value} with this "
                f"job; they shared: {', '.join(consent.sections) or 'nothing yet'}"
            )
        github = self.repo.settings(name).get("github")
        return profile, [github] if github else []


def _source(kind: SourceKind | None) -> str:
    """Name a source kind for the agent, as the shortlist does."""
    if kind is None:
        return "unknown"
    return "candidate statement" if kind == SourceKind.INTERVIEW else kind.value
