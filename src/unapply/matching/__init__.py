"""Match candidates to jobs: hard filters, scores per criterion, and a ranking.

- `filters`: location, work mode, work permit and minimum years, in plain code.
- `baseline`: a deterministic scorer from skill levels, the taxonomy and evidence.
- `llm_scorer`: a model scores each criterion from the anonymised profile.
- `scoring`: `match_candidate`, `rank` and the `Scorer` protocol.
- `audit`: the append-only log of matches and rankings, and reproducing a ranking.
"""

from unapply.matching.baseline import BASELINE_MODEL, BaselineScorer
from unapply.matching.filters import FilterCheck, FilterReport, check_hard_filters
from unapply.matching.llm_scorer import LLMScorer
from unapply.matching.scoring import (
    MatchResult,
    Ranked,
    Scorer,
    ScoringResult,
    latest,
    match_candidate,
    rank,
)

__all__ = [
    "BASELINE_MODEL",
    "BaselineScorer",
    "FilterCheck",
    "FilterReport",
    "LLMScorer",
    "MatchResult",
    "Ranked",
    "Scorer",
    "ScoringResult",
    "check_hard_filters",
    "latest",
    "match_candidate",
    "rank",
]
