"""The candidate's dashboard: their own profile in overview, without the assessment.

Runs on John Doe's demo, with the synthetic pool (`tests/fixtures/pool`) as the
candidates he is compared with and the demo jobs on the board for tips. Everything
replays recordings or is plain code: no model is called.
"""

import json
import re
from datetime import datetime

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.dashboard import MIN_GROUP, compare, dashboard
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.evaluation.pool import load_pool
from unapply.schemas import (
    ClaimSupport,
    SkillCategory,
    SkillEstimate,
    SkillLevel,
    SourceKind,
)
from unapply.taxonomy import default_taxonomy

POOL_SIZE = 12
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


def approved_john(client) -> str:
    name = ok(client.post("/demos/candidate"), 201)["name"]
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    return name


def skills_of(d: dict) -> dict[str, dict]:
    return {s["name"]: s for a in d["areas"] for s in a["skills"]}


# The group-size rule


def test_fewer_than_five_levels_are_never_compared():
    four = [SkillLevel.WORKING] * (MIN_GROUP - 1)
    assert compare(four) is None
    c = compare([*four, SkillLevel.EXPERT])
    assert c is not None
    assert c.candidates == MIN_GROUP
    assert c.levels == [0, 0, MIN_GROUP - 1, 0, 1]
    assert c.median == 3.0


def test_the_median_of_an_even_count_falls_between_two_levels():
    c = compare([SkillLevel(v) for v in (1, 2, 3, 4, 4, 5)])
    assert c.median == 3.5 and sum(c.levels) == 6


# John's dashboard


def test_johns_skills_by_area_with_his_levels_and_his_quotes(client, repo):
    name = approved_john(client)
    d = ok(client.get(f"/candidates/{name}/dashboard"))
    profile = repo.profile(name)
    assert d["approved"] is True
    assert d["skills"] == len(profile.skills)
    assert d["rated"] == sum(s.self_level is not None for s in profile.skills)
    assert d["documents"] + d["statements"] == len(profile.evidence)

    taxonomy = default_taxonomy()
    order = [a["category"] for a in d["areas"]]
    assert order == [c for c in [*SkillCategory, None] if c in order]
    shown = skills_of(d)
    assert set(shown) == {s.name for s in profile.skills}
    kinds = {s.id: s.kind for s in profile.sources}
    source = {e.id: kinds[e.source_id] for e in profile.evidence}
    for a in d["areas"]:
        levels = [s["self_level"] or 0 for s in a["skills"]]
        assert levels == sorted(levels, reverse=True)
        for s in a["skills"]:
            skill = profile.skill(s["name"])
            known = taxonomy.get(s["name"])
            assert a["category"] == (
                known.category if known and known.category else skill.category
            )
            assert s["self_level"] == skill.self_level
            statements = [
                i for i in skill.evidence_ids if source[i] == SourceKind.INTERVIEW
            ]
            assert s["statements"] == len(statements)
            assert s["documents"] == len(skill.evidence_ids) - len(statements)


def test_without_five_others_nothing_is_compared(client):
    name = approved_john(client)
    d = ok(client.get(f"/candidates/{name}/dashboard"))
    assert d["compared_with"] == 0 and d["min_group"] == MIN_GROUP
    assert all(s["comparison"] is None for s in skills_of(d).values())


def test_john_is_compared_with_the_pool_in_groups_of_five_or_more(client, repo):
    ok(client.post("/demos/board"), 201)
    name = approved_john(client)
    # Another copy of the demo is John again, so it never counts as someone else.
    approved_john(client)
    d = ok(client.get(f"/candidates/{name}/dashboard"))
    assert d["compared_with"] == POOL_SIZE

    pool = [p.profile for p in load_pool().candidates.values()]
    compared = 0
    for s in skills_of(d).values():
        levels = [
            int(x.self_level)
            for p in pool
            for x in p.skills
            if x.name == s["name"] and x.self_level is not None
        ]
        if len(levels) < MIN_GROUP:
            assert s["comparison"] is None, s["name"]
            continue
        compared += 1
        c = s["comparison"]
        assert c["candidates"] == len(levels)
        assert c["levels"] == [levels.count(v) for v in range(1, 6)]
    # Some of John's skills are compared and some are too rare in the pool.
    assert compared >= 3
    assert any(s["comparison"] is None for s in skills_of(d).values())


def test_a_real_candidate_is_never_compared_with_the_pool(client, repo):
    ok(client.post("/demos/board"), 201)
    pool = list(load_pool().candidates.values())
    repo.create_candidate("jane")
    repo.save_profile("jane", pool[0].profile, "reviewed")
    assert dashboard(repo, "jane").compared_with == 0

    # Four real candidates are too few; drafts never count.
    for i, p in enumerate(pool[1:5]):
        repo.create_candidate(f"real-{i}")
        repo.save_profile(f"real-{i}", p.profile, "reviewed")
    draft = pool[5].profile.model_copy(update={"approved_by_candidate_at": None})
    repo.create_candidate("real-draft")
    repo.save_profile("real-draft", draft, "extracted")
    assert dashboard(repo, "jane").compared_with == 0
    repo.create_candidate("real-4")
    repo.save_profile("real-4", pool[6].profile, "reviewed")
    d = dashboard(repo, "jane")
    assert d.compared_with == MIN_GROUP
    assert any(s.comparison for a in d.areas for s in a.skills)


# Tips


def test_tips_name_skills_from_the_board_and_the_taxonomy(client, repo):
    name = approved_john(client)
    before = ok(client.get(f"/candidates/{name}/dashboard"))
    assert before["in_demand"] == []  # No jobs on the board yet.

    jobs = ok(client.post("/demos/board"), 201)["jobs"]
    d = ok(client.get(f"/candidates/{name}/dashboard"))
    own = set(skills_of(d))
    taxonomy = default_taxonomy()

    following = {f["skill"]: f["because"] for f in d["following"]}
    assert following
    for skill, because in following.items():
        assert skill not in own
        assert because and set(because) <= own
        assert all(skill in taxonomy.implied(b) for b in because)
    for skill in own:
        assert taxonomy.implied(skill) - own <= set(following)

    asked = {}
    for job in jobs:
        for c in repo.job(job).rubric.criteria:
            if c.skill:
                skill = taxonomy.canonical(c.skill)
                asked.setdefault(skill, set()).add(job)
    assert 0 < len(d["in_demand"]) <= 5
    counts = [len(asked[s]) for s in d["in_demand"]]
    assert counts == sorted(counts, reverse=True)
    for skill in d["in_demand"]:
        assert skill not in own and skill not in following
    # The most asked-for skill John lacks is among the tips.
    missing = {s: len(j) for s, j in asked.items() if s not in own | set(following)}
    assert max(missing.values()) == counts[0]

    # Tips are skills only: no job named, nothing from a rubric.
    text = json.dumps(d)
    assert not [j for j in jobs if j in text]
    assert not HIDDEN.search(text)


# Nothing from the assessment


def test_no_assessment_word_or_estimate_reaches_the_dashboard(client, repo):
    ok(client.post("/demos/board"), 201)
    name = approved_john(client)
    ok(client.post(f"/candidates/{name}/questions"))
    answers = ok(client.get(f"/candidates/{name}/demo/answers"))
    ok(client.post(f"/candidates/{name}/answers", json=answers))
    profile = repo.profile(name)
    assert any(s.estimate for s in profile.skills) and profile.claim_support

    d = ok(client.get(f"/candidates/{name}/dashboard"))
    assert d["statements"] > 0
    text = json.dumps(d)
    assert not HIDDEN.search(text), HIDDEN.search(text)
    for s in profile.skills:
        if s.estimate:
            assert s.estimate.rationale not in text

    # Changing every estimate and the claim support, for John and the pool, changes
    # nothing on his dashboard: none of it is used.
    def reassessed(p):
        return p.model_copy(
            update={
                "skills": [
                    s.model_copy(
                        update={
                            "estimate": SkillEstimate(
                                level=SkillLevel.AWARE,
                                confidence=0.01,
                                rationale="changed",
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

    for other in [name, *(n for n in repo.candidate_names() if n.startswith("pool-"))]:
        repo.save_profile(other, reassessed(repo.profile(other)), "assessed")
    assert ok(client.get(f"/candidates/{name}/dashboard")) == d


def test_no_other_candidate_can_be_identified(client, repo):
    ok(client.post("/demos/board"), 201)
    name = approved_john(client)
    text = json.dumps(ok(client.get(f"/candidates/{name}/dashboard")))
    secrets = []
    for other in repo.candidate_names():
        if other.startswith("pool-"):
            p = repo.profile(other)
            secrets.append(other)
            secrets += [e.quote for e in p.evidence if len(e.quote) > 12]
            secrets += [x.organisation for x in p.experiences if x.organisation]
            secrets.append(p.headline)
    assert len(secrets) > 50
    assert not [s for s in secrets if s and s in text]
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text)


def test_a_candidate_without_a_profile_or_no_candidate_at_all(client):
    ok(client.post("/candidates", json={"name": "empty"}), 201)
    assert client.get("/candidates/empty/dashboard").status_code == 409
    assert client.get("/candidates/nobody/dashboard").status_code == 404
