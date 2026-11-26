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
