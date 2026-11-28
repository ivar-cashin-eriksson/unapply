"""Evaluate rankings against a reference ranking, on a pool of synthetic candidates.

- `metrics`: top-k overlap and Kendall's tau, reading a reference ranking, and the
  agreement between several references (the ceiling, with human shortlists).
- `pool`: a job's synthetic candidate pool with its intended ranking, and ranking
  it with the baseline or LLM scorer (`unapply evaluate`).
"""

from unapply.evaluation.metrics import (
    Agreement,
    ReferenceEntry,
    compare_ranking,
    kendall_tau,
    load_reference,
    mean_comparison,
    rater_agreement,
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

__all__ = [
    "Agreement",
    "DEFAULT_POOL",
    "Evaluation",
    "Pool",
    "PoolCandidate",
    "ReferenceEntry",
    "compare_ranking",
    "evaluate_pool",
    "kendall_tau",
    "load_pool",
    "load_reference",
    "mean_comparison",
    "rater_agreement",
    "top_k_overlap",
]
