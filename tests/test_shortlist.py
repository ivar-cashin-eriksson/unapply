"""The employer's shortlist: anonymised candidates, both levels, reveals and requests.

Everything runs on the synthetic pool for Fjord Grocery (`tests/fixtures/pool`),
which the shortlist demo stores in the database; both scorers replay recordings.
"""

import json
import re
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import anthropic
import pytest
from fastapi.testclient import TestClient

import unapply.matching.filters as filters
from unapply.api.app import create_app
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.evaluation.pool import (
    DEMO_PREFIX,
    evaluate_pool,
    load_pool,
    match_recording,
    store_pool,
)
from unapply.matching import own_and_estimated
from unapply.matching.audit import AuditKind, check_ranking
from unapply.matching.shortlist import (
    ADJECTIVES,
    ALIASES,
    NOUNS,
    Intent,
    IntentKind,
    alias,
    anonymous_candidate,
    identities,
    identity,
    rubric_skills,
    skill_levels,
)
from unapply.schemas import (
    Criterion,
    CriterionKind,
    Evidence,
    Experience,
    Profile,
    Rubric,
    Skill,
    SkillEstimate,
    SkillLevel,
    Source,
    SourceKind,
)

POOL = Path(__file__).parent / "fixtures" / "pool"
# The pool's candidates who fail a hard filter: scored, but ranked after the rest.
FAILING = {"clara-jensen", "emil-dahl", "priya-raman"}


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the API created an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


@pytest.fixture(scope="module")
def pool():
    return load_pool(POOL)


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


def folder_of(repo, profile_id: str) -> str:
    """The pool folder of a ranked candidate, from their profile id."""
    return repo.candidate_of(UUID(profile_id)).removeprefix(DEMO_PREFIX)


def shortlist_demo(client) -> str:
    return ok(client.post("/demos/shortlist"), 201)["name"]


# The anonymised view


def profile_with(skills: list[Skill], **fields) -> Profile:
    cv = Source(kind=SourceKind.CV, uri="jane-cv.md")
    interview = Source(kind=SourceKind.INTERVIEW, uri="interview")
    evidence = [
        Evidence(source_id=cv.id, quote="Wrote it with Jane Roe, jane@example.com"),
        Evidence(source_id=interview.id, quote="I use dbt every day, see @janeroe"),
    ]
    return Profile(
        headline="Analyst, see github.com/janeroe",
        sources=[cv, interview],
        evidence=evidence,
        experiences=[
            Experience(
                title="Analyst",
                organisation="Roe Consulting",
                start=date(2020, 1, 1),
                summary="Call +45 12 34 56 78 for references.",
            )
        ],
        skills=skills,
        **fields,
    )


def estimate(level: int, confidence: float = 0.8) -> SkillEstimate:
    return SkillEstimate(
        level=SkillLevel(level), confidence=confidence, rationale="r", model="m"
    )


def rubric(*skills: str | None) -> Rubric:
    return Rubric(
        criteria=[
            Criterion(kind=CriterionKind.MUST_HAVE, description=f"{s}", skill=s)
            for s in skills
        ]
    )


ALIAS = r"[A-Z][a-z]+ [A-Z][a-z]+"

# Common first names in Denmark, the EU and elsewhere, and the words in the pool
# candidates' names: no alias word may be one of them.
FIRST_NAMES = """
amber robin jade ruby rose violet hazel olive ivy lily daisy iris fern sage basil
coral misty sunny rocky sandy stormy willow maple autumn summer skye river jasper
indigo scarlett ginger honey cherry crystal pearl opal goldie sterling hunter
mason crane wren jay finch dove raven fox wolf bear lynn sky storm dawn
ida emma clara freja sofie astrid nadia priya anna maria mia lucas noah oliver
emil lars jonas henrik mikkel william oscar carl victor august
""".split()


def test_alias_is_two_words_and_stable_for_a_profile_and_job():
    profile_id, job_id = uuid4(), uuid4()
    known = identity(profile_id, job_id)
    assert alias(profile_id, job_id) == alias(profile_id, job_id) == known.alias
    assert re.fullmatch(ALIAS, known.alias)
    adjective, noun = known.alias.split()
    assert adjective in ADJECTIVES and noun in NOUNS
    assert identity(UUID(str(profile_id)), UUID(str(job_id))) == known
    # Known ids always get the same alias, on any machine and run.
    fixed = UUID("12345678-1234-5678-1234-567812345678")
    job = UUID("87654321-4321-8765-4321-876543218765")
    assert identity(fixed, job) == identity(fixed, job)
    assert 0 <= identity(fixed, job).avatar < ALIASES


def test_a_candidate_is_known_by_different_aliases_on_different_jobs():
    profile_id = uuid4()
    jobs = [uuid4() for _ in range(50)]
    seen = {identity(profile_id, j).avatar for j in jobs}
    # 50 jobs from 1920 aliases: nearly all different, never all the same.
    assert len(seen) > 40
    # The job and profile ids aren't interchangeable.
    a, b = uuid4(), uuid4()
    assert identity(a, b) != identity(b, a)
    # Nor does one candidate's order on a job carry over to another.
    ids = [uuid4() for _ in range(30)]
    one, two = identities(ids, jobs[0]), identities(ids, jobs[1])
    assert sum(one[i] == two[i] for i in ids) < 5


def test_every_alias_number_names_a_different_alias():
    job_id = uuid4()
    for profile_id in (uuid4() for _ in range(300)):
        known = identity(profile_id, job_id)
        adjective, noun = known.alias.split()
        assert ADJECTIVES.index(adjective) * len(NOUNS) + NOUNS.index(noun) == (
            known.avatar
        )
    assert (
        ALIASES
        == len(ADJECTIVES) * len(NOUNS)
        == len(set(ADJECTIVES)) * len(set(NOUNS))
    )


def test_alias_words_are_never_person_names():
    words = {w.lower() for w in (*ADJECTIVES, *NOUNS)}
    pool = {part for d in POOL.iterdir() if d.is_dir() for part in d.name.split("-")}
    assert not words & set(FIRST_NAMES)
    assert not words & pool
    for w in words:
        assert re.fullmatch(r"[a-z]+", w), w


def test_identities_are_unique_within_a_job_and_independent_of_order():
    ids, job_id = [uuid4() for _ in range(400)], uuid4()
    known = identities(ids, job_id)
    assert len({k.alias for k in known.values()}) == len(ids)
    assert len({k.avatar for k in known.values()}) == len(ids)
    assert identities(reversed(ids), job_id) == known
    # Without clashes, a candidate keeps the alias their ids give on their own.
    assert identities(ids[:1], job_id) == {ids[0]: identity(ids[0], job_id)}


def test_a_clash_goes_to_the_candidate_with_the_lower_profile_id(monkeypatch):
    import unapply.matching.shortlist as shortlist

    low, high = sorted([uuid4(), uuid4()])
    monkeypatch.setattr(shortlist, "_index", lambda _id, _job: ALIASES - 1)
    known = identities([high, low], uuid4())
    assert known[low].avatar == ALIASES - 1
    assert known[high].avatar == 0
    assert known[low].alias != known[high].alias


def test_more_candidates_than_aliases_is_refused(monkeypatch):
    import unapply.matching.shortlist as shortlist

    monkeypatch.setattr(shortlist, "ALIASES", 2)
    with pytest.raises(ValueError, match="only 2 aliases"):
        identities([uuid4() for _ in range(3)], uuid4())


def test_rubric_skills_are_canonical_once_each_in_rubric_order():
    assert rubric_skills(rubric("SQL", None, "scikit learn", "sql", "python")) == [
        "sql",
        "scikit-learn",
        "python",
    ]
    assert rubric_skills(rubric(None)) == []


def test_skill_levels_come_from_the_skill_itself_then_a_related_one():
    sql = Skill(name="sql", self_level=SkillLevel(4), estimate=estimate(3, 0.6))
    dbt = Skill(name="dbt", self_level=SkillLevel(5), estimate=estimate(4))
    postgres = Skill(name="postgresql", self_level=SkillLevel(2))

    direct = skill_levels(profile_with([dbt, sql]), "SQL")
    assert (direct.skill, direct.own_level, direct.estimated_level) == ("sql", 4, 3)
    assert (direct.confidence, direct.via) == (0.6, None)

    # Without SQL itself, the related skill with the highest level counts.
    related = skill_levels(profile_with([postgres, dbt]), "sql")
    assert (related.own_level, related.estimated_level, related.via) == (5, 4, "dbt")

    none = skill_levels(profile_with([dbt]), "deep learning")
    assert none.model_dump() == {
        "skill": "deep learning",
        "own_level": None,
        "estimated_level": None,
        "confidence": None,
        "via": None,
    }
    # An own level without an estimate yet.
    own = skill_levels(profile_with([postgres]), "postgresql")
    assert (own.own_level, own.estimated_level, own.confidence) == (2, None, None)


def test_the_anonymous_candidate_has_no_names_contacts_or_claim_support():
    skills = [Skill(name="python", self_level=SkillLevel(4), estimate=estimate(3))]
    profile = profile_with(skills)
    known_as = identity(profile.id, uuid4())
    seen = anonymous_candidate(
        profile, rubric("python", "sql"), ["Jane", "Roe"], known_as=known_as
    )
    text = seen.model_dump_json()
    for leak in ("Jane", "jane@", "janeroe", "12 34 56 78", "jane-cv.md", "claim"):
        assert leak.lower() not in text.lower(), leak
    assert (seen.alias, seen.avatar) == (known_as.alias, known_as.avatar)
    assert seen.headline == "Analyst, see [redacted]"
    assert seen.experiences[0].organisation == "[redacted] Consulting"
    assert seen.experiences[0].start == date(2020, 1, 1)
    assert [e.source for e in seen.evidence] == ["cv", "candidate statement"]
    assert [e.id for e in seen.evidence] == [e.id for e in profile.evidence]
    assert [(s.skill, s.own_level, s.estimated_level) for s in seen.skills] == [
        ("python", 4, 3),
        ("sql", None, None),
    ]


# Intents in the database


def test_intents_are_recorded_once_and_read_back_in_order(repo):
    job_id, a, b = uuid4(), uuid4(), uuid4()
    first, new = repo.record_intent(
        Intent(job_id=job_id, profile_id=a, kind=IntentKind.REVEAL)
    )
    assert new and first.id is not None
    again, new = repo.record_intent(
        Intent(job_id=job_id, profile_id=a, kind=IntentKind.REVEAL)
    )
    assert not new and again == first
    request, new = repo.record_intent(
        Intent(job_id=job_id, profile_id=a, kind=IntentKind.REQUEST_APPLICATION)
    )
    assert new
    repo.record_intent(Intent(job_id=job_id, profile_id=b, kind=IntentKind.REVEAL))
    repo.record_intent(Intent(job_id=uuid4(), profile_id=a, kind=IntentKind.REVEAL))

    log = repo.intents(job_id)
    assert [(i.profile_id, i.kind) for i in log] == [
        (a, IntentKind.REVEAL),
        (a, IntentKind.REQUEST_APPLICATION),
        (b, IntentKind.REVEAL),
    ]
    assert [i.profile_id for i in repo.intents(job_id, IntentKind.REVEAL)] == [a, b]
    with pytest.raises(ValueError, match="already stored"):
        repo.record_intent(first)


# Storing the pool


def test_store_pool_stores_the_job_and_each_candidate_once(repo, pool):
    names = store_pool(repo, pool, "shortlist")
    assert names == sorted(DEMO_PREFIX + n for n in pool.candidates)
    job = repo.job("shortlist")
    assert job.rubric.approved_at is not None
    assert job.rubric == pool.job.rubric
    settings = repo.job_settings("shortlist")
    assert settings["demo"] and settings["today"] == "2026-11-26"
    for folder, candidate in pool.candidates.items():
        name = DEMO_PREFIX + folder
        assert repo.settings(name) == {"demo": True, "pool": folder}
        assert repo.profile(name) == candidate.profile

    # A second pool job ranks the same people: the candidates are kept.
    profiles = {n: repo.profile(n).id for n in names}
    assert store_pool(repo, load_pool(POOL), "shortlist-2") == names
    assert {n: repo.profile(n).id for n in names} == profiles
    assert repo.job("shortlist-2").id != job.id

    with pytest.raises(ValueError, match="already exists"):
        store_pool(repo, pool, "shortlist")


def test_store_pool_refuses_a_name_taken_by_someone_else(repo, pool):
    repo.create_candidate(DEMO_PREFIX + "astrid-holm")
    with pytest.raises(ValueError, match="not from the pool"):
        store_pool(repo, pool, "shortlist")


def test_match_recordings_are_found_without_loading_the_pool(pool):
    for name in pool.candidates:
        assert match_recording(name, POOL) == pool.match_recording(name)


# The API


def test_the_shortlist_demo_ranks_the_pool_as_the_evaluation_does(client, repo, pool):
    job = shortlist_demo(client)
    summary = ok(client.get(f"/jobs/{job}"))
    assert summary["demo"] and summary["approved"]
    # Pool candidates aren't candidate journeys, so they aren't listed.
    assert ok(client.get("/candidates")) == []

    for scorer in ("baseline", "llm"):
        ok(client.post(f"/jobs/{job}/match?scorer={scorer}"))
        shortlist = ok(client.get(f"/jobs/{job}/shortlist?scorer={scorer}"))
        ranking = shortlist["ranking"]["candidates"]
        assert len(ranking) == len(shortlist["candidates"]) == 12
        # The same ranking as `unapply evaluate`, which works in memory.
        ranks = {folder_of(repo, c["profile_id"]): c["rank"] for c in ranking}
        evaluation = evaluate_pool(pool, scorer)
        assert ranks == {n: r.rank for n, r in evaluation.ranking}, scorer
        failed = {
            folder_of(repo, c["profile_id"])
            for c in ranking
            if not c["passed_hard_filters"]
        }
        assert failed == FAILING
        # In ranking order, each with the rubric's skills.
        assert [c["profile_id"] for c in shortlist["candidates"]] == [
            c["profile_id"] for c in ranking
        ]
        assert shortlist["skills"] == rubric_skills(pool.job.rubric)
        assert shortlist["rubric"]["version"] == shortlist["ranking"]["rubric_version"]
        assert [c["id"] for c in shortlist["rubric"]["criteria"]] == [
            str(c.id) for c in repo.job(job).rubric.criteria
        ]
        for c in shortlist["candidates"]:
            assert [s["skill"] for s in c["skills"]] == shortlist["skills"]
        # No quotes before a reveal; each cited one is the candidate's own.
        for r, c in zip(ranking, shortlist["candidates"], strict=True):
            assert c["evidence"] == []
            assert c["progress"]["stage"] == "connected" and c["contact"] is None
            quotes = {
                str(e.id) for e in repo.profile_by_id(UUID(c["profile_id"])).evidence
            }
            for score in r["criterion_scores"]:
                assert set(score["evidence_ids"]) <= quotes
    assert shortlist["intents"] == []
    assert shortlist["reveal_quota"] == 10


def test_the_shortlist_never_names_a_candidate(client, repo):
    job = shortlist_demo(client)
    ok(client.post(f"/jobs/{job}/match"))
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    for c in shortlist["candidates"]:
        text = json.dumps(
            [c["headline"], c["experiences"], [e["quote"] for e in c["evidence"]]]
        )
        assert "@" not in text and "+45" not in text
        assert "example.com" not in text and ".md" not in text
        assert re.fullmatch(ALIAS, c["alias"])
    aliases = [c["alias"] for c in shortlist["candidates"]]
    assert len(set(aliases)) == len(aliases) == 12
    assert len({c["avatar"] for c in shortlist["candidates"]}) == 12
    ids = [UUID(c["profile_id"]) for c in shortlist["candidates"]]
    job_id = repo.job(job).id
    assert aliases == [identities(ids, job_id)[i].alias for i in ids]
    # The same aliases when the shortlist is read again, and with the other scorer.
    ok(client.post(f"/jobs/{job}/match?scorer=llm"))
    again = ok(client.get(f"/jobs/{job}/shortlist?scorer=llm"))
    assert {c["profile_id"]: c["alias"] for c in again["candidates"]} == {
        c["profile_id"]: c["alias"] for c in shortlist["candidates"]
    }
    whole = json.dumps(shortlist).lower()
    for folder in (POOL).iterdir():
        if folder.is_dir():
            for part in folder.name.split("-"):
                assert not re.search(rf"\b{part}\b", whole), folder.name


def test_the_same_candidates_have_other_aliases_on_another_job(client, repo):
    first, second = shortlist_demo(client), shortlist_demo(client)
    seen = []
    for job in (first, second):
        ok(client.post(f"/jobs/{job}/match"))
        shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
        seen.append(
            {
                c["profile_id"]: (c["alias"], c["avatar"])
                for c in shortlist["candidates"]
            }
        )
    # The pool is stored once, so both jobs rank the same 12 profiles.
    assert seen[0].keys() == seen[1].keys() and len(seen[0]) == 12
    assert sum(seen[0][pid] == seen[1][pid] for pid in seen[0]) < 3
    for one in seen:
        assert len({a for a, _ in one.values()}) == 12
        assert len({v for _, v in one.values()}) == 12


def test_the_shortlist_is_recorded_in_the_audit_log(client, repo):
    job = shortlist_demo(client)
    ok(client.post(f"/jobs/{job}/match"))
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    log = repo.audit_log(repo.job(job).id)
    entry = log[-1]
    assert entry.kind == AuditKind.RANKING
    assert [m["match"]["id"] for m in entry.payload["ranking"]] == [
        c["match_id"] for c in shortlist["ranking"]["candidates"]
    ]
    assert check_ranking(entry, log) == []


def test_shortlist_errors(client):
    assert client.get("/jobs/nothing/shortlist").status_code == 404
    ok(client.post("/demos/job"), 201)
    assert client.get("/jobs/fjord-grocery-demo/shortlist").status_code == 409
    job = shortlist_demo(client)
    assert ok(client.get(f"/jobs/{job}/shortlist"))["candidates"] == []
    assert client.get(f"/jobs/{job}/shortlist?version=7").status_code == 404
    assert client.get(f"/jobs/{job}/shortlist?scorer=magic").status_code == 422


def test_pool_candidates_make_no_model_calls(client):
    shortlist_demo(client)
    name = DEMO_PREFIX + "astrid-holm"
    response = client.post(f"/candidates/{name}/extract")
    assert response.status_code == 409
    assert "synthetic pool" in response.json()["detail"]
    assert client.post(f"/candidates/{name}/questions").status_code == 409
    # Their profile is there, as candidates see it.
    assert ok(client.get(f"/candidates/{name}/profile"))["approved_by_candidate_at"]


def test_the_early_intents_are_kept_as_history_on_the_shortlist(client, repo):
    job = shortlist_demo(client)
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    first = UUID(ranking[0]["profile_id"])
    repo.record_intent(Intent(job_id=repo.job(job).id, profile_id=first, kind="reveal"))
    intents = ok(client.get(f"/jobs/{job}/intents"))
    assert [(i["profile_id"], i["kind"]) for i in intents] == [(str(first), "reveal")]
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    assert shortlist["intents"] == intents
    # They revealed no one: the candidate is still anonymous, with no quotes.
    assert shortlist["candidates"][0]["contact"] is None
    assert shortlist["counts"]["revealed"] == 0
    # New intents can't be recorded: reveals go through their own route.
    response = client.post(
        f"/jobs/{job}/intents", json={"profile_id": str(first), "kind": "reveal"}
    )
    assert response.status_code == 405
    assert client.get("/jobs/nothing/intents").status_code == 404


def test_years_of_experience_count_to_the_pools_date(client, repo, monkeypatch):
    """Matching the demo gives the pool's results on any day, not only today."""
    job = shortlist_demo(client)

    # Years later, the too-junior candidate would have enough years.
    class Later(date):
        @classmethod
        def today(cls):
            return date(2030, 1, 1)

    monkeypatch.setattr(filters, "date", Later)
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    failed = {
        folder_of(repo, c["profile_id"])
        for c in ranking
        if not c["passed_hard_filters"]
    }
    assert failed == FAILING
    # The ranking shown works the filters out again, on the same date.
    shown = ok(client.get(f"/jobs/{job}/ranking"))["candidates"]
    junior = next(c for c in shown if folder_of(repo, c["profile_id"]) == "emil-dahl")
    (years,) = [
        f for f in junior["hard_filters"] if f["name"] == "min_years_experience"
    ]
    assert years["outcome"] == "fail"


# Own and estimated scores, and failed filters


def test_own_and_estimated_scores_tell_the_overclaimer_apart(pool):
    totals = {
        name: own_and_estimated(c.profile, pool.job.rubric)
        for name, c in pool.candidates.items()
    }
    own, estimated = totals["jonas-friis"]
    # Expert on his own word, a BI analyst on his evidence.
    assert own - estimated > 0.3
    # An honest candidate's two scores are close.
    own, estimated = totals["astrid-holm"]
    assert abs(own - estimated) < 0.1
    assert all(0 <= t <= 1 for pair in totals.values() for t in pair)


def test_the_shortlist_shows_both_scores_and_failed_candidates_last(client, repo):
    job = shortlist_demo(client)
    rubric = repo.job(job).rubric
    for scorer in ("baseline", "llm"):
        ok(client.post(f"/jobs/{job}/match?scorer={scorer}"))
        ranking = ok(client.get(f"/jobs/{job}/shortlist?scorer={scorer}"))["ranking"]
        candidates = ranking["candidates"]
        passed = [c["passed_hard_filters"] for c in candidates]
        # Everyone who passes, then everyone who fails: one divider.
        assert passed == [True] * 9 + [False] * 3, scorer
        for c in candidates:
            profile = repo.profile_by_id(UUID(c["profile_id"]))
            expected = own_and_estimated(profile, rubric)
            assert (c["own_total"], c["estimated_total"]) == expected
        for c in candidates[9:]:
            # Scored by the scorer too, with the failed filters named.
            assert c["total"] > 0 and c["criterion_scores"], scorer
            assert any(f["outcome"] == "fail" for f in c["hard_filters"])
        # Priya, outside the EU, scores above most who pass but ranks after them.
        priya = next(
            c for c in candidates if folder_of(repo, c["profile_id"]) == "priya-raman"
        )
        assert priya["total"] > candidates[8]["total"]
        assert priya["rank"] == 10
