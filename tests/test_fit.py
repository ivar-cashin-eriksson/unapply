"""Tests for how well a candidate fits a job on the board (task 15).

The band comes from the baseline on own levels only, the missed hard filters are
named as the ad states them, and the place comes from the job's latest ranking.
Everything runs on the synthetic pool, John Doe's demo and the demo jobs, offline.
"""

import json
from pathlib import Path

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.app.forms import candidate_view
from unapply.db.engine import database_url, init_db
from unapply.db.repository import NotFound, Repository
from unapply.evaluation.pool import load_board, load_pool, store_board
from unapply.jobs.fit import (
    FitBand,
    band,
    filter_label,
    fit,
    missed_filters,
    own_band,
    place,
)
from unapply.matching.audit import AuditKind
from unapply.matching.baseline import BaselineScorer, own_total
from unapply.matching.run import match_job
from unapply.schemas import HardFilters, SkillEstimate, SkillLevel, WorkMode

FJORD = "board-fjord-grocery"
# Nothing about the rubric or the assessment may reach a candidate.
HIDDEN_WORDS = (
    "criteria",
    "criterion",
    "weight",
    "min_level",
    "hard_filters",
    "score",
    "total",
    "overclaim",
    "underclaim",
    "unverified",
    "statement_only",
    "estimate",
    "confidence",
    "claim_support",
)


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the API created an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


@pytest.fixture(scope="module")
def pool():
    return load_pool()


@pytest.fixture(scope="module")
def board():
    return load_board()


@pytest.fixture
def repo():
    init_db()
    repo = Repository.from_url(database_url())
    yield repo
    repo.engine.dispose()


class NoModel:
    """A model factory that must never be used: everything here replays."""

    def __call__(self, purpose: str, allow: bool):
        raise AssertionError(f"a model was asked for ({purpose})")


@pytest.fixture
def client(repo, tmp_path: Path):
    return TestClient(
        create_app(repo=repo, uploads=tmp_path / "uploads", llm_factory=NoModel())
    )


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def approved_demo(client) -> str:
    """John Doe's demo candidate with his review saved and approved."""
    name = ok(client.post("/demos/candidate"), 201)["name"]
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    return name


def assert_hidden(body) -> None:
    text = json.dumps(body).lower()
    assert not [w for w in HIDDEN_WORDS if w in text], text


def job_of(board, folder: str):
    return next(b.job for b in board[1] if b.folder == folder)


# Bands


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (1.0, FitBand.STRONG),
        (0.8, FitBand.STRONG),
        (0.7999, FitBand.GOOD),
        (0.6, FitBand.GOOD),
        (0.5999, FitBand.PARTIAL),
        (0.3, FitBand.PARTIAL),
        (0.2999, FitBand.LOW),
        (0.0, FitBand.LOW),
    ],
)
def test_bands_at_their_edges(total, expected):
    assert band(total) is expected


# (pool candidate, job folder, band): clear fits, near misses and mismatches.
POOL_BANDS = [
    ("astrid-holm", "fjord_grocery", FitBand.STRONG),
    ("sofie-krag", "lynfjord_power", FitBand.STRONG),
    ("freja-nygaard", "havnelys_logistics", FitBand.STRONG),
    ("nadia-kowal", "ravnekaer_mobility", FitBand.STRONG),
    ("ida-thorsen", "oresund_academy", FitBand.STRONG),
    ("lars-winther", "kloevermark_supermarkets", FitBand.STRONG),
    ("lars-winther", "fjord_grocery", FitBand.GOOD),
    ("freja-nygaard", "fjord_grocery", FitBand.GOOD),
    ("ida-thorsen", "fjord_grocery", FitBand.PARTIAL),
    ("astrid-holm", "kloevermark_supermarkets", FitBand.PARTIAL),
    ("henrik-mose", "fjord_grocery", FitBand.LOW),
    ("nadia-kowal", "oresund_academy", FitBand.LOW),
]


@pytest.mark.parametrize(("candidate", "folder", "expected"), POOL_BANDS)
def test_the_pool_gets_sensible_bands(pool, board, candidate, folder, expected):
    profile = pool.candidates[candidate].profile
    assert own_band(profile, job_of(board, folder).rubric) is expected


def test_the_band_uses_own_levels_and_never_the_estimate(pool, board):
    # The overclaimer rates himself expert; his estimates are far lower, but the
    # band is his own rating.
    rubric = job_of(board, "fjord_grocery").rubric
    jonas = pool.candidates["jonas-friis"].profile
    assert own_band(jonas, rubric) is FitBand.STRONG
    changed = jonas.model_copy(
        update={
            "skills": [
                s.model_copy(
                    update={
                        "estimate": SkillEstimate(
                            level=SkillLevel.AWARE,
                            confidence=1.0,
                            rationale="x",
                            model="test",
                        )
                    }
                )
                for s in jonas.skills
            ]
        }
    )
    assert own_band(changed, rubric) is own_band(jonas, rubric)
    assert own_total(candidate_view(jonas), rubric) == own_total(jonas, rubric)


def test_every_pool_band_matches_the_own_rating(pool, board):
    for b in board[1]:
        for c in pool.candidates.values():
            total = own_total(candidate_view(c.profile), b.job.rubric)
            assert own_band(c.profile, b.job.rubric) is band(total)


# Missed hard filters


def test_filters_are_named_as_the_ad_states_them():
    filters = HardFilters(
        locations=["Copenhagen", "Aarhus"],
        work_modes=[WorkMode.HYBRID, WorkMode.ONSITE],
        required_work_permits=["EU"],
        min_years_experience=4,
    )
    assert filter_label("location", filters) == "Location: Copenhagen, Aarhus"
    assert filter_label("work_mode", filters) == "Work mode: hybrid or onsite"
    assert filter_label("work_permit", filters) == "Work permit: EU required"
    assert filter_label("min_years_experience", filters) == (
        "Experience: at least 4 years"
    )
    one = HardFilters(min_years_experience=1)
    assert filter_label("min_years_experience", one) == "Experience: at least 1 year"
    with pytest.raises(ValueError, match="unknown"):
        filter_label("height", filters)


def test_the_pool_misses_the_filters_it_fails(pool, board):
    today, jobs = board
    filters = job_of(board, "fjord_grocery").rubric.hard_filters
    missed = {
        name: [m.label for m in missed_filters(c.profile, filters, today)]
        for name, c in pool.candidates.items()
    }
    assert missed["priya-raman"] == ["Work permit: EU required"]
    assert missed["emil-dahl"] == ["Experience: at least 4 years"]
    assert missed["clara-jensen"] and all(
        m.startswith(("Work mode:", "Location:")) for m in missed["clara-jensen"]
    )
    passing = {n for n, m in missed.items() if not m}
    assert len(passing) == 9
    # Unknowns aren't failures: a profile that gives no place or permit misses
    # neither.
    astrid = pool.candidates["astrid-holm"].profile
    silent = astrid.model_copy(
        update={
            "preferences": astrid.preferences.model_copy(
                update={"locations": [], "work_permits": []}
            )
        }
    )
    assert missed_filters(silent, filters, today) == []


# Through the database and the API


def test_fit_before_connecting(client, repo):
    ok(client.post("/demos/board"), 201)
    name = approved_demo(client)
    consents, audit = len(repo.consents(FJORD)), len(repo.audit_log())
    fits = ok(client.get(f"/candidates/{name}/fit"))
    assert len(fits) == 11
    assert_hidden(fits)
    by_job = {f["job"]: f for f in fits}
    assert by_job[FJORD] == {
        "job": FJORD,
        "band": "strong",
        "missed": [],
        "connected": False,
        "place": None,
    }
    assert by_job["board-kloevermark-supermarkets"]["band"] == "low"
    assert by_job["board-ravnekaer-mobility"]["band"] == "good"
    assert by_job["board-havnelys-logistics"]["band"] == "partial"
    assert [m["label"] for m in by_job["board-kaveri-retail"]["missed"]] == [
        "Location: Bengaluru",
        "Work permit: IN required",
    ]
    assert all(not f["connected"] and f["place"] is None for f in fits)
    one = ok(client.get(f"/candidates/{name}/fit/{FJORD}"))
    assert one == by_job[FJORD]
    # Nothing is stored for jobs the candidate hasn't connected to.
    assert len(repo.consents(FJORD)) == consents
    assert len(repo.audit_log()) == audit
    assert ok(client.get(f"/candidates/{name}/connections")) == []


def test_place_after_connecting_comes_from_the_latest_ranking(client, repo):
    ok(client.post("/demos/board"), 201)
    name = approved_demo(client)
    ok(client.put(f"/candidates/{name}/connections/{FJORD}"))
    # Connected, but not ranked yet.
    before = ok(client.get(f"/candidates/{name}/fit/{FJORD}"))
    assert before["connected"] and before["place"] is None

    ranking = ok(client.post(f"/jobs/{FJORD}/match"))["candidates"]
    profile_id = ok(client.get(f"/candidates/{name}/profile"))["id"]
    mine = next(c for c in ranking if c["profile_id"] == profile_id)
    after = ok(client.get(f"/candidates/{name}/fit/{FJORD}"))
    assert_hidden(after)
    assert after["place"]["rank"] == mine["rank"] == 3
    assert after["place"]["of"] == len(ranking) == 13
    latest = repo.audit_log(repo.job(FJORD).id, AuditKind.RANKING)[-1]
    assert after["place"]["ranked_at"] == latest.recorded_at.isoformat()

    # Another ranking is the latest one now.
    ok(client.get(f"/jobs/{FJORD}/ranking"))
    newer = repo.audit_log(repo.job(FJORD).id, AuditKind.RANKING)[-1]
    again = ok(client.get(f"/candidates/{name}/fit/{FJORD}"))
    assert again["place"]["ranked_at"] == newer.recorded_at.isoformat()

    # Withdrawn: no place, though earlier rankings still include them.
    assert client.delete(f"/candidates/{name}/connections/{FJORD}").status_code == 204
    gone = ok(client.get(f"/candidates/{name}/fit/{FJORD}"))
    assert not gone["connected"] and gone["place"] is None
    assert gone["band"] == "strong"


def test_a_pool_candidate_failing_a_filter_ranks_after_those_who_pass(
    repo, pool, board
):
    store_board(repo, pool)
    assert place(repo, "pool-priya-raman", FJORD) is None  # Not ranked yet.
    match_job(repo, FJORD, lambda name, settings: BaselineScorer(), today=board[0])
    priya = fit(repo, "pool-priya-raman", FJORD)
    assert priya.connected  # The pool is connected to every demo job.
    assert priya.band is FitBand.STRONG
    assert [m.label for m in priya.missed] == ["Work permit: EU required"]
    assert priya.place.of == 12
    assert priya.place.rank == 10  # After the nine who pass, first of the rest.
    astrid = fit(repo, "pool-astrid-holm", FJORD)
    assert (astrid.place.rank, astrid.missed) == (1, [])


def test_unknown_candidates_and_jobs(repo, pool):
    store_board(repo, pool)
    with pytest.raises(NotFound):
        fit(repo, "nobody", FJORD)
    assert fit(repo, "pool-astrid-holm", "no-such-job") is None
    repo.create_candidate("jane")  # No profile yet: no band, nothing missed.
    jane = fit(repo, "jane", FJORD)
    assert (jane.band, jane.missed, jane.connected, jane.place) == (
        None,
        [],
        False,
        None,
    )


def test_fit_routes_refuse_unknown_names(client):
    ok(client.post("/demos/board"), 201)
    assert client.get("/candidates/nobody/fit").status_code == 404
    assert client.get(f"/candidates/nobody/fit/{FJORD}").status_code == 404
    name = approved_demo(client)
    assert client.get(f"/candidates/{name}/fit/no-such-job").status_code == 404
