"""Messages between an employer and a candidate they revealed.

Once an employer reveals a candidate for a job (`unapply.jobs.hiring.reveal`), the
two can write to each other: one thread per candidate and job, in the order sent.
Before the reveal there is no thread, so neither side can read or write one; after
it the thread stays, as a revealed candidate can't withdraw. There are no emails or
push notifications: each side sees how many messages it hasn't read yet.

Messages are the candidate's personal data: they go with the candidate, and the
candidate can export them (`GET /candidates/<name>/messages`).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from unapply.db.repository import Repository

Sender = Literal["candidate", "employer"]
MAX_MESSAGE_CHARS = 5_000


class Message(BaseModel):
    """One message in a thread between an employer and a candidate.

    Parameters
    ----------
    id : int
        Given by the database; later messages have higher ids.
    sender : {"candidate", "employer"}
        Who wrote it.
    text : str
        What they wrote, without surrounding whitespace.
    sent_at : datetime
        When it was sent, local time.
    read_at : datetime or None
        When the other side first opened the thread after it was sent; None while
        it is unread.
    """

    id: int
    sender: Sender
    text: str
    sent_at: datetime
    read_at: datetime | None = None


class MessageError(ValueError):
    """There is no thread: the employer hasn't revealed the candidate."""


class BadMessage(ValueError):
    """A message that is empty or too long. The message says which."""


def other(side: Sender) -> Sender:
    """Name the other side of a thread.

    Parameters
    ----------
    side : {"candidate", "employer"}
        One side.

    Returns
    -------
    {"candidate", "employer"}
        The other.
    """
    return "employer" if side == "candidate" else "candidate"


def unread(messages: list[Message], reader: Sender) -> int:
    """Count the messages a reader hasn't read: the other side's, without `read_at`.

    Parameters
    ----------
    messages : list of Message
        A thread.
    reader : {"candidate", "employer"}
        Whose unread messages to count.

    Returns
    -------
    int
        How many.
    """
    return sum(m.sender != reader and m.read_at is None for m in messages)


def thread(repo: Repository, candidate: str, job: str) -> list[Message]:
    """Read the thread between a revealed candidate and a job's employer.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.

    Returns
    -------
    list of Message
        Oldest first; empty if neither side has written yet.

    Raises
    ------
    MessageError
        If the employer hasn't revealed the candidate: there is no thread yet.
    NotFound
        If there is no such candidate or job.
    """
    _need_reveal(repo, candidate, job)
    return repo.messages(candidate, job)


def send(
    repo: Repository, candidate: str, job: str, sender: Sender, text: str
) -> Message:
    """Add a message to the thread between a revealed candidate and a job's employer.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.
    sender : {"candidate", "employer"}
        Who writes it.
    text : str
        What they write: not empty, at most `MAX_MESSAGE_CHARS` characters once
        surrounding whitespace is removed.

    Returns
    -------
    Message
        The message as stored.

    Raises
    ------
    MessageError
        If the candidate isn't revealed yet.
    BadMessage
        If the text is empty or too long.
    NotFound
        If there is no such candidate or job.
    """
    _need_reveal(repo, candidate, job)
    text = text.strip()
    if not text:
        raise BadMessage("write something to send")
    if len(text) > MAX_MESSAGE_CHARS:
        raise BadMessage(f"a message is at most {MAX_MESSAGE_CHARS} characters")
    return repo.add_message(candidate, job, sender, text)


def mark_read(
    repo: Repository, candidate: str, job: str, reader: Sender
) -> list[Message]:
    """Mark the other side's messages in a thread as read by `reader`.

    Parameters
    ----------
    repo : Repository
        The database.
    candidate : str
        The candidate.
    job : str
        The job.
    reader : {"candidate", "employer"}
        Who opened the thread.

    Returns
    -------
    list of Message
        The thread, oldest first, with nothing left unread for `reader`.

    Raises
    ------
    MessageError
        If the employer hasn't revealed the candidate: there is no thread yet.
    NotFound
        If there is no such candidate or job.
    """
    _need_reveal(repo, candidate, job)
    repo.mark_read(candidate, job, sender=other(reader))
    return repo.messages(candidate, job)


def _need_reveal(repo: Repository, candidate: str, job: str) -> None:
    progress = repo.progress(candidate, job)
    if progress is None or progress.revealed_at is None:
        raise MessageError(
            "there are no messages before the employer reveals the candidate"
        )
