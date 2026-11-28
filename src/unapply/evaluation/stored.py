"""A job's ranking from the audit log, to compare with references.

The pool's rankings are made by `unapply evaluate` itself. A real job's rankings are
the ones its employer saw: each is kept in full in the audit log
(`unapply.matching.audit`), so it can be read back and compared with the shortlists
of the people who hire, without scoring anyone again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from unapply.matching.audit import AuditKind
from unapply.matching.scoring import Ranked
from unapply.schemas import Match

if TYPE_CHECKING:
    from unapply.db.repository import Repository


@dataclass
class StoredRanking:
    """A ranking from the audit log, with each candidate's name.

    Parameters
    ----------
    entry_id : int
        The ranking's id in the audit log, as `unapply audit` lists it.
    recorded_at : datetime
        When it was ranked.
    rubric_version : int
        The rubric version ranked against.
    scorer : str
        The scorers whose matches were ranked, such as "baseline".
    model : str
        The models or methods that scored, such as "baseline-v1".
    ranking : list of tuple of (str, Ranked)
        Candidate name and place, best first. A profile that no candidate in the
        database has had is named "profile <id>".
    """

    entry_id: int
    recorded_at: datetime
    rubric_version: int
    scorer: str
    model: str
    ranking: list[tuple[str, Ranked]]


def stored_ranking(
    repo: Repository, job: str, entry_id: int | None = None
) -> StoredRanking:
    """Read one of a job's rankings from the audit log. Nothing is stored.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job's name.
    entry_id : int or None, optional
        The ranking's id in the audit log. By default the job's latest ranking.

    Returns
    -------
    StoredRanking
        The ranking, with the candidates named as in the database.

    Raises
    ------
    NotFound
        If there is no such job.
    ValueError
        If the job has no rubric or hasn't been ranked, or `entry_id` isn't one of
        its rankings.
    """
    current = repo.job(job)
    if current is None:
        raise ValueError(f"job {job!r} has no rubric, so it hasn't been ranked")
    rankings = repo.audit_log(current.id, AuditKind.RANKING)
    if not rankings:
        raise ValueError(f"job {job!r} hasn't been ranked yet (see `unapply match`)")
    if entry_id is None:
        entry = rankings[-1]
    else:
        found = [e for e in rankings if e.id == entry_id]
        if not found:
            ids = ", ".join(str(e.id) for e in rankings)
            raise ValueError(
                f"no ranking {entry_id} of job {job!r}; its rankings are {ids}"
            )
        entry = found[0]
    names = {
        profile_id: name
        for name in repo.candidate_names()
        for profile_id in repo.profile_ids(name)
    }
    ranking = []
    for r in entry.payload["ranking"]:
        match = Match.model_validate(r["match"])
        name = names.get(match.profile_id, f"profile {match.profile_id}")
        ranking.append((name, Ranked(rank=r["rank"], total=r["total"], match=match)))
    assert entry.id is not None  # Read from the database.
    return StoredRanking(
        entry_id=entry.id,
        recorded_at=entry.recorded_at,
        rubric_version=entry.rubric_version,
        scorer=entry.scorer,
        model=entry.model,
        ranking=ranking,
    )
