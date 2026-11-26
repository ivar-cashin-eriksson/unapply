"""Evaluate rankings against a reference ranking, on a pool of synthetic candidates.

- `metrics`: top-k overlap and Kendall's tau, and reading a reference ranking.
- `pool`: a job's synthetic candidate pool with its intended ranking, and ranking
  it with the baseline or LLM scorer (`unapply evaluate`).
"""

from unapply.evaluation.metrics import (
    ReferenceEntry,
    kendall_tau,
    load_reference,
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
    "DEFAULT_POOL",
    "Evaluation",
    "Pool",
    "PoolCandidate",
    "ReferenceEntry",
    "evaluate_pool",
    "kendall_tau",
    "load_pool",
    "load_reference",
    "top_k_overlap",
]
