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
    MAX_AXES,
    MAX_TIPS,
    RARE_SHARE,
    Group,
    candidate_jobs,
    compare_group,
    group_profiles,
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


# Comparing with groups of the others on a job, and the group-size rule


def groups(jobs: dict, job: str) -> dict[str, dict]:
    return {g["group"]: g for g in outcome(jobs, job)["groups"]}


def test_a_group_shows_only_once_it_has_five_others(client, repo, pool):
    me, *others = pool
    reveal_all(repo, FJORD, others[: MIN_GROUP - 1])
    assert groups(ok(client.get(f"/candidates/{me}/jobs")), FJORD) == {}

    reveal_all(repo, FJORD, [others[MIN_GROUP - 1]])
    found = groups(ok(client.get(f"/candidates/{me}/jobs")), FJORD)
    assert list(found) == [Group.REVEALED]
    # A job nobody was revealed on shows no group.
    assert groups(ok(client.get(f"/candidates/{me}/jobs")), LYNFJORD) == {}


def test_the_groups_overlap_and_ignore_the_candidates_own_stage(client, repo, pool):
    me, *others = pool
    shown = others[: MIN_GROUP + 2]
    reveal_all(repo, FJORD, [*shown, me])
    for name in shown[:MIN_GROUP]:
        request_application(repo, FJORD, repo.profile(name).id)
    for name in shown[: MIN_GROUP - 1]:
        answer(repo, name, FJORD, "applied", letter="Yes.")
    found = groups(ok(client.get(f"/candidates/{me}/jobs")), FJORD)
    # Revealed themselves, they still see both groups; four applied is too few.
    assert list(found) == [Group.REVEALED, Group.REQUESTED]

    answer(repo, shown[MIN_GROUP - 1], FJORD, "applied", letter="Yes.")
    profiles = group_profiles(repo, FJORD, me)
    assert len(profiles[Group.REVEALED]) == MIN_GROUP + 2
    assert len(profiles[Group.REQUESTED]) == MIN_GROUP
    assert len(profiles[Group.APPLIED]) == MIN_GROUP
    found = groups(ok(client.get(f"/candidates/{me}/jobs")), FJORD)
    assert list(found) == [Group.REVEALED, Group.REQUESTED, Group.APPLIED]


def test_a_decline_counts_as_asked_but_not_applied(client, repo, pool):
    me, *others = pool
    shown = others[:MIN_GROUP]
    reveal_all(repo, FJORD, shown)
    for name in shown:
        request_application(repo, FJORD, repo.profile(name).id)
        answer(repo, name, FJORD, "declined")
    profiles = group_profiles(repo, FJORD, me)
    assert len(profiles[Group.REQUESTED]) == MIN_GROUP
    assert profiles[Group.APPLIED] == []


def test_copies_of_the_demo_never_count_in_a_group(client, repo, pool):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    copies = [approved_john(client) for _ in range(MIN_GROUP)]
    for c in copies:
        ok(client.put(f"/candidates/{c}/connections/{FJORD}"))
    reveal_all(repo, FJORD, copies)
    assert all(not v for v in group_profiles(repo, FJORD, john).values())
    assert groups(ok(client.get(f"/candidates/{john}/jobs")), FJORD) == {}


def test_johns_comparison_matches_a_calculation_by_hand(client, repo, pool):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    shown = pool[:7]
    reveal_all(repo, FJORD, shown)
    found = groups(ok(client.get(f"/candidates/{john}/jobs")), FJORD)[Group.REVEALED]

    # Worked out again by hand from the pool's own levels.
    taxonomy = default_taxonomy()
    listed = [
        {taxonomy.canonical(s.name): s.self_level for s in repo.profile(n).skills}
        for n in shown
    ]
    skills = {s for x in listed for s in x}
    count = {s: sum(s in x for x in listed) for s in skills}
    rated = {s: [int(x[s]) for x in listed if x.get(s) is not None] for s in skills}
    medians = {s: median(v) for s, v in rated.items() if len(v) >= MIN_GROUP}
    common = {s for s in skills if count[s] >= COMMON_SHARE * len(shown)}
    own = {taxonomy.canonical(s.name): s.self_level for s in repo.profile(john).skills}
    implied = set().union(*(taxonomy.implied(s) for s in own))

    axes = [s["skill"] for s in found["skills"]]
    assert 3 <= len(axes) <= MAX_AXES and set(axes) <= medians.keys()
    assert [count[s] for s in axes] == sorted((count[s] for s in axes), reverse=True)
    for s in found["skills"]:
        assert s["median"] == medians[s["skill"]]
        assert s["own_level"] == own.get(s["skill"])

    higher = {s for s in own if own[s] and s in medians and own[s] > medians[s]}
    rare = {s for s in own if count.get(s, 0) <= RARE_SHARE * len(shown)}
    missing = {s for s in common if s not in own and s not in implied}
    lower = {s for s in common if own.get(s) and s in medians and own[s] < medians[s]}
    for key, expected in [
        ("higher", higher),
        ("rare", rare),
        ("missing", missing),
        ("lower", lower),
    ]:
        assert set(found[key]) <= expected, key
        assert len(found[key]) == min(len(expected), MAX_TIPS), key
    # The pool and John differ, so there is something on each side.
    assert found["higher"] or found["rare"]
    assert found["missing"] or found["lower"]


def own_levels(levels: dict[str, int | None]) -> Profile:
    return Profile(
        skills=[
            Skill(name=k, self_level=SkillLevel(v) if v else None)
            for k, v in levels.items()
        ]
    )


def compared(me: Profile, others: list[Profile]):
    return compare_group(me, Group.REVEALED, others, default_taxonomy())


def test_a_level_is_compared_only_where_five_of_the_group_rated_it():
    me = own_levels({"python": 1, "sql": 5})
    # Five list both; all five rate python, only four rate sql.
    others = [own_levels({"python": 4, "sql": 4}) for _ in range(4)]
    others.append(own_levels({"python": 4, "sql": None}))
    found = compared(me, others)
    assert found.lower == ["python"] and found.higher == []
    assert [s.skill for s in found.skills] == ["python"]
    assert found.missing == [] and found.rare == []
    assert compared(me, others[:4]) is None


def test_higher_and_rare_are_where_the_candidate_stands_out():
    me = own_levels({"python": 5, "sql": 4, "kafka": 2, "rust": None})
    others = [own_levels({"python": 3, "sql": 3}) for _ in range(5)]
    others[0] = own_levels({"python": 3, "sql": 3, "kafka": 4})
    found = compared(me, others)
    # Furthest above the median first; rare by own level, unrated last.
    assert found.higher == ["python", "sql"]
    assert found.rare == ["kafka", "rust"]
    assert found.lower == [] and found.missing == []
    others[1] = own_levels({"python": 3, "sql": 3, "kafka": 4})
    assert compared(me, others).rare == ["rust"]


def test_common_means_at_least_half_of_the_group():
    me = own_levels({"python": 3})
    others = [own_levels({"python": 3, "kafka": 3}) for _ in range(3)]
    others += [own_levels({"python": 3, "dbt": 3}) for _ in range(3)]
    others.append(own_levels({"python": 3, "terraform": 3}))
    found = compared(me, others)
    # 3 of 7 is under half; and the same level is neither higher nor lower.
    assert found.missing == [] and found.lower == [] and found.higher == []
    others.append(own_levels({"python": 3, "kafka": 2}))
    assert compared(me, others).missing == ["kafka"]


def test_the_chart_has_the_skills_the_group_lists_most():
    names = [f"skill {i}" for i in range(MAX_AXES + 2)]
    me = own_levels({names[0]: 2})
    # The first skill is listed by all six, the rest by five.
    others = [own_levels(dict.fromkeys(names, 3)) for _ in range(5)]
    others.append(own_levels({names[0]: 3}))
    found = compared(me, others)
    axes = [s.skill for s in found.skills]
    assert len(axes) == MAX_AXES and axes[0] == names[0]
    assert found.skills[0].own_level == 2 and found.skills[0].median == 3
    assert all(s.own_level is None for s in found.skills[1:])


# Nothing hidden, nothing about one other candidate


def test_no_assessment_rubric_or_other_candidate_reaches_the_jobs(client, repo, pool):
    john = approved_john(client)
    ok(client.put(f"/candidates/{john}/connections/{FJORD}"))
    shown = pool[:6]
    reveal_all(repo, FJORD, shown)
    before = ok(client.get(f"/candidates/{john}/jobs"))
    assert outcome(before, FJORD)["groups"]

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
    assert [j["groups"] for j in after["jobs"]] == [j["groups"] for j in before["jobs"]]
    assert after["revealed_rate"] == before["revealed_rate"]


def test_the_library_matches_the_route(client, repo, pool):
    me = pool[0]
    reveal_all(repo, FJORD, pool[1 : 1 + MIN_GROUP])
    assert candidate_jobs(repo, me).model_dump(mode="json") == ok(
        client.get(f"/candidates/{me}/jobs")
    )
