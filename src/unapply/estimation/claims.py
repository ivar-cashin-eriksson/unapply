"""Claim support: how well the candidate's own levels agree with the evidence.

Deterministic, with no model call, so the same profile always gets the same score and
the candidate can see exactly why.
"""

from __future__ import annotations

from unapply.schemas import ClaimSupport, Profile, Skill, SourceKind

# A gap of one level is normal disagreement; two or more is worth flagging.
FLAG_GAP = 2
# Gaps only count when the estimate is reasonably sure.
MIN_CONFIDENCE = 0.5
# How much an unsupported claim costs, relative to a confident four-level overclaim.
UNSUPPORTED_PENALTY = 0.5


def claim_support(profile: Profile) -> ClaimSupport:
    """Compare the candidate's own levels with the estimates.

    Only skills the candidate rated count. Each falls in one group:

    - **overclaim:** own level `FLAG_GAP` or more above an estimate with confidence of
      at least `MIN_CONFIDENCE`. Penalty: the gap beyond one level, as a share of
      the largest possible, times the confidence; a sure 5-against-1 costs 1.
    - **unverified:** the same gap, but the evidence says little either way. No
      penalty: the candidate is asked about it instead.
    - **underclaim:** own level `FLAG_GAP` or more below a sure estimate. No
      penalty: modesty is not a problem for the reader.
    - **unsupported:** backed only by the candidate's own statements. Penalty
      `UNSUPPORTED_PENALTY` if rated 3 or more.
    - anything else, including a one-level gap: no penalty.

    The score is 1 minus the mean penalty over the rated skills.

    Parameters
    ----------
    profile : Profile
        A profile with estimates (see `estimate_skills`).

    Returns
    -------
    ClaimSupport
        The score from 0 to 1, and the skills behind it. A profile with no rated
        skills scores 1.
    """
    kinds = {s.id: s.kind for s in profile.sources}
    source_of = {e.id: kinds[e.source_id] for e in profile.evidence}
    rated = [s for s in profile.skills if s.self_level is not None]
    penalties: list[float] = []
    over, under, unverified, unsupported = [], [], [], []
    for s in rated:
        if _statement_only(s, source_of):
            unsupported.append(s.name)
            penalties.append(UNSUPPORTED_PENALTY if s.self_level >= 3 else 0.0)
            continue
        if s.estimate is None:
            continue
        gap = int(s.self_level) - int(s.estimate.level)
        sure = s.estimate.confidence >= MIN_CONFIDENCE
        penalty = 0.0
        if gap >= FLAG_GAP and sure:
            over.append(s.name)
            penalty = (gap - 1) / 3 * s.estimate.confidence
        elif gap >= FLAG_GAP:
            unverified.append(s.name)
        elif gap <= -FLAG_GAP and sure:
            under.append(s.name)
        penalties.append(penalty)
    score = 1 - sum(penalties) / len(penalties) if penalties else 1.0
    return ClaimSupport(
        score=round(min(max(score, 0.0), 1.0), 3),
        overclaims=over,
        underclaims=under,
        unverified=unverified,
        unsupported_claims=unsupported,
    )


def _statement_only(skill: Skill, source_of: dict) -> bool:
    return bool(skill.evidence_ids) and all(
        source_of[i] == SourceKind.INTERVIEW for i in skill.evidence_ids
    )
