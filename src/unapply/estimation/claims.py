"""Claim support: how well the candidate's own levels agree with the evidence.

Deterministic, with no model call, so the same profile always gets the same result
and the candidate can see exactly why. `claim_support` sorts the candidate's rated
skills into findings, which are shown as counts. `penalty_score` combines findings
into one number; how findings should combine is still open, so it isn't used by
default.
"""

from __future__ import annotations

from unapply.schemas import ClaimSupport, Profile, Skill, SourceKind

# A gap of one level is normal disagreement; two or more is worth flagging.
FLAG_GAP = 2
# Gaps only count as over- or underclaims when the estimate is reasonably sure.
MIN_CONFIDENCE = 0.5
# In penalty_score: an unsupported claim rated 3 or more, relative to a sure
# five-against-one overclaim.
UNSUPPORTED_PENALTY = 0.5


def claim_support(profile: Profile) -> ClaimSupport:
    """Sort the candidate's rated skills into findings.

    - **overclaim:** own level `FLAG_GAP` or more above an estimate with confidence
      of at least `MIN_CONFIDENCE`.
    - **unverified:** the same gap, but the evidence says little either way. The
      candidate is asked about these.
    - **underclaim:** own level `FLAG_GAP` or more below a sure estimate.
    - **unsupported:** backed only by the candidate's own statements.

    Anything else, including a one-level gap, is no finding.

    Parameters
    ----------
    profile : Profile
        A profile with estimates (see `estimate_skills`).

    Returns
    -------
    ClaimSupport
        The findings and the number of rated skills; `score` is left unset.
    """
    source_of = _source_of(profile)
    rated = [s for s in profile.skills if s.self_level is not None]
    over, under, unverified, unsupported = [], [], [], []
    for s in rated:
        if _statement_only(s, source_of):
            unsupported.append(s.name)
        elif s.estimate is not None:
            gap = int(s.self_level) - int(s.estimate.level)
            sure = s.estimate.confidence >= MIN_CONFIDENCE
            if gap >= FLAG_GAP:
                (over if sure else unverified).append(s.name)
            elif gap <= -FLAG_GAP and sure:
                under.append(s.name)
    return ClaimSupport(
        rated=len(rated),
        overclaims=over,
        underclaims=under,
        unverified=unverified,
        unsupported_claims=unsupported,
    )


def penalty_score(profile: Profile, support: ClaimSupport) -> float:
    """Combine findings into one score from 0 to 1. Experimental; not used by default.

    The score is 1 minus the mean penalty over the rated skills. An overclaim costs
    the gap beyond one level, as a share of the largest possible, times the
    estimate's confidence, so a sure 5-against-1 costs 1. An unsupported claim
    rated 3 or more costs `UNSUPPORTED_PENALTY`. Nothing else costs anything.

    Parameters
    ----------
    profile : Profile
        The profile `support` was computed from.
    support : ClaimSupport
        Its findings, from `claim_support`.

    Returns
    -------
    float
        From 0 to 1; 1 when nothing is rated.
    """
    if support.rated == 0:
        return 1.0
    penalties = 0.0
    for name in support.overclaims:
        s = profile.skill(name)
        penalties += (
            (int(s.self_level) - int(s.estimate.level) - 1)
            / 3
            * (s.estimate.confidence)
        )
    for name in support.unsupported_claims:
        if profile.skill(name).self_level >= 3:
            penalties += UNSUPPORTED_PENALTY
    return round(min(max(1 - penalties / support.rated, 0.0), 1.0), 3)


def summary(support: ClaimSupport) -> str:
    """Describe the findings as counts, such as '3 overclaims, 4 unverified, ...'.

    Parameters
    ----------
    support : ClaimSupport
        Findings from `claim_support`.

    Returns
    -------
    str
        One line, for people.
    """
    counts = [
        (len(support.overclaims), "overclaim", "overclaims"),
        (len(support.unverified), "unverified", "unverified"),
        (len(support.underclaims), "underclaim", "underclaims"),
        (
            len(support.unsupported_claims),
            "only your own statement",
            "only your own statement",
        ),
    ]
    parts = [f"{n} {one if n == 1 else many}" for n, one, many in counts]
    return f"{', '.join(parts)}, of {support.rated} rated skills"


def _source_of(profile: Profile) -> dict:
    kinds = {s.id: s.kind for s in profile.sources}
    return {e.id: kinds[e.source_id] for e in profile.evidence}


def _statement_only(skill: Skill, source_of: dict) -> bool:
    return bool(skill.evidence_ids) and all(
        source_of[i] == SourceKind.INTERVIEW for i in skill.evidence_ids
    )
