"""What happens after the shortlist: reveal, request an application, apply or decline.

An employer's actions on a candidate go in one order:

1. **Reveal**: the employer sees who the candidate is (name, contact details, and the
   quotes behind each score). Anyone connected to the job can be revealed, as
   connecting is the candidate's consent; there is no accept step. Reveals are
   limited by the job's `reveal_quota` and recorded in the audit log. No payment is
   taken: a `ChargeIntent` is recorded where payment would happen.
2. **Request application**: only once revealed. The candidate sees the request in
   their app and then
3. **applies**, with a letter or files (or both), or **declines**. The employer sees
   the application.

Each step is kept in one `Progress` per candidate and job. Once revealed, a candidate
can't withdraw their connection (see `unapply.jobs.board.withdraw`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from unapply.jobs.board import connected
from unapply.matching.audit import reveal_entry

if TYPE_CHECKING:
    from unapply.db.repository import Repository


class Stage(StrEnum):
    """How far a connected candidate has got on a job, in order."""

    CONNECTED = "connected"
    REVEALED = "revealed"
    REQUESTED = "requested"
    APPLIED = "applied"
    DECLINED = "declined"


Answer = Literal["applied", "declined"]


class ChargeIntent(BaseModel):
    """Where payment for a reveal would be taken. Nothing is charged.

    Parameters
    ----------
    charged : bool
        Always False: there is no payment yet.
    note : str
        Says so.
    recorded_at : datetime
        When the reveal would have been paid for, local time.
    """

    charged: bool = False
    note: str = "No payment is taken: payment isn't built yet."
    recorded_at: datetime = Field(default_factory=datetime.now)


class ApplicationFile(BaseModel):
    """A file a candidate sent with their application.

    Parameters
    ----------
    id : int
        Given by the database.
    name : str
        The file name, without folders.
    size : int
        In bytes.
    uploaded_at : datetime
        When it was sent, local time.
    """

    id: int
    name: str
    size: int
    uploaded_at: datetime


class Progress(BaseModel):
    """How far a candidate got on a job after connecting, and their application.

    Parameters
    ----------
    candidate : str
        The candidate's name in the database. Never shown to an employer before a
        reveal.
    job : str
        The job's name in the database.
    revealed_at : datetime or None
        When the employer revealed them.
    revealed_profile_id : UUID or None
        The profile the employer revealed, as the shortlist showed it.
    charge : ChargeIntent or None
        Where the reveal would have been paid for.
    requested_at : datetime or None
        When the employer asked them to apply.
    answer : {"applied", "declined"} or None
        What the candidate answered, if they have.
    answered_at : datetime or None
        When.
    letter : str
        The application's text, such as a cover letter; empty if none.
    files : list of ApplicationFile
        Files sent with the application, in the order sent.
    """

    candidate: str
    job: str
    revealed_at: datetime | None = None
    revealed_profile_id: UUID | None = None
    charge: ChargeIntent | None = None
    requested_at: datetime | None = None
    answer: Answer | None = None
    answered_at: datetime | None = None
    letter: str = ""
    files: list[ApplicationFile] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stage(self) -> Stage:
        """How far the candidate got, from the times recorded."""
        if self.answer is not None:
            return Stage(self.answer)
        if self.requested_at is not None:
            return Stage.REQUESTED
        if self.revealed_at is not None:
            return Stage.REVEALED
        return Stage.CONNECTED


class Contact(BaseModel):
    """Who a candidate is: what an employer sees once they reveal them.

    Parameters
    ----------
    name : str
        The candidate's full name.
    email : str or None
        Email address, if given.
    phone : str or None
        Phone number, if given.
    """

    name: str
    email: str | None = None
    phone: str | None = None


class HiringError(ValueError):
    """An action that isn't allowed at this step. The message says why."""


class NotOnJob(LookupError):
    """No candidate connected to the job has this profile id."""


# Application material: text and documents, as for the candidate's own material.
APPLICATION_SUFFIXES = {".pdf", ".md", ".txt", ".docx", ".odt", ".rtf"}
MAX_LETTER_CHARS = 20_000


def candidate_on_job(repo: Repository, job: str, profile_id: UUID) -> str:
    """Find which connected candidate a shortlisted profile id belongs to.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.
    profile_id : UUID
        A profile id as the shortlist shows it: the candidate's current or an
        earlier one.

    Returns
    -------
    str
        The candidate's name.

    Raises
    ------
    NotOnJob
        If no candidate connected to the job has had that profile.
    NotFound
        If there is no such job.
    """
    for name in connected(repo, job):
        if profile_id in repo.profile_ids(name):
            return name
    raise NotOnJob(f"no candidate on job {job!r} has profile {profile_id}")


def reveal(repo: Repository, job: str, profile_id: UUID) -> tuple[Progress, bool]:
    """Reveal a connected candidate to the employer.

    Records a charge intent (nothing is paid) and an audit log entry. Revealing
    again changes nothing.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.
    profile_id : UUID
        The candidate, as the shortlist shows them.

    Returns
    -------
    tuple of Progress and bool
        The candidate's progress, and whether they were revealed just now.

    Raises
    ------
    NotOnJob
        If no connected candidate has that profile.
    HiringError
        If the job has no rubric yet, or every reveal of its quota is used.
    """
    candidate = candidate_on_job(repo, job, profile_id)
    current = repo.progress(candidate, job)
    if current is not None and current.revealed_at is not None:
        return current, False
    found = repo.job(job)
    if found is None:
        raise HiringError("the job has no rubric yet")
    used = sum(p.revealed_at is not None for p in repo.progresses(job=job))
    if used >= found.reveal_quota:
        raise HiringError(f"all {found.reveal_quota} reveals for this job are used")
    now = datetime.now()
    charge = ChargeIntent(recorded_at=now)
    progress = Progress(
        candidate=candidate,
        job=job,
        revealed_at=now,
        revealed_profile_id=profile_id,
        charge=charge,
    )
    profile = repo.profile(candidate)
    repo.save_progress(progress)
    repo.append_audit(
        reveal_entry(found, profile_id, profile, charge.model_dump(mode="json"))
    )
    return repo.progress(candidate, job) or progress, True


def request_application(
    repo: Repository, job: str, profile_id: UUID
) -> tuple[Progress, bool]:
    """Ask a revealed candidate to apply.

    Asking again changes nothing.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job.
    profile_id : UUID
        The candidate, as the shortlist shows them.

    Returns
    -------
    tuple of Progress and bool
        The candidate's progress, and whether they were asked just now.

    Raises
    ------
    NotOnJob
        If no connected candidate has that profile.
    HiringError
        If the candidate isn't revealed yet.
    """
    candidate = candidate_on_job(repo, job, profile_id)
    current = repo.progress(candidate, job)
    if current is None or current.revealed_at is None:
        raise HiringError("reveal the candidate before requesting an application")
    if current.requested_at is not None:
        return current, False
    repo.save_progress(current.model_copy(update={"requested_at": datetime.now()}))
    return repo.progress(candidate, job) or current, True


def answer(
    repo: Repository,
    candidate: str,
    job: str,
    choice: Answer,
    letter: str = "",
    files: Sequence[tuple[str, bytes]] = (),
) -> Progress:
    """Apply for a job the employer asked the candidate to apply for, or decline.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.
    choice : {"applied", "declined"}
        Apply or decline.
    letter : str, optional
        The application's text. With "applied", a letter or at least one file is
        needed; with "declined", neither is kept.
    files : sequence of (str, bytes), optional
        File names and contents, already checked by the caller.

    Returns
    -------
    Progress
        The candidate's progress, with the answer.

    Raises
    ------
    HiringError
        If the employer hasn't asked them to apply, they already answered, or an
        application has neither a letter nor a file.
    NotFound
        If there is no such candidate or job.
    """
    current = repo.progress(candidate, job)
    if current is None or current.requested_at is None:
        raise HiringError("the employer hasn't asked you to apply for this job")
    if current.answer is not None:
        raise HiringError(f"you already {current.answer} for this job")
    letter = letter.strip()
    if choice == "applied" and not letter and not files:
        raise HiringError("write a letter or add a file to apply")
    if len(letter) > MAX_LETTER_CHARS:
        raise HiringError(f"the letter is over {MAX_LETTER_CHARS} characters")
    applied = choice == "applied"
    repo.save_progress(
        current.model_copy(
            update={
                "answer": choice,
                "answered_at": datetime.now(),
                "letter": letter if applied else "",
            }
        ),
        files if applied else (),
    )
    return repo.progress(candidate, job) or current


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d ()-]{6,}\d")


def contact_from_cv(text: str, fallback: str) -> Contact:
    """Read a name and contact details from the top of a Markdown CV.

    Used for demo candidates, whose CVs are fixtures; real candidates give their
    contact details themselves.

    Parameters
    ----------
    text : str
        The CV, whose first "# " heading is the name.
    fallback : str
        The name to use if the CV has no heading.

    Returns
    -------
    Contact
        The name, and the first email address and phone number in the first ten
        lines, if any.
    """
    head = text.splitlines()[:10]
    name = next((x[2:].strip() for x in head if x.startswith("# ")), fallback)
    top = "\n".join(head)
    email = _EMAIL.search(top)
    phone = _PHONE.search(_EMAIL.sub("", top))
    return Contact(
        name=name or fallback,
        email=email.group(0) if email else None,
        phone=phone.group(0).strip() if phone else None,
    )
