"""Candidate routes: material, extraction, review, questions, answers and profile.

Everything here is what the candidate sees, so nothing returns the assessment: the
profile comes without estimates or claim support, and questions say why they are
asked in neutral words. The assessment runs in the background when questions are
prepared and answers are given; `unapply.api.internal` shows it.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, status

from unapply.api.deps import AllowAPI, Context, Ctx, may_call
from unapply.api.models import (
    AnsweredQuestion,
    AnswerResult,
    Answers,
    CandidateProfile,
    CandidateSettings,
    CandidateSummary,
    ExperienceEdit,
    Extraction,
    MaterialFile,
    NewCandidate,
    Question,
    Questions,
    ReviewForm,
    SkillEdit,
)
from unapply.app import demo, forms
from unapply.estimation.claims import claim_support
from unapply.estimation.skills import estimate_skills, skills_without_estimate
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.ingest.github import cached_fetcher, fetch_github
from unapply.interview.questions import (
    MAX_QUESTIONS,
    WHY,
    Reason,
    select_topics,
    write_questions,
)
from unapply.interview.sheet import apply_interview_sheet
from unapply.llm import LLMError, StructuredLLM
from unapply.review import apply_review_sheet, export_review_sheet
from unapply.schemas import Profile
from unapply.workspace import data_dir

log = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"])
demos = APIRouter(prefix="/demos", tags=["demos"])

# What can be uploaded: what `unapply.ingest.documents.load_path` reads, and zipped
# LinkedIn exports.
UPLOAD_SUFFIXES = {".pdf", ".md", ".txt", ".tex", ".yaml", ".yml", ".json", ".zip"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("", status_code=status.HTTP_201_CREATED)
def create_candidate(body: NewCandidate, ctx: Ctx) -> CandidateSummary:
    """Create a candidate without material or a profile."""
    try:
        ctx.repo.create_candidate(body.name, github=_blank(body.github))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return summary(ctx, body.name)


@router.get("")
def list_candidates(ctx: Ctx) -> list[str]:
    """List the candidates' names.

    The synthetic pool's candidates, stored for the shortlist demo, aren't listed:
    their profiles are finished fixtures, not journeys to continue.
    """
    return [
        n for n in ctx.repo.candidate_names() if not ctx.repo.settings(n).get("pool")
    ]


@router.get("/{name}")
def get_candidate(name: str, ctx: Ctx) -> CandidateSummary:
    """Show where a candidate is: material, profile, approval and questions."""
    return summary(ctx, name)


@router.patch("/{name}")
def update_candidate(name: str, body: CandidateSettings, ctx: Ctx) -> CandidateSummary:
    """Change a candidate's settings, such as their GitHub username."""
    settings = ctx.repo.settings(name)
    _not_demo(settings, "The demo's material is fixed, so the recordings fit it.")
    ctx.repo.save_settings(name, {**settings, "github": _blank(body.github)})
    return summary(ctx, name)


@router.get("/{name}/material")
def list_material(name: str, ctx: Ctx) -> list[MaterialFile]:
    """List the candidate's uploaded files."""
    ctx.repo.settings(name)  # 404 for an unknown candidate
    return _files(ctx.material(name))


@router.post("/{name}/material", status_code=status.HTTP_201_CREATED)
def upload_material(name: str, files: list[UploadFile], ctx: Ctx) -> list[MaterialFile]:
    """Upload files: a CV, other documents, a zipped LinkedIn data export.

    A file with the same name as an uploaded one replaces it. From a LinkedIn
    export only profile sections are read, never messages or connections.
    """
    settings = ctx.repo.settings(name)
    _not_demo(settings, "The demo's material is fixed, so the recordings fit it.")
    checked = []
    for f in files:
        filename = Path(f.filename or "").name
        if not filename or filename.startswith("."):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no file name")
        if Path(filename).suffix.lower() not in UPLOAD_SUFFIXES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{filename}: use one of {', '.join(sorted(UPLOAD_SUFFIXES))}",
            )
        content = f.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"{filename} is over {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
            )
        checked.append((filename, content))
    # Written only once every file is checked, so a refused upload adds nothing.
    folder = ctx.material(name)
    folder.mkdir(parents=True, exist_ok=True)
    for filename, content in checked:
        (folder / filename).write_bytes(content)
    return _files(folder)


@router.delete("/{name}/material/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(name: str, filename: str, ctx: Ctx) -> None:
    """Remove an uploaded file. The profile keeps what was extracted from it."""
    settings = ctx.repo.settings(name)
    _not_demo(settings, "The demo's material is fixed, so the recordings fit it.")
    path = ctx.material(name) / filename
    if Path(filename).name != filename or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no file {filename!r}")
    path.unlink()


@router.post("/{name}/extract")
def extract(name: str, ctx: Ctx, allow_api: AllowAPI = False) -> Extraction:
    """Extract a draft profile from the material (a model call).

    Replaces the current profile, including the review and answers; earlier
    versions stay in the history. Every claim is backed by a quote found in the
    material.
    """
    settings = ctx.repo.settings(name)
    llm = ctx.model(settings, "extract", allow_api)  # Refuses before any work.
    folder = ctx.material(name)
    # Each upload is the candidate's choice, so each is read, even a README; they
    # leave a file out by removing it.
    files = sorted(folder.iterdir()) if folder.exists() else []
    documents = [d for f in files if f.is_file() for d in load_path(f)]
    if github := settings.get("github"):
        fetch = cached_fetcher(data_dir() / ".cache" / "github")
        documents.append(fetch_github(github, fetch=fetch))
    if not documents:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add some material first.")
    result = extract_profile(documents, llm)
    ctx.repo.save_profile(name, result.profile, "extracted")
    ctx.repo.save_pending_questions(name, None)
    return Extraction(
        profile=CandidateProfile.of(result.profile),
        rejected_quotes=len(result.rejected_quotes),
        unsupported=result.unsupported,
    )


@router.get("/{name}/review")
def get_review(name: str, ctx: Ctx) -> ReviewForm:
    """Read the review form: the profile to check, rate and approve.

    Each skill and experience comes with the quotes behind it.
    """
    return review_form(_need_profile(ctx, name))


@router.put("/{name}/review")
def save_review(name: str, body: ReviewForm, ctx: Ctx) -> CandidateProfile:
    """Save the candidate's review: levels, corrections, removals, additions.

    Every skill and experience of the profile must be in the form; set `keep`
    to false to remove one. Skill names are mapped to their canonical names, so
    synonyms merge. Employers only see approved profiles.
    """
    profile = _need_profile(ctx, name)
    reviewed = apply_review_sheet(profile, review_sheet(profile, body))
    # Levels may have changed, so findings are recomputed (no model call).
    if any(s.estimate for s in reviewed.skills):
        reviewed = reviewed.model_copy(
            update={"claim_support": claim_support(reviewed)}
        )
    ctx.repo.save_profile(name, reviewed, "reviewed")
    return CandidateProfile.of(reviewed)


@router.get("/{name}/questions")
def get_questions(name: str, ctx: Ctx) -> Questions:
    """List the questions waiting for answers and those answered before."""
    return questions(ctx, name)


@router.post("/{name}/questions")
def prepare_questions(name: str, ctx: Ctx, allow_api: AllowAPI = False) -> Questions:
    """Prepare questions about skills the documents say little about (model calls).

    Needs an approved profile. Up to 8 questions, never about a skill asked
    about before; none if the documents cover what the candidate rated.
    """
    profile = _need_profile(ctx, name)
    if profile.approved_by_candidate_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approve your profile first.")
    if ctx.repo.pending_questions(name):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Answer or discard the waiting questions first.",
        )
    settings = ctx.repo.settings(name)
    # Both models are picked first, so a refused request changes nothing.
    estimator = ctx.model(settings, "estimate", allow_api, profile)
    writer = ctx.model(settings, "questions", allow_api)
    missing = skills_without_estimate(profile)
    if missing or profile.claim_support is None:
        profile = assess(profile, estimator, missing)
        ctx.repo.save_profile(name, profile, "assessed")
    topics = select_topics(profile, MAX_QUESTIONS)
    if topics:
        written = write_questions(profile, topics, writer)
        ctx.repo.save_pending_questions(
            name,
            [
                {"skill": q.skill, "reason": q.reason.value, "text": q.text}
                for q in written
            ],
        )
    return questions(ctx, name)


@router.delete("/{name}/questions", status_code=status.HTTP_204_NO_CONTENT)
def discard_questions(name: str, ctx: Ctx) -> None:
    """Discard the questions waiting for answers. Answered ones are kept."""
    ctx.repo.save_pending_questions(name, None)


@router.post("/{name}/answers")
def answer_questions(
    name: str, body: Answers, ctx: Ctx, allow_api: AllowAPI = False
) -> AnswerResult:
    """Answer the waiting questions.

    Answers become the candidate's own statements in the profile, each next to its
    question. Questions left unanswered are discarded, unless nothing was
    answered: then nothing changes. The assessment of the answered skills is updated
    in the background when model calls are allowed (always in a demo); otherwise
    the answers are saved and it is updated the next time questions are prepared.
    """
    profile = _need_profile(ctx, name)
    waiting = ctx.repo.pending_questions(name)
    if not waiting:
        raise HTTPException(status.HTTP_409_CONFLICT, "No questions are waiting.")
    unknown = sorted(set(body.answers) - {q["skill"] for q in waiting})
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"no waiting question about: {', '.join(unknown)}",
        )
    updated, n = apply_interview_sheet(
        profile, forms.interview_sheet(profile, waiting, body.answers)
    )
    if not n:
        return AnswerResult(answered=0)
    ctx.repo.record_answers(name, body.answers)
    ctx.repo.save_pending_questions(name, None)
    ctx.repo.save_profile(name, updated, "interviewed")
    settings = ctx.repo.settings(name)
    if may_call(settings, allow_api):
        try:
            estimator = ctx.model(settings, "estimate", allow_api, updated)
            assessed = assess(updated, estimator, skills_without_estimate(updated))
            ctx.repo.save_profile(name, assessed, "assessed")
        except LLMError:
            # The answers are saved; the assessment is updated next time.
            log.warning("assessment after answers failed for %s", name, exc_info=True)
    return AnswerResult(answered=n)


@router.get("/{name}/profile")
def get_profile(name: str, ctx: Ctx) -> CandidateProfile:
    """Show the profile as the candidate sees it, without the assessment.

    This is also what the candidate downloads. The assessment is part of their
    data too and is provided on a data access request.
    """
    profile = ctx.repo.profile(name)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet.")
    return CandidateProfile.of(profile)


@router.get("/{name}/demo/review")
def demo_review(name: str, ctx: Ctx) -> ReviewForm:
    """John Doe's review, filled in and approved. Only for demo candidates."""
    _need_demo(ctx, name)
    profile = _need_profile(ctx, name)
    return _form(profile, yaml.safe_load(demo.john_review_sheet(profile)))


@router.get("/{name}/demo/answers")
def demo_answers(name: str, ctx: Ctx) -> Answers:
    """John Doe's answers to the waiting questions. Only for demo candidates."""
    _need_demo(ctx, name)
    john = demo.john_answers()
    waiting = ctx.repo.pending_questions(name) or []
    return Answers(
        answers={q["skill"]: john[q["skill"]] for q in waiting if q["skill"] in john}
    )


@demos.post("/candidate", status_code=status.HTTP_201_CREATED)
def create_demo_candidate(ctx: Ctx) -> CandidateSummary:
    """Create a John Doe demo candidate, which replays recorded answers for free.

    Named "john-doe-demo", or "john-doe-demo-2" and so on if taken. Its material is
    John's and can't change, so the recordings fit it.
    """
    if not demo.available():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo isn't installed.")
    name = free_name(ctx.repo.candidate_names(), "john-doe-demo")
    ctx.repo.create_candidate(name, demo=True)
    folder = ctx.material(name)
    folder.mkdir(parents=True, exist_ok=True)
    for f in (demo.FIXTURE / "material").iterdir():
        shutil.copy(f, folder / f.name)
    return summary(ctx, name)


def summary(ctx: Context, name: str) -> CandidateSummary:
    """Describe where a candidate is.

    Parameters
    ----------
    ctx : Context
        The app's context.
    name : str
        The candidate.

    Returns
    -------
    CandidateSummary
        Material, profile, approval, questions and history.

    Raises
    ------
    NotFound
        If there is no such candidate.
    """
    settings = ctx.repo.settings(name)
    profile = ctx.repo.profile(name)
    return CandidateSummary(
        name=name,
        demo=bool(settings.get("demo")),
        github=settings.get("github"),
        material=_files(ctx.material(name)),
        has_profile=profile is not None,
        approved=bool(profile and profile.approved_by_candidate_at),
        questions_waiting=len(ctx.repo.pending_questions(name) or []),
        history=ctx.repo.history(name),
    )


def questions(ctx: Context, name: str) -> Questions:
    """List a candidate's waiting and answered questions, in neutral words.

    Parameters
    ----------
    ctx : Context
        The app's context.
    name : str
        The candidate.

    Returns
    -------
    Questions
        Waiting questions say why they are asked as the candidate is told
        (`unapply.interview.questions.WHY`), never the finding behind it.
    """
    return Questions(
        waiting=[
            Question(skill=q["skill"], why=WHY[Reason(q["reason"])], text=q["text"])
            for q in ctx.repo.pending_questions(name) or []
        ],
        answered=[
            AnsweredQuestion(skill=q["skill"], text=q["text"], answer=q["answer"])
            for q in ctx.repo.answered_questions(name)
        ],
    )


def assess(profile: Profile, llm: StructuredLLM, names: set[str] | None) -> Profile:
    """Estimate skills and recompute claim support.

    Parameters
    ----------
    profile : Profile
        The profile.
    llm : StructuredLLM
        The model to estimate with.
    names : set of str or None
        Skills to estimate; None for every skill.

    Returns
    -------
    Profile
        The profile with the new estimates and claim support.
    """
    result = estimate_skills(profile, llm, names)
    return result.profile.model_copy(
        update={"claim_support": claim_support(result.profile)}
    )


def review_form(profile: Profile) -> ReviewForm:
    """Build the review form for a profile.

    Parameters
    ----------
    profile : Profile
        The profile to review.

    Returns
    -------
    ReviewForm
        Its headline, preferences, experiences and skills with their quotes, and
        whether it is approved.
    """
    form = _form(profile, yaml.safe_load(export_review_sheet(profile)))
    return form.model_copy(
        update={"approve": profile.approved_by_candidate_at is not None}
    )


def review_sheet(profile: Profile, form: ReviewForm) -> str:
    """Turn a review form into a review sheet, so the sheet's checks apply.

    Parameters
    ----------
    profile : Profile
        The profile reviewed.
    form : ReviewForm
        The candidate's review.

    Returns
    -------
    str
        A sheet for `unapply.review.apply_review_sheet`.
    """
    sheet = {
        "profile": str(profile.id),
        **form.model_dump(
            mode="json",
            exclude={
                "experiences": {"__all__": {"evidence"}},
                "skills": {"__all__": {"evidence"}},
            },
        ),
    }
    sheet["add_skills"] = sheet["add_skills"] or None
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False)


def free_name(taken: list[str], name: str) -> str:
    """Return `name`, or `name-2`, `name-3` and so on, whichever isn't taken.

    Parameters
    ----------
    taken : list of str
        Names in use.
    name : str
        The name wanted.

    Returns
    -------
    str
        A free name.
    """
    free, n = name, 2
    while free in taken:
        free, n = f"{name}-{n}", n + 1
    return free


def _form(profile: Profile, sheet: dict) -> ReviewForm:
    """Read a parsed review sheet into a form, with each item's quotes."""
    experiences = {str(x.id): x for x in profile.experiences}
    skills = {s.name: s for s in profile.skills}
    return ReviewForm(
        approve=bool(sheet.get("approve")),
        headline=sheet.get("headline") or "",
        preferences=sheet["preferences"],
        experiences=[
            ExperienceEdit(
                id=x["id"],
                keep=x["keep"],
                title=x["title"] or "",
                organisation=x["organisation"] or "",
                start=_date(x["start"]),
                end=_date(x["end"]),
                summary=x["summary"] or "",
                evidence=forms.evidence_lines(
                    profile, experiences[x["id"]].evidence_ids
                ),
            )
            for x in sheet.get("experiences") or []
        ],
        skills=[
            SkillEdit(
                name=s["name"],
                category=s["category"] or None,
                level=s["level"] or None,
                keep=s["keep"],
                evidence=forms.evidence_lines(profile, skills[s["name"]].evidence_ids),
            )
            for s in sheet.get("skills") or []
        ],
        add_skills=sheet.get("add_skills") or [],
    )


def _date(value: int | str | None) -> str | None:
    """Read a sheet date, which YAML reads as a number (2019) or text ("2019-08")."""
    return None if value in (None, "") else str(value)


def _files(folder: Path) -> list[MaterialFile]:
    if not folder.exists():
        return []
    return [
        MaterialFile(name=f.name, size=f.stat().st_size)
        for f in sorted(folder.iterdir())
        if f.is_file()
    ]


def _need_profile(ctx: Context, name: str) -> Profile:
    profile = ctx.repo.profile(name)
    if profile is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Extract a profile from your material first."
        )
    return profile


def _need_demo(ctx: Context, name: str) -> None:
    if not ctx.repo.settings(name).get("demo"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a demo candidate.")


def _not_demo(settings: dict, why: str) -> None:
    if settings.get("demo"):
        raise HTTPException(status.HTTP_409_CONFLICT, why)


def _blank(value: str | None) -> str | None:
    return (value or "").strip() or None
