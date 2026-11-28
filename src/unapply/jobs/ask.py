"""Ask about a revealed candidate: a model answers from their own material only.

Once an employer reveals a candidate, they can ask questions about them in plain
language ("Have they deployed models to production?"). A model answers from that
candidate's profile alone: the headline, the roles, the skills with the
candidate's own levels, and the evidence quotes, each with an id such as "E3". It
never sees the rubric, the estimated levels, the claim support, the candidate's
preferences, or anyone else. Each answer cites quotes; cited ids are checked to
belong to the candidate and others are dropped, and an answer that cites none of
the candidate's quotes counts as not answered by the material.

Conversations aren't saved: the employer's open page keeps them and sends the
earlier questions and answers along with each new one, so follow-up questions
work. Nothing here writes to the database, the audit log or a candidate's export.
Paid calls are refused unless allowed, as everywhere; pool candidates replay
hand-written stand-ins for a few demo questions (`demo_questions`).
"""

from __future__ import annotations

from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr

import yaml
from pydantic import BaseModel, Field

from unapply.app.demo import FIXTURES
from unapply.dates import format_partial_date
from unapply.jobs.hiring import HiringError, candidate_on_job
from unapply.llm import StructuredLLM
from unapply.matching.anonymise import redact
from unapply.schemas import Profile, SourceKind

if TYPE_CHECKING:
    from unapply.db.repository import Repository

MAX_QUESTION_CHARS = 500
# Earlier turns sent back by the page, so follow-ups have their context.
MAX_HISTORY = 10
MAX_TURN_ANSWER_CHARS = 4000
# Demo questions and their stand-in answers for the synthetic pool.
POOL = FIXTURES / "pool"
DEMO_QUESTIONS = POOL / "questions.yaml"


class NotRevealed(HiringError):
    """The employer hasn't revealed the candidate, so they can't ask about them."""


class BadQuestion(ValueError):
    """An empty or too long question, or too many earlier turns."""


class Turn(BaseModel):
    """An earlier question and its answer in the same conversation.

    Parameters
    ----------
    question : str
        What the employer asked.
    answer : str
        What the model answered.
    """

    question: str
    answer: str


class CitedQuote(BaseModel):
    """A quote from the candidate's material that an answer rests on.

    Parameters
    ----------
    id : UUID
        The `Evidence.id`.
    source : str
        Where it comes from: "cv", "github", ..., or "candidate statement" for
        what the candidate said in their interview.
    quote : str
        The quote, with contact details removed.
    """

    id: UUID
    source: str
    quote: str


class CandidateAnswer(BaseModel):
    """The answer to an employer's question about a revealed candidate.

    Parameters
    ----------
    question : str
        The question.
    answer : str
        The answer, in plain language.
    answered : bool
        Whether the candidate's material answers the question. False when the
        model says it doesn't, or cites none of the candidate's quotes.
    evidence : list of CitedQuote
        The quotes the answer rests on, all the candidate's own.
    model : str
        The model that answered, or the replay of a recording.
    problems : list of str
        What was wrong with the model's answer and dropped, such as cited ids that
        aren't the candidate's.
    asked_at : datetime
        When it was answered, local time.
    """

    question: str
    answer: str
    answered: bool
    evidence: list[CitedQuote] = Field(default_factory=list)
    model: str
    problems: list[str] = Field(default_factory=list)
    asked_at: datetime = Field(default_factory=datetime.now)


# The schema the model answers in. Its field descriptions are sent to the model,
# so they are written as instructions.


class ModelAnswer(BaseModel):
    """The model's answer to one question about the candidate."""

    answered: bool = Field(
        description="True only if the candidate's material answers the question. "
        "False if it says nothing about it, or too little to tell."
    )
    answer: str = Field(
        description="Two to five sentences for the employer, from the material "
        "only. If the material doesn't answer the question, say so and say what it "
        "does show that comes closest, if anything."
    )
    evidence: list[str] = Field(
        description="Ids of the quotes the answer rests on, such as 'E3'. Empty if "
        "the material doesn't answer the question."
    )


def revealed_candidate(repo: Repository, job: str, profile_id: UUID) -> str:
    """Find the candidate an employer asks about, checking they revealed them.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The employer's job.
    profile_id : UUID
        The candidate, as the shortlist shows them.

    Returns
    -------
    str
        The candidate's name in the database.

    Raises
    ------
    NotOnJob
        If no candidate connected to the job has that profile.
    NotRevealed
        If the employer hasn't revealed them on this job.
    """
    candidate = candidate_on_job(repo, job, profile_id)
    progress = repo.progress(candidate, job)
    if progress is None or progress.revealed_at is None:
        raise NotRevealed("reveal the candidate before asking about them")
    return candidate


def check_question(question: str, history: list[Turn]) -> str:
    """Check a question and the earlier turns sent with it.

    Parameters
    ----------
    question : str
        The question.
    history : list of Turn
        Earlier turns in the conversation, oldest first.

    Returns
    -------
    str
        The question, stripped.

    Raises
    ------
    BadQuestion
        If the question is empty or over `MAX_QUESTION_CHARS`, or there are more
        than `MAX_HISTORY` earlier turns or one of them is too long.
    """
    question = question.strip()
    if not question:
        raise BadQuestion("write a question")
    if len(question) > MAX_QUESTION_CHARS:
        raise BadQuestion(f"a question is at most {MAX_QUESTION_CHARS} characters")
    if len(history) > MAX_HISTORY:
        raise BadQuestion(f"at most {MAX_HISTORY} earlier questions are sent")
    for turn in history:
        if (
            len(turn.question) > MAX_QUESTION_CHARS
            or len(turn.answer) > MAX_TURN_ANSWER_CHARS
        ):
            raise BadQuestion("an earlier question or answer is too long")
    return question


def ask_candidate(
    profile: Profile,
    question: str,
    llm: StructuredLLM,
    history: list[Turn] | None = None,
    names: list[str] | None = None,
) -> CandidateAnswer:
    """Answer a question about a candidate from their own material, with one call.

    Parameters
    ----------
    profile : Profile
        The candidate's profile. Only their own material is sent: no estimates,
        claim support or preferences.
    question : str
        The employer's question, already checked (`check_question`).
    llm : StructuredLLM
        The model, or a replay of its answer.
    history : list of Turn or None, optional
        Earlier turns in the conversation, oldest first.
    names : list of str or None, optional
        Names to remove from everything sent, such as a GitHub username.

    Returns
    -------
    CandidateAnswer
        The answer, with the quotes it cites.

    Raises
    ------
    LLMError
        If the model gives no usable answer.
    """
    prompt, evidence = render_ask_prompt(profile, question, history or [], names)
    system = resources.files(__package__).joinpath("prompts/ask_candidate.md")
    answer = llm.parse(
        system=system.read_text(encoding="utf-8"),
        prompt=prompt,
        output_type=ModelAnswer,
    )
    return check_answer(profile, question, answer, evidence, llm.model, names)


def render_ask_prompt(
    profile: Profile,
    question: str,
    history: list[Turn],
    names: list[str] | None = None,
) -> tuple[str, dict[str, UUID]]:
    """Render the candidate's material, the earlier turns and the question.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    question : str
        The question.
    history : list of Turn
        Earlier turns, oldest first.
    names : list of str or None, optional
        Names to remove from every text from the profile.

    Returns
    -------
    str
        The prompt.
    dict of str to UUID
        Evidence id in the prompt, such as "E3", to `Evidence.id`.
    """
    kinds = {s.id: s.kind for s in profile.sources}
    labels = {e.id: f"E{i}" for i, e in enumerate(profile.evidence, 1)}

    def text(value: str) -> str:
        return escape(" ".join(redact(value, names).split()))

    def cited(ids: list[UUID]) -> str:
        return " ".join(labels[i] for i in ids if i in labels)

    lines = ["<candidate>", f"<headline>{text(profile.headline)}</headline>", "<roles>"]
    for x in profile.experiences:
        start = format_partial_date(x.start, x.start_precision) or "?"
        end = format_partial_date(x.end, x.end_precision) or "present"
        lines.append(
            f"<role from={quoteattr(start)} to={quoteattr(end)} "
            f"evidence={quoteattr(cited(x.evidence_ids))}>"
            f"{text(x.title)}, {text(x.organisation)}. {text(x.summary)}"
            f"{' Skills: ' + text(', '.join(x.skills)) + '.' if x.skills else ''}"
            "</role>"
        )
    lines += ["</roles>", "<skills>"]
    for s in profile.skills:
        attributes = f"name={quoteattr(s.name)}"
        if s.self_level:
            attributes += f' own_level="{int(s.self_level)}"'
        attributes += f" evidence={quoteattr(cited(s.evidence_ids))}"
        lines.append(f"<skill {attributes}/>")
    lines += ["</skills>", "<evidence>"]
    for e in profile.evidence:
        lines.append(
            f"<quote id={quoteattr(labels[e.id])} "
            f"source={quoteattr(_source(kinds.get(e.source_id)))}>"
            f"{text(e.quote)}</quote>"
        )
    lines += ["</evidence>", "</candidate>", ""]
    if history:
        lines.append("<earlier_questions>")
        for turn in history:
            lines.append(
                f"<turn><question>{escape(turn.question)}</question>"
                f"<answer>{escape(turn.answer)}</answer></turn>"
            )
        lines += ["</earlier_questions>", ""]
    lines.append(f"<question>{escape(question)}</question>")
    return "\n".join(lines), {v: k for k, v in labels.items()}


def check_answer(
    profile: Profile,
    question: str,
    answer: ModelAnswer,
    evidence: dict[str, UUID],
    model: str,
    names: list[str] | None = None,
) -> CandidateAnswer:
    """Check the model's answer and attach the quotes it cites.

    Parameters
    ----------
    profile : Profile
        The candidate whose material was sent.
    question : str
        The question.
    answer : ModelAnswer
        The model's answer.
    evidence : dict of str to UUID
        Evidence ids from the prompt, as returned by `render_ask_prompt`.
    model : str
        The model that answered.
    names : list of str or None, optional
        Names to remove from the quotes shown.

    Returns
    -------
    CandidateAnswer
        Cited ids that aren't the candidate's are dropped; an answer the model
        calls answered but that cites none of the candidate's quotes is marked not
        answered. Each is listed in `problems`.
    """
    problems = []
    unknown = [e for e in answer.evidence if e not in evidence]
    if unknown:
        problems.append(f"cited {unknown}, which aren't the candidate's; dropped")
    ids = list(dict.fromkeys(evidence[e] for e in answer.evidence if e in evidence))
    answered = answer.answered
    if answered and not ids:
        problems.append("answered without citing the candidate's quotes")
        answered = False
    kinds = {s.id: s.kind for s in profile.sources}
    quotes = {e.id: e for e in profile.evidence}
    return CandidateAnswer(
        question=question,
        answer=answer.answer.strip(),
        answered=answered,
        evidence=[
            CitedQuote(
                id=i,
                source=_source(kinds.get(quotes[i].source_id)),
                quote=redact(quotes[i].quote, names),
            )
            for i in ids
        ],
        model=model,
        problems=problems,
    )


def demo_questions(pool_name: str | None) -> dict[str, Path]:
    """List the demo questions with a stand-in answer for a pool candidate.

    Parameters
    ----------
    pool_name : str or None
        The candidate's folder in the synthetic pool (their `pool` setting), or
        None for anyone else, who has none.

    Returns
    -------
    dict of str to Path
        Each question's text to its recording, in the order of
        `tests/fixtures/pool/questions.yaml`; only those recorded for this
        candidate.
    """
    if not pool_name or not DEMO_QUESTIONS.is_file():
        return {}
    spec = yaml.safe_load(DEMO_QUESTIONS.read_text(encoding="utf-8")) or {}
    found = {}
    for q in spec.get("questions", []):
        path = POOL / pool_name / f"ask_{q['id']}.json"
        if path.is_file():
            found[q["text"]] = path
    return found


def demo_recording(pool_name: str | None, question: str) -> Path | None:
    """Find the stand-in answer to a demo question, matched ignoring case and spaces.

    Parameters
    ----------
    pool_name : str or None
        The candidate's folder in the synthetic pool, or None.
    question : str
        The question asked.

    Returns
    -------
    Path or None
        The recording to replay, or None if the question isn't a recorded one.
    """
    wanted = _normal(question)
    for text, path in demo_questions(pool_name).items():
        if _normal(text) == wanted:
            return path
    return None


def _normal(text: str) -> str:
    return " ".join(text.casefold().split()).rstrip("?").strip()


def _source(kind: SourceKind | None) -> str:
    if kind is None:
        return "unknown"
    return "candidate statement" if kind == SourceKind.INTERVIEW else kind.value
