"""A candidate's jobs: how far they got on each, their fit, and their success rate.

Runs on the demo board with the synthetic pool (`tests/fixtures/pool`) connected to
every demo job, with demo reveals and requests made through `unapply.jobs.hiring`.
Everything replays recordings or is plain code: no model is called.
"""

import json
import re
from datetime import datetime
from statistics import median

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.dashboard import MIN_GROUP
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.jobs.hiring import Stage, answer, request_application, reveal
from unapply.jobs.outcomes import (
    COMMON_SHARE,
    candidate_jobs,
    revealed_profiles,
    revealed_skills,
)
from unapply.schemas import ClaimSupport, Profile, Skill, SkillEstimate, SkillLevel
from unapply.taxonomy import default_taxonomy

BOARD_SIZE = 11
FJORD = "board-fjord-grocery"
LYNFJORD = "board-lynfjord-power"
# Words for the assessment and the rubric, which a candidate never sees.
HIDDEN = re.compile(
    r"estimat|confidence|claim|overclaim|underclaim|unverified|rationale|rubric|"
    r"criteri|weight|min.?level|gap",
    re.I,
)


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


@pytest.fixture
def pool(client, repo) -> list[str]:
    """Put the demo board up; return the pool candidates' names, sorted."""
    ok(client.post("/demos/board"), 201)
    return [n for n in repo.candidate_names() if repo.settings(n).get("pool")]


def approved_john(client) -> str:
    name = ok(client.post("/demos/candidate"), 201)["name"]
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    return name


def reveal_all(repo, job: str, names: list[str]) -> None:
    for name in names:
        reveal(repo, job, repo.profile(name).id)


def outcome(jobs: dict, job: str) -> dict:
    return next(j for j in jobs["jobs"] if j["job"] == job)


# Stages, fit and the success rate


def test_a_pool_candidate_sees_every_demo_job_with_its_stage_and_fit(
    client, repo, pool
):
    me, *others = pool
    reveal_all(repo, FJORD, [me])
    request_application(repo, FJORD, repo.profile(me).id)
    answer(repo, me, FJORD, "applied", letter="I'd like to.")
    reveal_all(repo, LYNFJORD, [me])

    jobs = ok(client.get(f"/candidates/{me}/jobs"))
    assert jobs["connected"] == BOARD_SIZE
    assert jobs["revealed"] == 2 and jobs["requested"] == 1 and jobs["applied"] == 1
    assert jobs["revealed_rate"] == pytest.approx(2 / BOARD_SIZE)
    assert jobs["requested_rate"] == pytest.approx(1 / BOARD_SIZE)
    assert jobs["min_group"] == MIN_GROUP
    assert outcome(jobs, FJORD)["stage"] == Stage.APPLIED
    assert outcome(jobs, LYNFJORD)["stage"] == Stage.REVEALED
    fits = {f["job"]: f for f in ok(client.get(f"/candidates/{me}/fit"))}
    for j in jobs["jobs"]:
        assert j["listing"]["name"] == j["job"]
        assert j["fit"] == fits[j["job"]]
        assert j["fit"]["connected"] is True


def test_the_success_rate_counts_only_the_jobs_john_connected_to(client, repo, pool):
    john = approved_john(client)
    empty = ok(client.get(f"/candidates/{john}/jobs"))
    assert empty["jobs"] == [] and empty["connected"] == 0
    assert empty["revealed_rate"] is None and empty["requested_rate"] is None

    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    ok(client.put(f"/candidates/{john}/connections/{LYNFJORD}"))
    reveal_all(repo, LYNFJORD, [john])
    request_application(repo, LYNFJORD, repo.profile(john).id)
    answer(repo, john, LYNFJORD, "declined")
    jobs = ok(client.get(f"/candidates/{john}/jobs"))
    # Newest connection first.
    assert [j["job"] for j in jobs["jobs"]] == [LYNFJORD, FJORD]
    assert [j["stage"] for j in jobs["jobs"]] == [Stage.DECLINED, Stage.CONNECTED]
    assert (jobs["connected"], jobs["revealed"], jobs["requested"]) == (2, 1, 1)
    assert jobs["applied"] == 0
    assert jobs["revealed_rate"] == 0.5 and jobs["requested_rate"] == 0.5


def test_an_unknown_candidate_is_not_found(client):
    assert client.get("/candidates/nobody/jobs").status_code == 404


# Skills common among the revealed, and the group-size rule


def test_skills_are_suggested_only_once_five_others_were_revealed(client, repo, pool):
    me, *others = pool
    reveal_all(repo, FJORD, others[: MIN_GROUP - 1])
    assert (
        outcome(ok(client.get(f"/candidates/{me}/jobs")), FJORD)["revealed_skills"]
        is None
    )

    reveal_all(repo, FJORD, [others[MIN_GROUP - 1]])
    tips = outcome(ok(client.get(f"/candidates/{me}/jobs")), FJORD)["revealed_skills"]
    assert tips is not None
    # A job nobody was revealed on suggests nothing.
    assert (
        outcome(ok(client.get(f"/candidates/{me}/jobs")), LYNFJORD)["revealed_skills"]
        is None
    )


def test_a_revealed_candidate_gets_no_suggestions_for_that_job(client, repo, pool):
    me, *others = pool
    reveal_all(repo, FJORD, [*others[:MIN_GROUP], me])
    assert (
        outcome(ok(client.get(f"/candidates/{me}/jobs")), FJORD)["revealed_skills"]
        is None
    )


def test_copies_of_the_demo_never_count_as_revealed_others(client, repo, pool):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    copies = [approved_john(client) for _ in range(MIN_GROUP)]
    for c in copies:
        ok(client.put(f"/candidates/{c}/connections/{FJORD}"))
    reveal_all(repo, FJORD, copies)
    assert revealed_profiles(repo, FJORD, john) == []
    assert (
        outcome(ok(client.get(f"/candidates/{john}/jobs")), FJORD)["revealed_skills"]
        is None
    )


def test_the_suggestions_are_the_common_skills_john_lacks_or_rated_lower(
    client, repo, pool
):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    shown = pool[:7]
    reveal_all(repo, FJORD, shown)
    for name in shown[:3]:
        request_application(repo, FJORD, repo.profile(name).id)
    tips = outcome(ok(client.get(f"/candidates/{john}/jobs")), FJORD)["revealed_skills"]

    # Worked out again by hand from the pool's own levels.
    taxonomy = default_taxonomy()
    profiles = [repo.profile(n) for n in shown]
    listed = {
        n: {taxonomy.canonical(s.name): s.self_level for s in p.skills}
        for n, p in zip(shown, profiles, strict=True)
    }
    skills = {s for x in listed.values() for s in x}
    count = {s: sum(s in x for x in listed.values()) for s in skills}
    common = {s for s in skills if count[s] >= COMMON_SHARE * len(shown)}
    own = {taxonomy.canonical(s.name): s.self_level for s in repo.profile(john).skills}
    implied = set().union(*(taxonomy.implied(s) for s in own))
    missing = {s for s in common if s not in own and s not in implied}
    lower = set()
    for s in common & own.keys():
        rated = [int(x[s]) for x in listed.values() if x.get(s) is not None]
        if own[s] is not None and len(rated) >= MIN_GROUP and own[s] < median(rated):
            lower.add(s)

    assert set(tips["missing"]) <= missing
    assert len(tips["missing"]) == min(len(missing), 5)
    assert set(tips["lower"]) == lower or len(tips["lower"]) == 5
    assert set(tips["lower"]) <= lower
    # Most common first.
    for found in (tips["missing"], tips["lower"]):
        assert [count[s] for s in found] == sorted(
            (count[s] for s in found), reverse=True
        )
    # The pool and John differ, so there is something to suggest.
    assert tips["missing"] or tips["lower"]


def own_levels(levels: dict[str, int | None]) -> Profile:
    return Profile(
        skills=[
            Skill(name=k, self_level=SkillLevel(v) if v else None)
            for k, v in levels.items()
        ]
    )


def test_lower_needs_five_of_the_revealed_to_have_rated_it():
    taxonomy = default_taxonomy()
    me = own_levels({"python": 1, "sql": 1})
    # Five revealed list both; all five rate python, only four rate sql.
    revealed = [own_levels({"python": 4, "sql": 4}) for _ in range(4)]
    revealed.append(own_levels({"python": 4, "sql": None}))
    tips = revealed_skills(me, revealed, taxonomy)
    assert tips.lower == ["python"]
    assert tips.missing == []
    assert revealed_skills(me, revealed[:4], taxonomy) is None


def test_common_means_at_least_half_of_the_revealed():
    taxonomy = default_taxonomy()
    me = own_levels({"python": 3})
    revealed = [own_levels({"python": 3, "kafka": 3}) for _ in range(3)]
    revealed += [own_levels({"python": 3, "dbt": 3}) for _ in range(3)]
    revealed.append(own_levels({"python": 3, "terraform": 3}))
    tips = revealed_skills(me, revealed, taxonomy)
    # 3 of 7 is under half; and the same level isn't lower.
    assert tips.missing == [] and tips.lower == []
    revealed.append(own_levels({"python": 3, "kafka": 2}))
    assert revealed_skills(me, revealed, taxonomy).missing == ["kafka"]


# Nothing hidden, nothing about one other candidate


def test_no_assessment_rubric_or_other_candidate_reaches_the_jobs(client, repo, pool):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    shown = pool[:6]
    reveal_all(repo, FJORD, shown)
    before = ok(client.get(f"/candidates/{john}/jobs"))
    assert outcome(before, FJORD)["revealed_skills"] is not None

    text = json.dumps({k: v for k, v in before.items() if k != "jobs"}) + json.dumps(
        [{k: v for k, v in j.items() if k != "listing"} for j in before["jobs"]]
    )
    assert not HIDDEN.search(text), HIDDEN.search(text)
    for name in shown:
        profile = repo.profile(name)
        assert name not in text
        assert str(profile.id) not in text
        assert all(e.quote not in text for e in profile.evidence)
        assert all(
            x.organisation not in text for x in profile.experiences if x.organisation
        )

    # Rewriting every estimate and the claim support changes nothing.
    for name in [john, *shown]:
        p = repo.profile(name)
        rewritten = p.model_copy(
            update={
                "skills": [
                    s.model_copy(
                        update={
                            "estimate": SkillEstimate(
                                level=SkillLevel.AWARE,
                                confidence=0.01,
                                rationale="rewritten",
                                model="test",
                                estimated_at=datetime(2026, 1, 1),
                            )
                        }
                    )
                    for s in p.skills
                ],
                "claim_support": ClaimSupport(
                    rated=1, overclaims=[s.name for s in p.skills]
                ),
            }
        )
        repo.save_profile(name, rewritten, "assessed")
    after = ok(client.get(f"/candidates/{john}/jobs"))
    assert [j["revealed_skills"] for j in after["jobs"]] == [
        j["revealed_skills"] for j in before["jobs"]
    ]
    assert after["revealed_rate"] == before["revealed_rate"]


def test_the_library_matches_the_route(client, repo, pool):
    me = pool[0]
    reveal_all(repo, FJORD, pool[1 : 1 + MIN_GROUP])
    assert candidate_jobs(repo, me).model_dump(mode="json") == ok(
        client.get(f"/candidates/{me}/jobs")
    )
