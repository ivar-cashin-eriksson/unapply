"""Evaluation: top-k overlap, Kendall's tau, the synthetic pool and `unapply evaluate`.

The pool (`tests/fixtures/pool/`) has 12 fictional candidates for Fjord Grocery with
an intended ranking. Their extractions, estimates and LLM scorer answers are
hand-written stand-ins (listed in `docs/to-record.md`), so everything runs offline.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update

from unapply.cli import main
from unapply.db.engine import database_url, init_db
from unapply.db.models import AuditEntryRow
from unapply.db.repository import NotFound, Repository
from unapply.evaluation import (
    DEFAULT_POOL,
    ReferenceEntry,
    compare_ranking,
    evaluate_pool,
    kendall_tau,
    load_pool,
    load_reference,
    mean_comparison,
    rater_agreement,
    stored_ranking,
    top_k_overlap,
)
from unapply.evaluation.pool import DEMO_PREFIX, store_pool
from unapply.ingest.extract import normalise_quote
from unapply.llm import LLMError
from unapply.matching import BaselineScorer, check_hard_filters
from unapply.matching.audit import AuditKind
from unapply.matching.filters import Outcome
from unapply.matching.llm_scorer import render_match_prompt
from unapply.matching.run import match_job

PLACEHOLDER = "hand-written placeholder, not a model answer: re-record with --record"
FAILING = {
    "priya-raman": "work_permit",
    "emil-dahl": "min_years_experience",
    "clara-jensen": "work_mode",
}


@pytest.fixture(scope="module")
def pool():
    """The Fjord Grocery pool, loaded once: replaying it is the slow part."""
    return load_pool()


# Metrics


def test_top_k_overlap():
    reference = ["a", "b", "c", "d", "e"]
    assert top_k_overlap(reference, reference, 3) == 1.0
    assert top_k_overlap(["c", "b", "a", "d", "e"], reference, 3) == 1.0
    assert top_k_overlap(["a", "d", "b", "c", "e"], reference, 3) == pytest.approx(
        2 / 3
    )
    assert top_k_overlap(["d", "e", "a", "b", "c"], reference, 2) == 0.0


def test_top_k_overlap_only_counts_candidates_in_both():
    # "x" isn't in the reference and "e" isn't ranked: both are left out first.
    assert top_k_overlap(["x", "a", "b"], ["a", "b", "e"], 2) == 1.0
    # k is capped at the candidates in common.
    assert top_k_overlap(["a", "b"], ["b", "a", "c"], 5) == 1.0


def test_top_k_overlap_refuses_bad_input():
    with pytest.raises(ValueError, match="k must be"):
        top_k_overlap(["a"], ["a"], 0)
    with pytest.raises(ValueError, match="no candidate in common"):
        top_k_overlap(["a"], ["b"], 1)


def test_kendall_tau():
    ranks = {"a": 1, "b": 2, "c": 3, "d": 4}
    assert kendall_tau(ranks, ranks) == 1.0
    assert kendall_tau(ranks, {"a": 4, "b": 3, "c": 2, "d": 1}) == -1.0
    # One swapped pair of six: (5 - 1) / 6.
    assert kendall_tau(ranks, {"a": 1, "b": 3, "c": 2, "d": 4}) == pytest.approx(4 / 6)


def test_kendall_tau_with_ties():
    # a and b share a rank: 2 concordant pairs, 0 discordant, of 3 pairs with 1
    # tied in the ranking: 2 / sqrt(2 x 3).
    tau = kendall_tau({"a": 1, "b": 1, "c": 3}, {"a": 1, "b": 2, "c": 3})
    assert tau == pytest.approx(2 / 6**0.5)
    # Tied the same way in both: a perfect agreement.
    assert kendall_tau({"a": 1, "b": 1, "c": 3}, {"a": 2, "b": 2, "c": 3}) == 1.0


def test_kendall_tau_undefined():
    assert kendall_tau({"a": 1}, {"a": 1}) is None
    assert kendall_tau({"a": 1, "b": 2}, {"a": 1, "c": 2}) is None  # One in common.
    assert kendall_tau({"a": 1, "b": 1}, {"a": 1, "b": 2}) is None  # All tied.


def _reference(*names: str) -> list[ReferenceEntry]:
    """A reference ranking of `names`, best first, without ties."""
    return [ReferenceEntry(n, i) for i, n in enumerate(names, 1)]


# Two people who agree on the top two but swap the 1st and 2nd and the 3rd and 4th.
FIRST = _reference("a", "b", "c", "d")
SECOND = _reference("b", "a", "d", "c")


def test_compare_ranking():
    ranks = {"a": 1, "b": 2, "c": 3, "d": 4}
    top_k, tau = compare_ranking(ranks, ["a", "b", "c", "d"], SECOND, (2, 3))
    assert top_k == {2: 1.0, 3: pytest.approx(2 / 3)}
    # Two of the six pairs swapped: (4 - 2) / 6.
    assert tau == pytest.approx(1 / 3)


def test_mean_comparison_skips_undefined_taus():
    top_k, tau = mean_comparison([({3: 1.0}, 0.5), ({3: 0.5}, None), ({3: 0.0}, 1.0)])
    assert top_k == {3: 0.5}
    assert tau == 0.75
    assert mean_comparison([({3: 1.0}, None)]) == ({3: 1.0}, None)
    with pytest.raises(ValueError, match="nothing to average"):
        mean_comparison([])


def test_rater_agreement_of_two_references():
    agreement = rater_agreement([FIRST, SECOND], (2, 3))
    assert agreement.pairs == 1
    assert agreement.top_k == {2: 1.0, 3: pytest.approx(2 / 3)}
    assert agreement.tau == pytest.approx(1 / 3)
    # Symmetric: the order of the references doesn't matter.
    assert rater_agreement([SECOND, FIRST], (2, 3)) == agreement


def test_rater_agreement_is_the_mean_over_every_pair():
    # Pairs: FIRST-SECOND (tau 1/3), FIRST-FIRST (1) and SECOND-FIRST (1/3).
    agreement = rater_agreement([FIRST, SECOND, FIRST], (3,))
    assert agreement.pairs == 3
    assert agreement.top_k == {3: pytest.approx((2 / 3 + 1 + 2 / 3) / 3)}
    assert agreement.tau == pytest.approx(5 / 9)
    # Identical references agree completely.
    assert rater_agreement([FIRST, FIRST], (2,)).tau == 1.0


def test_rater_agreement_only_counts_candidates_in_both():
    # e and f are each in one reference only, so they don't count.
    agreement = rater_agreement(
        [_reference("a", "e", "b"), _reference("a", "b", "f")], (2,)
    )
    assert agreement.top_k == {2: 1.0}
    assert agreement.tau == 1.0


def test_rater_agreement_without_a_tau():
    # The second reference ties both candidates, so tau can't be computed.
    tied = [ReferenceEntry("a", 1), ReferenceEntry("b", 1)]
    agreement = rater_agreement([_reference("a", "b"), tied], (1,))
    assert agreement.top_k == {1: 1.0}
    assert agreement.tau is None


def test_rater_agreement_refuses_bad_input():
    with pytest.raises(ValueError, match="two or more references"):
        rater_agreement([FIRST], (3,))
    with pytest.raises(ValueError, match="no candidate in common"):
        rater_agreement([FIRST, _reference("x", "y")], (3,))
    with pytest.raises(ValueError, match="k must be 1 or more"):
        rater_agreement([FIRST, SECOND], (0,))


def test_load_reference(tmp_path):
    path = tmp_path / "shortlist.yaml"
    path.write_text(
        "ranking:\n"
        "  - {candidate: b, rank: 2}\n"
        "  - {candidate: a, rank: 1, reason: Best on evidence.}\n",
        encoding="utf-8",
    )
    assert load_reference(path) == [
        ReferenceEntry("a", 1, "Best on evidence."),
        ReferenceEntry("b", 2),
    ]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("{}", "no ranking"),
        ("ranking: []", "no ranking"),
        ("ranking: [{candidate: a}]", "needs `candidate` and `rank`"),
        ("ranking: [{candidate: a, rank: 0}]", "must be 1 or more"),
        ("ranking: [{candidate: a, rank: first}]", "must be 1 or more"),
        ("ranking: [{candidate: a, rank: 1}, {candidate: a, rank: 2}]", "more than"),
    ],
)
def test_load_reference_refuses_invalid_files(tmp_path, text, error):
    path = tmp_path / "shortlist.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_reference(path)


# The pool


def test_the_pool_has_twelve_approved_estimated_candidates(pool):
    assert len(pool.candidates) == 12
    assert [e.candidate for e in pool.intended][:3] == [
        "astrid-holm",
        "mikkel-lund",
        "sofie-krag",
    ]
    assert pool.job.rubric.approved_at is not None
    for name, c in pool.candidates.items():
        assert c.problems == [], name
        assert c.profile.approved_by_candidate_at is not None, name
        assert all(s.estimate for s in c.profile.skills), name
        assert c.profile.claim_support is not None, name


def test_every_quote_is_verbatim_from_the_cv(pool):
    for name, c in pool.candidates.items():
        cv = normalise_quote((c.folder / "material" / "cv.md").read_text("utf-8"))
        for e in c.profile.evidence:
            assert normalise_quote(e.quote) in cv, (name, e.quote)


def test_every_stand_in_is_marked_as_one(pool):
    for c in pool.candidates.values():
        for path in c.folder.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["model"] == PLACEHOLDER, path


def test_hard_filters_fail_exactly_the_intended_candidates(pool):
    for name, c in pool.candidates.items():
        report = check_hard_filters(c.profile, pool.job.rubric.hard_filters, pool.today)
        failed = {k.name for k in report.checks if k.outcome is Outcome.FAIL}
        if name in FAILING:
            assert FAILING[name] in failed, name
        else:
            assert failed == set(), name
        # Everyone is scored, those who fail a hard filter too.
        assert pool.match_recording(name).is_file(), name
    # Just under four years: 10 months as a student assistant and 28 since.
    emil = pool.candidates["emil-dahl"].profile
    report = check_hard_filters(emil, pool.job.rubric.hard_filters, pool.today)
    assert "3.2 years" in report.checks[-1].reason


def test_synonyms_in_the_cv_become_the_rubrics_skills(pool):
    mikkel = {s.name for s in pool.candidates["mikkel-lund"].profile.skills}
    rubric_skills = {c.skill for c in pool.job.rubric.criteria if c.skill}
    assert rubric_skills - {"danish"} <= mikkel
    assert not mikkel & {"python 3", "split testing", "time series prediction"}


def test_the_overclaimer_is_flagged(pool):
    support = pool.candidates["jonas-friis"].profile.claim_support
    assert {"python", "spark", "deep learning", "statistics"} <= set(
        support.overclaims + support.unverified
    )


def test_the_llm_scorer_never_sees_a_candidates_name(pool):
    for name, c in pool.candidates.items():
        prompt, _, _ = render_match_prompt(c.profile, pool.job.rubric)
        for part in name.split("-"):
            assert not re.search(rf"{part}", prompt, re.IGNORECASE), name
        assert "@" not in prompt and "+45" not in prompt, name


# Evaluating the pool


def _order(evaluation):
    return [(name, r.rank) for name, r in evaluation.ranking]


def test_the_baseline_against_the_intended_ranking(pool):
    evaluation = evaluate_pool(pool, "baseline")
    assert evaluation.model == "baseline-v1"
    assert [n for n, _ in evaluation.ranking] == [
        "astrid-holm",
        "mikkel-lund",
        "sofie-krag",
        # The baseline trusts own levels where estimates are unsure, so the
        # overclaimer (intended 8th) comes 4th: what the evaluation is for.
        "jonas-friis",
        "lars-winther",
        "nadia-kowal",
        "freja-nygaard",
        "ida-thorsen",
        "henrik-mose",
        # Those who fail a hard filter are scored too, and come after everyone
        # who passes, by score; the reference has them share the last place.
        "priya-raman",
        "clara-jensen",
        "emil-dahl",
    ]
    assert [r.rank for _, r in evaluation.ranking] == list(range(1, 13))
    failed = {n: r for n, r in evaluation.ranking if not r.match.passed_hard_filters}
    assert set(failed) == set(FAILING)
    assert failed["priya-raman"].total > evaluation.ranking[8][1].total
    assert evaluation.top_k == {3: 1.0, 5: 0.8}
    assert evaluation.tau == pytest.approx(0.8219, abs=1e-4)


def test_the_llm_scorer_against_the_intended_ranking(pool):
    evaluation = evaluate_pool(pool, "llm", ks=(1, 3, 5))
    assert evaluation.model == f"replay:{PLACEHOLDER}"
    assert all(r.problems == [] for r in evaluation.results.values())
    intended = {e.candidate: e.rank for e in pool.intended}
    # The intended order, with the three who fail a hard filter ordered by score
    # after the rest instead of sharing the last place.
    assert all(intended[n] == min(r, 10) for n, r in _order(evaluation))
    assert [n for n, _ in evaluation.ranking][9:] == [
        "priya-raman",
        "clara-jensen",
        "emil-dahl",
    ]
    assert evaluation.top_k == {1: 1.0, 3: 1.0, 5: 1.0}
    # Every pair the reference orders is in order; tau-b is just under 1 as the
    # reference ties the last three and the ranking doesn't: sqrt(63 / 66).
    assert evaluation.tau == pytest.approx((63 / 66) ** 0.5)


def test_a_partial_reference_such_as_a_shortlist(pool):
    shortlist = [
        ReferenceEntry("sofie-krag", 1),
        ReferenceEntry("astrid-holm", 2),
        ReferenceEntry("jonas-friis", 3),
    ]
    evaluation = evaluate_pool(pool, "baseline", shortlist, ks=(2,))
    # Of the three, the baseline orders astrid, sofie, jonas: one pair swapped.
    assert evaluation.top_k == {2: 1.0}
    assert evaluation.tau == pytest.approx(1 / 3)


def test_an_unknown_scorer_is_refused(pool):
    with pytest.raises(ValueError, match="unknown scorer"):
        evaluate_pool(pool, "magic")


def _copy_pool(tmp_path: Path) -> Path:
    """Copy the pool and the job it points to, keeping their relative places."""
    fixtures = DEFAULT_POOL.parent
    shutil.copytree(fixtures / "pool", tmp_path / "pool")
    shutil.copytree(
        fixtures / "jobs" / "fjord_grocery", tmp_path / "jobs" / "fjord_grocery"
    )
    return tmp_path / "pool"


def test_a_passing_candidate_without_a_recording_fails_loudly(tmp_path):
    folder = _copy_pool(tmp_path)
    (folder / "henrik-mose" / "match_fjord_grocery.json").unlink()
    pool = load_pool(folder)
    with pytest.raises(LLMError, match="no recorded answer"):
        evaluate_pool(pool, "llm")
    assert evaluate_pool(pool, "baseline").tau is not None  # Needs no recording.


def test_a_reference_naming_a_missing_candidate_is_refused(tmp_path):
    folder = _copy_pool(tmp_path)
    shutil.rmtree(folder / "henrik-mose")
    with pytest.raises(ValueError, match="no candidate folder for: henrik-mose"):
        load_pool(folder)


# The command


def test_cli_evaluates_both_scorers(capsys):
    assert main(["evaluate"]) == 0
    out = capsys.readouterr().out
    assert "12 candidates" in out
    assert "baseline (baseline-v1)" in out
    assert "top-3 overlap 1.00  top-5 overlap 0.80  Kendall's tau 0.82" in out
    assert "top-3 overlap 1.00  top-5 overlap 1.00  Kendall's tau 0.98" in out
    assert out.count("(failed hard filters)") == 6
    assert "problem:" not in out


def test_cli_with_a_reference_one_scorer_and_k(tmp_path, capsys):
    path = tmp_path / "shortlist.yaml"
    path.write_text(
        "ranking:\n"
        "  - {candidate: sofie-krag, rank: 1}\n"
        "  - {candidate: astrid-holm, rank: 2}\n"
        "  - {candidate: jonas-friis, rank: 3}\n",
        encoding="utf-8",
    )
    args = ["evaluate", "--reference", str(path), "--scorer", "baseline", "--k", "2"]
    assert main([*args, "-v"]) == 0
    out = capsys.readouterr().out
    assert f"Reference: {path}" in out
    assert "llm (" not in out
    assert "top-2 overlap 1.00  Kendall's tau 0.33" in out
    # The baseline can't read "retail experience"; --verbose says so.
    assert "names no skill, so the baseline doesn't score it" in out


def _write_reference(path: Path, *names: str) -> Path:
    path.write_text(
        "ranking:\n"
        + "".join(
            f"  - {{candidate: {n}, rank: {i}}}\n" for i, n in enumerate(names, 1)
        ),
        encoding="utf-8",
    )
    return path


def test_cli_with_several_references(tmp_path, capsys):
    first = _write_reference(
        tmp_path / "first.yaml",
        "astrid-holm",
        "mikkel-lund",
        "sofie-krag",
        "henrik-mose",
    )
    second = _write_reference(
        tmp_path / "second.yaml",
        "mikkel-lund",
        "astrid-holm",
        "henrik-mose",
        "sofie-krag",
    )
    args = ["evaluate", "--scorer", "baseline", "--k", "2", "3"]
    assert main([*args, "--reference", str(first), "--reference", str(second)]) == 0
    out = capsys.readouterr().out
    assert f"  1: {first}" in out and f"  2: {second}" in out
    # The two people agree on the top two and swap two of six pairs.
    assert (
        "Agreement between the references (the ceiling, 1 pair): "
        "top-2 overlap 1.00  top-3 overlap 0.67  Kendall's tau 0.33"
    ) in out
    assert "  rank  total  ref 1  ref 2  candidate" in out
    # The baseline ranks Astrid, Mikkel, Sofie, ... Henrik: the first person's order.
    assert re.search(r"\n +1 +0\.\d\d +1 +2  astrid-holm\n", out)
    assert re.search(r" +-  +-  jonas-friis\n", out)
    assert "  ref 1: top-2 overlap 1.00  top-3 overlap 1.00  Kendall's tau 1.00" in out
    assert "  ref 2: top-2 overlap 1.00  top-3 overlap 0.67  Kendall's tau 0.33" in out
    assert "  mean: top-2 overlap 1.00  top-3 overlap 0.83  Kendall's tau 0.67" in out


def test_cli_refuses_references_with_no_candidate_in_common(tmp_path, capsys):
    first = _write_reference(tmp_path / "first.yaml", "astrid-holm", "mikkel-lund")
    second = _write_reference(tmp_path / "second.yaml", "sofie-krag", "henrik-mose")
    args = ["evaluate", "--reference", str(first), "--reference", str(second)]
    assert main(args) == 2
    assert "no candidate in common" in capsys.readouterr().err


def _digest(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            h.update(path.as_posix().encode() + path.read_bytes())
    return h.hexdigest()


def test_cli_record_is_refused_without_allow_api(capsys):
    before = _digest(DEFAULT_POOL)
    assert main(["evaluate", "--record"]) == 3
    assert "paid API call" in capsys.readouterr().err
    assert _digest(DEFAULT_POOL) == before


def test_cli_reports_a_broken_pool(tmp_path, capsys):
    assert main(["evaluate", str(tmp_path)]) == 2
    assert "Can't evaluate" in capsys.readouterr().err
    assert main(["evaluate", "--k", "0"]) == 2


# A job's ranking from the database


@pytest.fixture
def ranked_db(pool):
    """A database with the pool stored as job "fjord", matched twice by the baseline.

    The first ranking is of the first six candidates only, the second of all.
    """
    init_db()
    repo = Repository.from_url(database_url())
    names = store_pool(repo, pool, "fjord")
    match_job(repo, "fjord", lambda n, s: BaselineScorer(), names[:6], pool.today)
    match_job(repo, "fjord", lambda n, s: BaselineScorer(), today=pool.today)
    yield repo
    repo.engine.dispose()


def _intended_in_db(pool, path: Path) -> Path:
    """The pool's intended ranking, naming candidates as they are in the database."""
    path.write_text(
        "ranking:\n"
        + "".join(
            f"  - {{candidate: {DEMO_PREFIX}{e.candidate}, rank: {e.rank}}}\n"
            for e in pool.intended
        ),
        encoding="utf-8",
    )
    return path


def test_stored_ranking_names_each_candidate_as_in_the_database(pool, ranked_db):
    stored = stored_ranking(ranked_db, "fjord")
    evaluated = evaluate_pool(pool, "baseline")
    # The same candidates, places and totals as ranking the pool directly.
    assert [(n, r.rank, r.total) for n, r in stored.ranking] == [
        (DEMO_PREFIX + n, r.rank, r.total) for n, r in evaluated.ranking
    ]
    assert (stored.scorer, stored.model, stored.rubric_version) == (
        "baseline",
        "baseline-v1",
        pool.job.rubric.version,
    )
    first, latest = ranked_db.audit_log(kind=AuditKind.RANKING)
    assert stored.entry_id == latest.id
    assert len(stored_ranking(ranked_db, "fjord", first.id).ranking) == 6


def test_stored_ranking_refuses_what_it_cant_read(ranked_db):
    with pytest.raises(NotFound):
        stored_ranking(ranked_db, "nothing")
    with pytest.raises(ValueError, match="no ranking 999 of job 'fjord'"):
        stored_ranking(ranked_db, "fjord", 999)
    ranked_db.create_job("empty")
    with pytest.raises(ValueError, match="has no rubric"):
        stored_ranking(ranked_db, "empty")


def test_a_profile_no_candidate_has_is_named_by_its_id(pool, ranked_db):
    entry = ranked_db.audit_log(kind=AuditKind.RANKING)[-1]
    gone = entry.payload["ranking"][0]["match"]["profile_id"]
    with ranked_db.engine.begin() as connection:
        entry.payload["ranking"][0]["match"]["profile_id"] = str(uuid4())
        connection.execute(
            update(AuditEntryRow)
            .where(AuditEntryRow.id == entry.id)
            .values(payload=entry.payload)
        )
    name, _ = stored_ranking(ranked_db, "fjord").ranking[0]
    assert name.startswith("profile ") and gone not in name


def test_cli_evaluates_a_stored_ranking(pool, ranked_db, tmp_path, capsys):
    reference = _intended_in_db(pool, tmp_path / "intended.yaml")
    before = len(ranked_db.audit_log())
    assert main(["evaluate", "--job", "fjord", "--reference", str(reference)]) == 0
    out = capsys.readouterr().out
    latest = ranked_db.audit_log(kind=AuditKind.RANKING)[-1]
    assert f"ranking #{latest.id} of " in out and "12 candidates" in out
    assert "baseline (baseline-v1)" in out
    # The same ranking as the pool's baseline, so the same agreement.
    assert "top-3 overlap 1.00  top-5 overlap 0.80  Kendall's tau 0.82" in out
    assert re.search(r"\n +1 +0\.\d\d +1  pool-astrid-holm\n", out)
    assert out.count("(failed hard filters)") == 3
    # Nothing was scored or recorded again.
    assert len(ranked_db.audit_log()) == before


def test_cli_evaluates_an_older_stored_ranking_with_several_references(
    pool, ranked_db, tmp_path, capsys
):
    first_id = ranked_db.audit_log(kind=AuditKind.RANKING)[0].id
    intended = _intended_in_db(pool, tmp_path / "intended.yaml")
    other = _write_reference(
        tmp_path / "other.yaml", "pool-mikkel-lund", "pool-astrid-holm"
    )
    args = ["evaluate", "--job", "fjord", "--ranking", str(first_id), "--k", "2"]
    assert main([*args, "--reference", str(intended), "--reference", str(other)]) == 0
    out = capsys.readouterr().out
    assert f"ranking #{first_id} of " in out and "6 candidates" in out
    assert "Agreement between the references (the ceiling, 1 pair)" in out
    assert "  ref 1: " in out and "  ref 2: " in out and "  mean: " in out


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--job", "fjord"], "--job needs at least one --reference"),
        (["--job", "fjord", "tests/fixtures/pool", "--reference", "r.yaml"], "a pool"),
        (["--job", "fjord", "--scorer", "llm", "--reference", "r.yaml"], "--scorer"),
        (["--job", "fjord", "--record", "--reference", "r.yaml"], "--record"),
        (["--ranking", "1"], "--ranking and --url need --job"),
        (["--job", "nothing", "--reference", "REF"], "Can't evaluate: "),
        (
            ["--job", "fjord", "--ranking", "999", "--reference", "REF"],
            "no ranking 999",
        ),
        (["--job", "fjord", "--reference", "OTHER"], "no candidate in common"),
    ],
)
def test_cli_refuses_a_stored_ranking_it_cant_evaluate(
    pool, ranked_db, tmp_path, capsys, args, error
):
    reference = str(_intended_in_db(pool, tmp_path / "intended.yaml"))
    other = str(_write_reference(tmp_path / "other.yaml", "astrid-holm"))
    args = [{"REF": reference, "OTHER": other}.get(a, a) for a in args]
    assert main(["evaluate", *args]) == 2
    assert error in capsys.readouterr().err
