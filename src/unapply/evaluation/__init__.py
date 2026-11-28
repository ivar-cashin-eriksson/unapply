"""Evaluate rankings against a reference ranking, on a pool of synthetic candidates.

- `metrics`: top-k overlap and Kendall's tau, reading a reference ranking, and the
  agreement between several references (the ceiling, with human shortlists), and
  a blank reference sheet for a person who hires to fill in.
- `pool`: a job's synthetic candidate pool with its intended ranking, and ranking
  it with the baseline or LLM scorer (`unapply evaluate`).
- `stored`: a job's ranking from the audit log, the one its employer saw
  (`unapply evaluate --job`).
"""

from unapply.evaluation.metrics import (
    Agreement,
    ReferenceEntry,
    compare_ranking,
    kendall_tau,
    load_reference,
    mean_comparison,
    rater_agreement,
    reference_sheet,
    top_k_overlap,
)
from unapply.evaluation.pool import (
    DEFAULT_POOL,
    Evaluation,
    Pool,
    PoolCandidate,
    evaluate_pool,
    load_pool,
)
from unapply.evaluation.stored import StoredRanking, stored_ranking

__all__ = [
    "Agreement",
    "DEFAULT_POOL",
    "Evaluation",
    "Pool",
    "PoolCandidate",
    "ReferenceEntry",
    "StoredRanking",
    "compare_ranking",
    "evaluate_pool",
    "kendall_tau",
    "load_pool",
    "load_reference",
    "mean_comparison",
    "rater_agreement",
    "reference_sheet",
    "stored_ranking",
    "top_k_overlap",
]
