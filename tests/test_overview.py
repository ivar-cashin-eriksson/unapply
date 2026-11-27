"""The employer's overview of a job: aggregates over its candidates, never one of them.

Runs on the synthetic pool for Fjord Grocery (`tests/fixtures/pool`) and John Doe's
demo on the job board; both scorers replay recordings.
"""

import re
from datetime import date
from uuid import UUID

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.matching import check_hard_filters, own_and_estimated
from unapply.matching.overview import BINS, distribution, job_overview
from unapply.matching.shortlist import identities, rubric_skills
from unapply.taxonomy import default_taxonomy

# The pool's candidates who fail a hard filter on Fjord Grocery.
FAILING = 3
POOL_SIZE = 12


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the API created an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


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
def client(repo, tmp_path):
    return TestClient(
        create_app(repo=repo, uploads=tmp_path / "uploads", llm_factory=NoModel())
    )


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def shortlist_demo(client) -> str:
    return ok(client.post("/demos/shortlist"), 201)["name"]


# Distributions


def test_scores_fall_in_tenths_with_one_in_the_last_bin():
    d = distribution([0.0, 0.0999, 0.1, 0.55, 0.9, 0.9999, 1.0])
    assert d.bins == [2, 1, 0, 0, 0, 1, 0, 0, 0, 3]
    assert d.median == 0.55


def test_out_of_range_scores_are_clamped_and_the_median_of_an_even_count():
    d = distribution([-0.2, 0.2, 0.4, 1.3])
    assert d.bins[0] == 1 and d.bins[-1] == 1 and sum(d.bins) == 4
    assert d.median == pytest.approx(0.3)


def test_no_scores_give_empty_bins_and_no_median():
    d = distribution([])
    assert d.bins == [0] * BINS and d.median is None


# The pool


def test_before_matching_only_the_connected_are_counted(client):
    job = shortlist_demo(client)
    o = ok(client.get(f"/jobs/{job}/overview"))
    assert o["connected"] == POOL_SIZE and o["matched"] == 0
    assert o["passed_hard_filters"] == 0 and o["filters"] == []
    for key in ("totals", "own", "estimated"):
        assert o[key] == {"bins": [0] * BINS, "median": None}
    assert all(s["candidates"] == 0 and s["related"] == 0 for s in o["rubric_skills"])
    assert o["other_skills"] == []
    assert o["counts"]["connected"] == POOL_SIZE and o["vacancies"] == 1


def test_the_pool_in_aggregate(client, repo):
    job = shortlist_demo(client)
    ranking = ok(client.post(f"/jobs/{job}/match"))
    o = ok(client.get(f"/jobs/{job}/overview"))
    assert o["matched"] == POOL_SIZE and o["rubric_version"] == 1
    assert o["passed_hard_filters"] == POOL_SIZE - FAILING

    # Each filter's counts add up, those failed most come first, and they agree
    # with the ranking's checks.
    for f in o["filters"]:
        assert f["passed"] + f["failed"] + f["unknown"] == POOL_SIZE
        expected = sum(
            any(
                c["name"] == f["name"] and c["outcome"] == "fail"
                for c in r["hard_filters"]
            )
            for r in ranking["candidates"]
        )
        assert f["failed"] == expected
    failed = [f["failed"] for f in o["filters"]]
    assert failed == sorted(failed, reverse=True) and sum(failed) >= FAILING

    # The distributions hold the ranking's totals and the baseline's own and
    # estimated scores.
    for key, field in (
        ("totals", "total"),
        ("own", "own_total"),
        ("estimated", "estimated_total"),
    ):
        assert sum(o[key]["bins"]) == POOL_SIZE
        assert (
            o[key]["bins"] == distribution(r[field] for r in ranking["candidates"]).bins
        )

    # Skills: the rubric's in rubric order, counted from the profiles.
    rubric = repo.job(job).rubric
    taxonomy = default_taxonomy()
    assert [s["skill"] for s in o["rubric_skills"]] == rubric_skills(rubric)
    profiles = [
        repo.profile_by_id(UUID(r["profile_id"])) for r in ranking["candidates"]
    ]
    has = [{taxonomy.canonical(s.name) for s in p.skills} for p in profiles]
    for s in o["rubric_skills"]:
        assert s["candidates"] == sum(s["skill"] in h for h in has)
        assert s["candidates"] + s["related"] <= POOL_SIZE
    assert any(s["related"] for s in o["rubric_skills"])
    others = [s["candidates"] for s in o["other_skills"]]
    assert others == sorted(others, reverse=True) and len(others) <= 10
    assert not {s["skill"] for s in o["other_skills"]} & set(rubric_skills(rubric))


def test_the_llm_scorer_gives_its_own_totals_and_the_same_baseline_scores(client):
    job = shortlist_demo(client)
    ok(client.post(f"/jobs/{job}/match"))
    before = ok(client.get(f"/jobs/{job}/overview?scorer=llm"))
    assert before["matched"] == 0
    ranking = ok(client.post(f"/jobs/{job}/match?scorer=llm"))
    llm = ok(client.get(f"/jobs/{job}/overview?scorer=llm"))
    baseline = ok(client.get(f"/jobs/{job}/overview"))
    assert llm["scorer"] == "llm" and llm["matched"] == POOL_SIZE
    assert (
        llm["totals"]["bins"]
        == distribution(r["total"] for r in ranking["candidates"]).bins
    )
    assert llm["own"] == baseline["own"] and llm["estimated"] == baseline["estimated"]


def test_the_package_agrees_with_the_profiles(client, repo):
    job = shortlist_demo(client)
    ok(client.post(f"/jobs/{job}/match"))
    today = date.fromisoformat(repo.job_settings(job)["today"])
    o = job_overview(repo, job, today=today)
    rubric = repo.job(job).rubric
    matches = repo.matches(repo.job(job).id, rubric.version)
    profiles = {m.profile_id: repo.profile_by_id(m.profile_id) for m in matches}
    own = [own_and_estimated(p, rubric)[0] for p in profiles.values()]
    assert o.own.bins == distribution(own).bins
    passed = sum(
        check_hard_filters(p, rubric.hard_filters, today).passed
        for p in profiles.values()
    )
    assert o.passed_hard_filters == passed


def test_the_overview_names_no_one_and_quotes_nothing(client, repo):
    job = shortlist_demo(client)
    ranking = ok(client.post(f"/jobs/{job}/match"))
    text = client.get(f"/jobs/{job}/overview").text
    ids = [UUID(r["profile_id"]) for r in ranking["candidates"]]
    secrets = [str(i) for i in ids]
    secrets += [i.alias for i in identities(ids).values()]
    for pid in ids:
        name = repo.candidate_of(pid)
        secrets.append(name)
        profile = repo.profile_by_id(pid)
        secrets += [e.quote for e in profile.evidence if len(e.quote) > 12]
        secrets += [x.organisation for x in profile.experiences if x.organisation]
    assert len(secrets) > 50
    assert not [s for s in secrets if s in text]
    # No match ids or times either: the overview is counts and skill names.
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text)


# John on the board: withdrawal and the funnel


def john_on(client, job: str) -> tuple[str, str]:
    name = ok(client.post("/demos/candidate"), 201)["name"]
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    ok(client.put(f"/candidates/{name}/connections/{job}"))
    ok(client.post(f"/jobs/{job}/match"))
    return name, ok(client.get(f"/candidates/{name}/profile"))["id"]


def test_the_funnel_and_a_withdrawal(client):
    job = ok(client.post("/demos/board"), 201)["jobs"][0]
    name, profile_id = john_on(client, job)
    o = ok(client.get(f"/jobs/{job}/overview"))
    assert o["connected"] == POOL_SIZE + 1 and o["matched"] == POOL_SIZE + 1
    assert o["counts"]["revealed"] == 0

    ok(client.post(f"/jobs/{job}/candidates/{profile_id}/reveal"), 201)
    ok(client.post(f"/jobs/{job}/candidates/{profile_id}/request-application"), 201)
    o = ok(client.get(f"/jobs/{job}/overview"))
    assert o["counts"] == {
        "connected": POOL_SIZE + 1,
        "revealed": 1,
        "requested": 1,
        "applied": 0,
    }
    ok(client.post(f"/candidates/{name}/applications/{job}", data={"letter": "Hi."}))
    assert ok(client.get(f"/jobs/{job}/overview"))["counts"]["applied"] == 1


def test_a_candidate_who_withdraws_is_no_longer_counted(client):
    job = ok(client.post("/demos/board"), 201)["jobs"][0]
    name, _ = john_on(client, job)
    assert ok(client.get(f"/jobs/{job}/overview"))["matched"] == POOL_SIZE + 1
    ok(client.delete(f"/candidates/{name}/connections/{job}"), 204)
    o = ok(client.get(f"/jobs/{job}/overview"))
    assert o["connected"] == POOL_SIZE and o["matched"] == POOL_SIZE


def test_a_job_without_a_rubric_or_no_job_at_all(client):
    ok(client.post("/jobs", json={"name": "empty"}), 201)
    assert client.get("/jobs/empty/overview").status_code == 409
    assert client.get("/jobs/nothing-here/overview").status_code == 404
