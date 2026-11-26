"""Job routes: the ad, rubric extraction and the recruiter's edits.

These are the employer's routes. The rubric is never shown to candidates.
"""

from __future__ import annotations

import yaml
from fastapi import APIRouter, HTTPException, status

from unapply.api.candidates import demos, free_name
from unapply.api.deps import AllowAPI, Context, Ctx
from unapply.api.models import JobAd, JobSummary, NewJob, RubricExtraction, RubricForm
from unapply.app import demo
from unapply.jobs.extract import extract_job
from unapply.jobs.sheet import apply_rubric_sheet
from unapply.schemas import Job, Rubric

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_job(body: NewJob, ctx: Ctx) -> JobSummary:
    """Create a job with its ad, before the rubric is extracted."""
    try:
        ctx.repo.create_job(
            body.name, ad=body.ad, company=body.company, title=body.title
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return summary(ctx, body.name)


@router.get("")
def list_jobs(ctx: Ctx) -> list[str]:
    """List the jobs' names."""
    return ctx.repo.job_names()


@router.get("/{name}")
def get_job(name: str, ctx: Ctx) -> JobSummary:
    """Show where a job is: its ad and rubric version."""
    return summary(ctx, name)


@router.put("/{name}/ad")
def set_ad(name: str, body: JobAd, ctx: Ctx) -> JobSummary:
    """Set the job ad to extract a rubric from. The current rubric stays until then."""
    settings = ctx.repo.job_settings(name)
    if settings.get("demo"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The demo's ad is fixed, so the recorded answer fits it.",
        )
    ctx.repo.save_job_settings(name, {**settings, **body.model_dump()})
    return summary(ctx, name)


@router.post("/{name}/extract")
def extract(name: str, ctx: Ctx, allow_api: AllowAPI = False) -> RubricExtraction:
    """Extract a draft rubric from the ad (a model call).

    Replaces the job and its rubric, unless candidates were matched against it.
    Every criterion quotes the ad; criteria whose quote isn't in it are dropped.
    """
    settings = ctx.repo.job_settings(name)
    ad = settings.get("ad") or ""
    if not ad.strip():
        raise HTTPException(status.HTTP_409_CONFLICT, "Set the job ad first.")
    llm = ctx.model(settings, "rubric", allow_api)
    result = extract_job(
        ad, llm, company=settings.get("company"), title=settings.get("title")
    )
    ctx.repo.save_job(name, result.job, "extracted")
    return RubricExtraction(job=result.job, dropped=result.dropped)


@router.get("/{name}/rubric")
def get_rubric(name: str, ctx: Ctx) -> Rubric:
    """Read the current rubric: hard filters and criteria, each quoting the ad."""
    return _need_job(ctx, name).rubric


@router.get("/{name}/rubric/{version}")
def get_rubric_version(name: str, version: int, ctx: Ctx) -> Rubric:
    """Read an earlier version of the rubric."""
    rubric = ctx.repo.rubric(_need_job(ctx, name).id, version)
    if rubric is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No rubric version {version}.")
    return rubric


@router.put("/{name}/rubric")
def save_rubric(name: str, body: RubricForm, ctx: Ctx) -> Rubric:
    """Save the recruiter's edit of the rubric, and approve it if asked.

    Criteria left out of the form, or with `keep` false, are removed; criteria
    without an id are added. Any change raises the version; a version that
    candidates were matched against never changes.
    """
    job = _need_job(ctx, name)
    updated = apply_rubric_sheet(job, rubric_sheet(job, body))
    ctx.repo.save_job(name, updated, "rubric")
    return updated.rubric


@demos.post("/job", status_code=status.HTTP_201_CREATED, tags=["demos"])
def create_demo_job(ctx: Ctx) -> JobSummary:
    """Create a Fjord Grocery demo job, which replays a recorded rubric for free.

    Named "fjord-grocery-demo", or with a number if taken. Its ad is fixed, so the
    recording fits it.
    """
    if not demo.available():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo isn't installed.")
    name = free_name(ctx.repo.job_names(), "fjord-grocery-demo")
    ad = (demo.JOB_FIXTURE / "ad.md").read_text(encoding="utf-8")
    ctx.repo.create_job(name, demo=True, ad=ad, company=None, title=None)
    return summary(ctx, name)


def summary(ctx: Context, name: str) -> JobSummary:
    """Describe where a job is.

    Parameters
    ----------
    ctx : Context
        The app's context.
    name : str
        The job.

    Returns
    -------
    JobSummary
        The ad, rubric version, approval and history.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    settings = ctx.repo.job_settings(name)
    job = ctx.repo.job(name)
    ad = JobAd(
        ad=settings.get("ad") or (job.ad_text if job else ""),
        company=settings.get("company") or (job.company if job else None),
        title=settings.get("title") or (job.title if job else None),
    )
    return JobSummary(
        name=name,
        demo=bool(settings.get("demo")),
        ad=ad,
        has_rubric=job is not None,
        rubric_version=job.rubric.version if job else None,
        approved=bool(job and job.rubric.approved_at),
        history=ctx.repo.job_history(name),
    )


def rubric_sheet(job: Job, form: RubricForm) -> str:
    """Turn a rubric form into a rubric sheet, so the sheet's checks apply.

    Parameters
    ----------
    job : Job
        The job edited.
    form : RubricForm
        The recruiter's edit.

    Returns
    -------
    str
        A sheet for `unapply.jobs.sheet.apply_rubric_sheet`.
    """
    sheet = {"job": str(job.id), **form.model_dump(mode="json")}
    return yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False)


def _need_job(ctx: Context, name: str) -> Job:
    job = ctx.repo.job(name)
    if job is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Extract a rubric from the job ad first."
        )
    return job
