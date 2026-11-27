"""The ranking audit log: what was scored and ranked, with what, and when.

Ranking job candidates is high-risk under the EU AI Act, so every match and every
ranking is recorded in an append-only log (the `audit_log` table). An entry keeps
enough to check a ranking later without trusting anything else in the database:

- a **match** entry: the `Match` with its scores, the hard filter outcomes, the
  scorer and model, the rubric version and a hash of it, and a hash of the profile
  that was scored (its "profile version");
- a **ranking** entry: the rubric version used, in full, and each ranked match in
  full, with its rank and total;
- a **reveal** entry: an employer saw who a candidate is, with the profile version
  revealed and where payment would have been taken (see `unapply.jobs.hiring`).

`reproduce_ranking` ranks a ranking entry's matches again with its rubric, and
`check_ranking` says whether that gives back the recorded ranking and agrees with
the match entries.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from unapply.matching.scoring import MatchResult, Ranked, rank
from unapply.schemas import Job, Match, Profile, Rubric


class AuditKind(StrEnum):
    """What an audit entry records."""

    MATCH = "match"
    RANKING = "ranking"
    REVEAL = "reveal"


class AuditEntry(BaseModel):
    """One entry in the audit log.

    Parameters
    ----------
    id : int or None
        Given by the database when the entry is stored, in the order entries were
        recorded; None before.
    kind : AuditKind
        A match, a ranking or a reveal.
    job_id : UUID
        The `Job.id`.
    rubric_version : int
        The `Rubric.version` scored against.
    rubric_hash : str
        `content_hash` of that rubric version.
    scorer : str
        The scorer, "baseline" or "llm". A ranking of matches by several scorers
        lists them all, sorted and separated by ", ". "employer" for a reveal.
    model : str
        `Match.model`, such as "baseline-v1" or a model name. Several, like
        `scorer`, for a ranking. "none" for a reveal.
    match_id : UUID or None
        The `Match.id` of a match entry; None for a ranking.
    profile_id : UUID or None
        The `Profile.id` scored, for a match entry, or revealed, for a reveal;
        None for a ranking.
    profile_hash : str or None
        `content_hash` of the profile scored or revealed: the profile version.
        None for a ranking, and for a reveal of a profile since replaced.
    payload : dict
        For a match: "match" (the `Match`), "hard_filters" (name, outcome and
        reason of each) and "problems". For a ranking: "rubric" (the `Rubric`) and
        "ranking" (rank, total and the `Match`, best first). For a reveal:
        "charge" (where payment would have been taken). JSON-ready.
    recorded_at : datetime
        When the entry was made, local time.
    """

    id: int | None = None
    kind: AuditKind
    job_id: UUID
    rubric_version: int
    rubric_hash: str
    scorer: str
    model: str
    match_id: UUID | None = None
    profile_id: UUID | None = None
    profile_hash: str | None = None
    payload: dict[str, Any]
    recorded_at: datetime = Field(default_factory=datetime.now)


def content_hash(model: BaseModel) -> str:
    """Hash a schema's content, to tell later whether it is still the same.

    Parameters
    ----------
    model : BaseModel
        Such as a `Profile` or a `Rubric`.

    Returns
    -------
    str
        "sha256:" and the hex digest of its JSON with sorted keys. Equal objects
        give equal hashes, also after a round trip through the database.
    """
    text = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def match_entry(
    result: MatchResult, profile: Profile, rubric: Rubric, scorer: str
) -> AuditEntry:
    """Make the audit entry for one match.

    Parameters
    ----------
    result : MatchResult
        The match, its hard filter outcomes and the scorer's problems.
    profile : Profile
        The profile that was scored.
    rubric : Rubric
        The rubric version it was scored against.
    scorer : str
        The scorer's name, "baseline" or "llm".

    Returns
    -------
    AuditEntry
        The entry, not stored yet.

    Raises
    ------
    ValueError
        If the profile or rubric isn't the one the match refers to.
    """
    match = result.match
    if match.profile_id != profile.id or match.rubric_version != rubric.version:
        raise ValueError("the profile or rubric isn't the one the match was scored on")
    return AuditEntry(
        kind=AuditKind.MATCH,
        job_id=match.job_id,
        rubric_version=rubric.version,
        rubric_hash=content_hash(rubric),
        scorer=scorer,
        model=match.model,
        match_id=match.id,
        profile_id=profile.id,
        profile_hash=content_hash(profile),
        payload={
            "match": match.model_dump(mode="json"),
            "hard_filters": [
                {"name": c.name, "outcome": c.outcome.value, "reason": c.reason}
                for c in result.filters.checks
            ],
            "problems": list(result.problems),
        },
    )


def ranking_entry(job: Job, ranking: list[Ranked], scorers: list[str]) -> AuditEntry:
    """Make the audit entry for a ranking.

    Parameters
    ----------
    job : Job
        The job, with the rubric version the matches were ranked against.
    ranking : list of Ranked
        The ranking, best first, as shown.
    scorers : list of str
        The names of the scorers that made the matches, "baseline" or "llm".

    Returns
    -------
    AuditEntry
        The entry, not stored yet.
    """
    return AuditEntry(
        kind=AuditKind.RANKING,
        job_id=job.id,
        rubric_version=job.rubric.version,
        rubric_hash=content_hash(job.rubric),
        scorer=", ".join(sorted(set(scorers))),
        model=", ".join(sorted({r.match.model for r in ranking})),
        payload={
            "rubric": job.rubric.model_dump(mode="json"),
            "ranking": [
                {
                    "rank": r.rank,
                    "total": r.total,
                    "match": r.match.model_dump(mode="json"),
                }
                for r in ranking
            ],
        },
    )


def reveal_entry(
    job: Job, profile_id: UUID, profile: Profile | None, charge: dict[str, Any]
) -> AuditEntry:
    """Make the audit entry for an employer revealing a candidate.

    Parameters
    ----------
    job : Job
        The job, with its current rubric.
    profile_id : UUID
        The profile revealed, as the shortlist showed it.
    profile : Profile or None
        The candidate's current profile, hashed if it is the one revealed.
    charge : dict
        Where payment would have been taken, JSON-ready.

    Returns
    -------
    AuditEntry
        The entry, not stored yet. It names no candidate: the profile id links it
        to the matches.
    """
    same = profile is not None and profile.id == profile_id
    return AuditEntry(
        kind=AuditKind.REVEAL,
        job_id=job.id,
        rubric_version=job.rubric.version,
        rubric_hash=content_hash(job.rubric),
        scorer="employer",
        model="none",
        profile_id=profile_id,
        profile_hash=content_hash(profile) if same and profile else None,
        payload={"charge": json.loads(json.dumps(charge, default=str))},
    )


def reproduce_ranking(entry: AuditEntry) -> list[Ranked]:
    """Rank a ranking entry's matches again, with the rubric it recorded.

    Parameters
    ----------
    entry : AuditEntry
        A ranking entry.

    Returns
    -------
    list of Ranked
        The ranking `rank` gives now, best first.

    Raises
    ------
    ValueError
        If the entry isn't a ranking.
    """
    if entry.kind is not AuditKind.RANKING:
        raise ValueError(f"audit entry {entry.id} is a {entry.kind}, not a ranking")
    rubric = Rubric.model_validate(entry.payload["rubric"])
    matches = [Match.model_validate(r["match"]) for r in entry.payload["ranking"]]
    return rank(matches, rubric)


def check_ranking(entry: AuditEntry, log: Sequence[AuditEntry] = ()) -> list[str]:
    """Check that a ranking entry reproduces and agrees with the rest of the log.

    Parameters
    ----------
    entry : AuditEntry
        A ranking entry.
    log : sequence of AuditEntry, optional
        Other entries, such as the job's whole log. Each ranked match that has a
        match entry among them must be recorded the same there, against the same
        rubric version.

    Returns
    -------
    list of str
        What doesn't agree; empty if the ranking is reproduced.

    Raises
    ------
    ValueError
        If the entry isn't a ranking.
    """
    problems = []
    rubric = Rubric.model_validate(entry.payload["rubric"])
    if (content_hash(rubric), rubric.version) != (
        entry.rubric_hash,
        entry.rubric_version,
    ):
        problems.append("the recorded rubric doesn't match its version or hash")
    recorded = [
        (r["rank"], r["total"], r["match"]["id"]) for r in entry.payload["ranking"]
    ]
    again = [(r.rank, r.total, str(r.match.id)) for r in reproduce_ranking(entry)]
    if again != recorded:
        problems.append(f"ranking again gives {again}, but {recorded} was recorded")
    matches = {
        str(e.match_id): e
        for e in log
        if e.kind is AuditKind.MATCH and e.job_id == entry.job_id
    }
    for r in entry.payload["ranking"]:
        logged = matches.get(r["match"]["id"])
        if logged is None:
            continue
        if logged.payload["match"] != r["match"]:
            problems.append(f"match {logged.match_id} differs from its match entry")
        if logged.rubric_hash != entry.rubric_hash:
            problems.append(
                f"match {logged.match_id} was scored against another rubric"
            )
    return problems
