"""Compare a ranking with a reference ranking: top-k overlap and Kendall's tau.

The reference is the ranking we trust more: the intended ranking of a synthetic pool
now, human shortlists later. Both metrics only look at candidates that are in both
rankings, so a reference can cover part of a ranking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ReferenceEntry:
    """One candidate's place in a reference ranking.

    Parameters
    ----------
    candidate : str
        The candidate's name, as in the ranking compared with.
    rank : int
        1 for the best. Candidates may share a rank, such as several who are all
        unsuitable.
    reason : str
        Why the candidate is placed there, for a reader checking the reference.
    """

    candidate: str
    rank: int
    reason: str = ""


def load_reference(path: Path) -> list[ReferenceEntry]:
    """Read a reference ranking from a YAML file.

    The file has a `ranking` list (or `intended`, as in a pool's `pool.yaml`) of
    entries with `candidate`, `rank` and an optional `reason`::

        ranking:
          - candidate: astrid-holm
            rank: 1
            reason: Forecasting in production at an online grocer.

    Parameters
    ----------
    path : Path
        The YAML file.

    Returns
    -------
    list of ReferenceEntry
        By rank, best first.

    Raises
    ------
    ValueError
        If the file has no ranking, a rank isn't a positive whole number, or a
        candidate is listed twice.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_reference(data.get("ranking", data.get("intended")), str(path))


def parse_reference(entries: object, where: str = "reference") -> list[ReferenceEntry]:
    """Check and parse the entries of a reference ranking.

    Parameters
    ----------
    entries : object
        The parsed YAML list of entries; see `load_reference`.
    where : str, optional
        Where they come from, for error messages.

    Returns
    -------
    list of ReferenceEntry
        By rank, best first.

    Raises
    ------
    ValueError
        If `entries` is empty or not a list, a rank isn't a positive whole number,
        or a candidate is listed twice.
    """
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{where}: no ranking (a list under `ranking`)")
    parsed: list[ReferenceEntry] = []
    for e in entries:
        if not isinstance(e, dict) or "candidate" not in e or "rank" not in e:
            raise ValueError(f"{where}: each entry needs `candidate` and `rank`: {e!r}")
        rank = e["rank"]
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise ValueError(f"{where}: rank of {e['candidate']!r} must be 1 or more")
        parsed.append(
            ReferenceEntry(str(e["candidate"]), rank, str(e.get("reason") or ""))
        )
    names = [e.candidate for e in parsed]
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        raise ValueError(f"{where}: listed more than once: {', '.join(twice)}")
    return sorted(parsed, key=lambda e: e.rank)


def top_k_overlap(ranking: list[str], reference: list[str], k: int) -> float:
    """Share of the reference's top k that are also in the ranking's top k.

    Only candidates in both lists count, so each top k is taken after dropping
    the others. Ties at the k-th place are broken by list order.

    Parameters
    ----------
    ranking : list of str
        Candidate names, best first.
    reference : list of str
        Candidate names in the reference order, best first.
    k : int
        How many top candidates to compare, 1 or more. Capped at the number of
        candidates in both lists.

    Returns
    -------
    float
        From 0 (no candidate in common) to 1 (the same top k, in any order).

    Raises
    ------
    ValueError
        If `k` is below 1 or the lists have no candidate in common.
    """
    if k < 1:
        raise ValueError("k must be 1 or more")
    common = set(ranking) & set(reference)
    if not common:
        raise ValueError("the ranking and the reference have no candidate in common")
    k = min(k, len(common))
    top = [n for n in ranking if n in common][:k]
    top_reference = [n for n in reference if n in common][:k]
    return len(set(top) & set(top_reference)) / k


def kendall_tau(ranks: dict[str, int], reference: dict[str, int]) -> float | None:
    """Kendall's tau-b between two rankings, which may have ties.

    Counts, over every pair of candidates in both rankings, whether the two put
    them in the same order (concordant) or the opposite one (discordant):
    tau-b = (concordant - discordant) / sqrt((pairs - tied in ranking) x (pairs -
    tied in reference)). Pairs tied in a ranking count as neither, and the
    denominator corrects for them, so shared ranks don't count against a ranking.

    Parameters
    ----------
    ranks : dict of str to int
        Rank by candidate name, 1 for the best.
    reference : dict of str to int
        Reference rank by candidate name.

    Returns
    -------
    float or None
        From -1 (reversed) through 0 (unrelated) to 1 (the same order). None if
        fewer than two candidates are in both, or either ranking ties them all.
    """
    names = sorted(set(ranks) & set(reference))
    concordant = discordant = tied_ranks = tied_reference = pairs = 0
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairs += 1
            x = ranks[a] - ranks[b]
            y = reference[a] - reference[b]
            tied_ranks += x == 0
            tied_reference += y == 0
            if x * y > 0:
                concordant += 1
            elif x * y < 0:
                discordant += 1
    denominator = math.sqrt((pairs - tied_ranks) * (pairs - tied_reference))
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def compare_ranking(
    ranks: dict[str, int],
    order: list[str],
    reference: list[ReferenceEntry],
    ks: tuple[int, ...],
) -> tuple[dict[int, float], float | None]:
    """Compare one ranking with a reference: top-k overlaps and Kendall's tau.

    Parameters
    ----------
    ranks : dict of str to int
        Rank by candidate name, 1 for the best.
    order : list of str
        The same candidates, best first (ties in any order).
    reference : list of ReferenceEntry
        The reference ranking, best first.
    ks : tuple of int
        The top-k overlaps to compute.

    Returns
    -------
    tuple of (dict of int to float, float or None)
        Top-k overlap by k, and Kendall's tau-b (None if it can't be computed).

    Raises
    ------
    ValueError
        If a k is below 1 or the two have no candidate in common.
    """
    reference_order = [e.candidate for e in reference]
    top_k = {k: top_k_overlap(order, reference_order, k) for k in ks}
    tau = kendall_tau(ranks, {e.candidate: e.rank for e in reference})
    return top_k, tau


@dataclass(frozen=True)
class Agreement:
    """How much several reference rankings agree with each other.

    The mean over every pair of references. With human shortlists as references,
    this is the ceiling a scorer is measured against: a ranking that agrees with
    each person about as much as they agree with each other is as good as one of
    them.

    Parameters
    ----------
    pairs : int
        The number of pairs of references compared.
    top_k : dict of int to float
        Mean top-k overlap, by k.
    tau : float or None
        Mean Kendall's tau-b over the pairs where it can be computed; None if it
        can't for any.
    """

    pairs: int
    top_k: dict[int, float]
    tau: float | None


def mean_comparison(
    comparisons: list[tuple[dict[int, float], float | None]],
) -> tuple[dict[int, float], float | None]:
    """Average several comparisons from `compare_ranking`.

    Parameters
    ----------
    comparisons : list of tuple of (dict of int to float, float or None)
        Top-k overlaps by k and tau, each for the same ks.

    Returns
    -------
    tuple of (dict of int to float, float or None)
        Mean top-k overlap by k, and the mean of the taus that aren't None (None
        if all are).

    Raises
    ------
    ValueError
        If `comparisons` is empty.
    """
    if not comparisons:
        raise ValueError("nothing to average")
    ks = comparisons[0][0]
    top_k = {k: sum(c[0][k] for c in comparisons) / len(comparisons) for k in ks}
    taus = [c[1] for c in comparisons if c[1] is not None]
    return top_k, (sum(taus) / len(taus) if taus else None)


def rater_agreement(
    references: list[list[ReferenceEntry]], ks: tuple[int, ...]
) -> Agreement:
    """Mean top-k overlap and Kendall's tau between every pair of references.

    Both metrics are symmetric, so each pair is compared once. As elsewhere, only
    candidates in both references of a pair count.

    Parameters
    ----------
    references : list of list of ReferenceEntry
        Two or more reference rankings, each best first.
    ks : tuple of int
        The top-k overlaps to compute.

    Returns
    -------
    Agreement
        The mean agreement over the pairs.

    Raises
    ------
    ValueError
        If there are fewer than two references, a k is below 1, or two references
        have no candidate in common.
    """
    if len(references) < 2:
        raise ValueError("agreement needs two or more references")
    comparisons = []
    for i, a in enumerate(references):
        for b in references[i + 1 :]:
            comparisons.append(
                compare_ranking(
                    {e.candidate: e.rank for e in a}, [e.candidate for e in a], b, ks
                )
            )
    top_k, tau = mean_comparison(comparisons)
    return Agreement(pairs=len(comparisons), top_k=top_k, tau=tau)
