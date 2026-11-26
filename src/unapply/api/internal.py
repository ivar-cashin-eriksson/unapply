"""Internal routes: a candidate's assessment. Never for the candidate's frontend.

The assessment (estimated levels, confidence, claim support) is hidden from
candidates so they can't tune their profile to it. These routes exist only in an
app created with `internal=True` (`unapply api --internal`), for developers and
for answering a candidate's data access request.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from unapply.api.candidates import assess
from unapply.api.deps import AllowAPI, Ctx
from unapply.api.models import Assessment
from unapply.estimation.claims import claim_support, summary
from unapply.estimation.skills import skills_without_estimate
from unapply.schemas import Profile

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/candidates/{name}/assessment")
def get_assessment(name: str, ctx: Ctx) -> Assessment:
    """Read a candidate's full profile with estimates and claim support."""
    return assessment(_need_profile(ctx.repo.profile(name)))


@router.post("/candidates/{name}/estimate")
def estimate(
    name: str,
    ctx: Ctx,
    allow_api: AllowAPI = False,
    all_skills: bool = Query(
        False,
        alias="all",
        description="Re-estimate every skill, not only those without an estimate.",
    ),
) -> Assessment:
    """Estimate skills from their evidence and recompute claim support.

    Calls the model only if some skill is to be estimated: by default those without
    an estimate, with `all=true` every skill.
    """
    profile = _need_profile(ctx.repo.profile(name))
    names = None if all_skills else skills_without_estimate(profile)
    if names is None or names:
        llm = ctx.model(ctx.repo.settings(name), "estimate", allow_api, profile)
        estimated = assess(profile, llm, names)
    else:
        estimated = profile.model_copy(update={"claim_support": claim_support(profile)})
    ctx.repo.save_profile(name, estimated, "assessed")
    return assessment(estimated)


def assessment(profile: Profile) -> Assessment:
    """Describe a profile's assessment.

    Parameters
    ----------
    profile : Profile
        The full profile.

    Returns
    -------
    Assessment
        The profile, claim support as counts, and the skills not estimated yet.
    """
    support = profile.claim_support
    return Assessment(
        profile=profile,
        summary=summary(support) if support else None,
        not_estimated=sorted(skills_without_estimate(profile)),
    )


def _need_profile(profile: Profile | None) -> Profile:
    if profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No profile yet.")
    return profile
