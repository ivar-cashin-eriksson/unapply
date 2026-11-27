"""The job board: demo jobs, vacancies, listings, search, and connecting a profile.

The demo jobs (`tests/fixtures/jobs`, listed in `board.yaml`) are matched against
the synthetic pool (`tests/fixtures/pool`). Everything replays recordings or uses
the baseline scorer, so nothing here makes a paid call.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import anthropic
import pytest
import yaml
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.db.engine import database_url, init_db
from unapply.db.repository import NotFound, Repository
from unapply.evaluation.pool import (
    BOARD_PREFIX,
    DEFAULT_BOARD,
    DEMO_PREFIX,
    load_board,
    load_pool,
    store_board,
)
from unapply.jobs.board import (
    ConnectError,
    Listing,
    Seniority,
    connect,
    connected,
    listing,
    listings,
    search,
    seniority,
    withdraw,
)
from unapply.jobs.extract import extract_job
from unapply.llm import ReplayLLM
from unapply.matching import BaselineScorer, match_candidate, rank
from unapply.matching.audit import AuditKind
from unapply.schemas import Job, WorkMode

FIXTURES = Path(__file__).parent / "fixtures"
JOBS = FIXTURES / "jobs"
STAND_IN = "hand-written placeholder, not a model answer: re-record with --record"
# Words for rubric details, which never reach a candidate route.
RUBRIC_WORDS = ("criteria", "criterion", "weight", "min_level", "hard_filters")


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
def client(repo, tmp_path):
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


def board_demo(client) -> list[str]:
    return ok(client.post("/demos/board"), 201)["jobs"]


def assert_no_rubric(body) -> None:
    text = json.dumps(body).lower()
    assert not [w for w in RUBRIC_WORDS if w in text], text


# The demo jobs


def folders() -> list[str]:
    spec = yaml.safe_load(DEFAULT_BOARD.read_text(encoding="utf-8"))
    return [entry["folder"] for entry in spec["jobs"]]


def test_the_board_lists_eleven_jobs_each_with_its_files():
    assert len(folders()) == 11
    assert folders()[0] == "fjord_grocery"
    assert sorted(folders()) == sorted(
        p.name for p in JOBS.iterdir() if p.is_dir() and p.name != "__pycache__"
    )
    for folder in folders():
        for file in ("ad.md", "extraction.json", "README.md"):
            assert (JOBS / folder / file).is_file(), f"{folder}/{file}"


@pytest.mark.parametrize("folder", folders())
def test_every_quote_is_in_the_ad_and_nothing_is_dropped(folder):
    ad = (JOBS / folder / "ad.md").read_text(encoding="utf-8")
    result = extract_job(ad, ReplayLLM(JOBS / folder / "extraction.json"))
    assert result.dropped == []
    record = json.loads((JOBS / folder / "extraction.json").read_text("utf-8"))
    assert len(result.job.rubric.criteria) == len(record["answer"]["criteria"])
    for c in result.job.rubric.criteria:
        assert c.source_quote in " ".join(ad.split())
    must = [c for c in result.job.rubric.criteria if c.kind == "must_have"]
    assert must and len(must) < len(result.job.rubric.criteria)


def test_the_new_jobs_are_stand_ins_listed_to_record():
    listed = (Path(__file__).parents[1] / "docs" / "to-record.md").read_text(
        encoding="utf-8"
    )
    for folder in folders():
        record = json.loads((JOBS / folder / "extraction.json").read_text("utf-8"))
        if folder == "fjord_grocery":
            assert record["model"] == "claude-opus-5-5"  # A real recording.
            continue
        assert record["model"] == STAND_IN, folder
        assert f"tests/fixtures/jobs/{folder}/extraction.json" in listed


def test_the_jobs_vary(board):
    _, jobs = board
    filters = [j.job.rubric.hard_filters for j in jobs]
    assert {j.job.vacancies for j in jobs} == {1, 2, 3}
    assert {p for f in filters for p in f.required_work_permits} == {"EU", "IN"}
    assert {"Copenhagen", "Aarhus", "Berlin", "Bengaluru"} <= {
        p for f in filters for p in f.locations
    }
    assert {m for f in filters for m in f.work_modes} == set(WorkMode)
    assert {f.min_years_experience for f in filters} >= {None, 2, 3, 4, 5, 6}
    assert {seniority(j.job.title) for j in jobs} == {
        Seniority.JUNIOR,
        Seniority.MID,
        Seniority.SENIOR,
    }
    assert len({j.job.company for j in jobs}) == len(jobs)
    # Only Fjord Grocery has recorded LLM scorer answers for the pool.
    assert [j.folder for j in jobs if j.llm] == ["fjord_grocery"]


# Each job matched against the pool with the baseline


def ranked(pool, job: Job) -> list[tuple[str, bool]]:
    """The pool's candidates best first, with whether each passed the filters."""
    results = {
        name: match_candidate(c.profile, job, BaselineScorer(), pool.today)
        for name, c in pool.candidates.items()
    }
    names = {r.match.id: name for name, r in results.items()}
    return [
        (names[r.match.id], r.match.passed_hard_filters)
        for r in rank([r.match for r in results.values()], job.rubric)
    ]


# The best candidate who passes every hard filter, as each job's README says.
BEST = {
    "fjord_grocery": "astrid-holm",
    "lynfjord_power": "sofie-krag",
    "havnelys_logistics": "freja-nygaard",
    "ravnekaer_mobility": "nadia-kowal",
    "kornmod_foods": "clara-jensen",
    "tidevand_software": "clara-jensen",
    "kloevermark_supermarkets": "lars-winther",
    "oresund_academy": "ida-thorsen",
    "bogreol_online": "mikkel-lund",
    "smoerblomst_dairy": "astrid-holm",
}


def test_each_job_ranks_the_pool_sensibly(pool, board):
    _, jobs = board
    by_folder = {j.folder: ranked(pool, j.job) for j in jobs}
    for folder, best in BEST.items():
        assert by_folder[folder][0] == (best, True), folder
    # The frontend developer is last of those who pass wherever no job wants him.
    for folder in ("fjord_grocery", "lynfjord_power", "bogreol_online"):
        passing = [n for n, passed in by_folder[folder] if passed]
        assert passing[-1] == "henrik-mose", folder
    # Remote or elsewhere: only Clara, who wants remote work, passes.
    for folder in ("kornmod_foods", "tidevand_software"):
        assert [n for n, passed in by_folder[folder] if passed] == ["clara-jensen"]
    # Outside the EU nobody passes; Priya, who may work in India, is first.
    assert not any(passed for _, passed in by_folder["kaveri_retail"])
    assert by_folder["kaveri_retail"][0][0] == "priya-raman"
    # The junior roles take Emil, who is too junior for Fjord Grocery.
    for folder in ("havnelys_logistics", "smoerblomst_dairy"):
        assert ("emil-dahl", True) in by_folder[folder]
    assert ("emil-dahl", False) in by_folder["fjord_grocery"]
    top3 = [n for n, _ in by_folder["smoerblomst_dairy"][:3]]
    assert "emil-dahl" in top3
    # Each pool candidate who passes some job's filters fails another's.
    for name in pool.candidates:
        outcomes = {passed for r in by_folder.values() for n, passed in r if n == name}
        assert False in outcomes, name


# Vacancies


def test_vacancies_default_to_one_and_round_trip(repo, board):
    _, jobs = board
    job = jobs[1].job
    assert job.vacancies == 2
    assert Job(company="A", title="B", ad_text="C").vacancies == 1
    with pytest.raises(ValueError):
        Job(company="A", title="B", ad_text="C", vacancies=0)
    repo.create_job("lynfjord")
    repo.save_job("lynfjord", job, "rubric")
    assert repo.job("lynfjord") == job


def test_the_employer_sets_vacancies_with_the_ad(client):
    name = ok(client.post("/demos/job"), 201)["name"]
    summary = ok(client.get(f"/jobs/{name}"))
    assert summary["ad"]["vacancies"] == 1
    # A demo's ad is fixed, but its vacancies can change.
    changed = {**summary["ad"], "vacancies": 4}
    assert ok(client.put(f"/jobs/{name}/ad", json=changed))["ad"]["vacancies"] == 4
    other = {**changed, "ad": changed["ad"] + " More."}
    assert client.put(f"/jobs/{name}/ad", json=other).status_code == 409
    job = ok(client.post(f"/jobs/{name}/extract"))["job"]
    assert job["vacancies"] == 4
    ok(client.put(f"/jobs/{name}/ad", json={**changed, "vacancies": 2}))
    assert ok(client.get(f"/jobs/{name}"))["ad"]["vacancies"] == 2


# Listings and search


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Junior Data Analyst", Seniority.JUNIOR),
        ("Graduate Engineer", Seniority.JUNIOR),
        ("Data Scientist", Seniority.MID),
        ("Category Manager, Fresh Produce", Seniority.MID),
        ("Senior Machine Learning Engineer", Seniority.SENIOR),
        ("Sr. Backend Developer", Seniority.SENIOR),
        ("Lead Data Scientist", Seniority.LEAD),
        ("Head of Data", Seniority.LEAD),
        ("Seniority Analyst", Seniority.MID),  # A word, not a level.
    ],
)
def test_seniority_comes_from_the_title(title, level):
    assert seniority(title) == level


@pytest.fixture
def found(board) -> list[Listing]:
    _, jobs = board
    now = datetime(2026, 11, 27, 9)
    return [
        listing(j.name, j.job.model_copy(update={"created_at": now - timedelta(i)}))
        for i, j in enumerate(jobs)
    ]


def test_a_listing_has_the_ad_and_vacancies_but_not_the_rubric(found):
    fjord = found[0]
    assert fjord.name == BOARD_PREFIX + "fjord-grocery"
    assert fjord.company == "Fjord Grocery ApS"
    assert fjord.ad.startswith("# Senior Data Scientist")
    assert (fjord.vacancies, fjord.seniority) == (1, Seniority.SENIOR)
    assert (fjord.locations, fjord.work_modes) == (["Copenhagen"], [WorkMode.HYBRID])
    assert_no_rubric(fjord.model_dump(mode="json"))


def test_search_by_words_location_work_mode_and_seniority(found):
    def titles(**kwargs) -> list[str]:
        return [x.company for x in search(found, **kwargs).listings]

    everything = search(found)
    assert [x.name for x in everything.listings] == [x.name for x in found]
    assert everything.total == 11
    assert everything.locations == ["Aarhus", "Bengaluru", "Berlin", "Copenhagen"]
    assert everything.work_modes == list(WorkMode)
    assert everything.seniorities == [Seniority.JUNIOR, Seniority.MID, Seniority.SENIOR]

    # Every word must be found, in any case, in the title, company or ad.
    assert titles(query="FORECASTING energy") == ["Lynfjord Power A/S"]
    assert titles(query="dbt snowflake") == ["Fjord Grocery ApS", "Kornmod Foods A/S"]
    assert titles(query="Mejeri") == ["Smørblomst Mejeri"]
    assert titles(query="cheese fridays") == ["Smørblomst Mejeri"]
    assert titles(query="nothing like this") == []
    # A place also finds jobs offering remote work.
    assert titles(location="Aarhus") == ["Kornmod Foods A/S", "Tidevand Software GmbH"]
    assert titles(location="bengaluru") == [
        "Kornmod Foods A/S",
        "Tidevand Software GmbH",
        "Kaveri Retail Pvt Ltd",
    ]
    assert len(titles(location="Copenhagen")) == 10
    assert titles(work_mode=WorkMode.REMOTE) == [
        "Kornmod Foods A/S",
        "Tidevand Software GmbH",
    ]
    assert titles(work_mode=WorkMode.ONSITE) == ["Havnelys Logistics ApS"]
    assert titles(level=Seniority.JUNIOR) == [
        "Havnelys Logistics ApS",
        "Smørblomst Mejeri",
    ]
    assert titles(query="data", location="Copenhagen", level=Seniority.SENIOR) == [
        "Fjord Grocery ApS",
        "Ravnekær Mobility",
    ]


def test_only_jobs_with_an_approved_rubric_are_listed(repo, board):
    _, jobs = board
    repo.create_job("empty")  # No rubric yet.
    draft = jobs[1].job.model_copy(
        update={"rubric": jobs[1].job.rubric.model_copy(update={"approved_at": None})}
    )
    repo.create_job("draft")
    repo.save_job("draft", draft, "extracted")
    repo.create_job("approved")
    repo.save_job("approved", jobs[2].job, "rubric")
    assert [x.name for x in listings(repo)] == ["approved"]


# The board demo and its routes


def test_the_board_demo_stores_every_job_once(client, repo):
    names = board_demo(client)
    assert names[0] == "board-fjord-grocery"
    assert len(names) == 11
    assert board_demo(client) == names  # Again: nothing new.
    assert sorted(repo.job_names()) == sorted(names)
    found = ok(client.get("/board"))
    assert [x["name"] for x in found["listings"]] == names  # Newest first.
    assert found["total"] == 11
    assert all(x["demo"] for x in found["listings"])
    settings = repo.job_settings("board-kornmod-foods")
    assert (settings["board"], settings["llm"], settings["vacancies"]) == (
        "kornmod_foods",
        False,
        2,
    )
    # The pool is stored once, and counts as connected to every board job.
    pool = [n for n in repo.candidate_names() if n.startswith(DEMO_PREFIX)]
    assert len(pool) == 12
    assert all(connected(repo, name) == sorted(pool) for name in names)
    assert all(repo.consents(name) == [] for name in names)


def test_board_routes_search_and_read_without_the_rubric(client):
    board_demo(client)
    found = ok(client.get("/board", params={"q": "statistics", "seniority": "mid"}))
    assert [x["company"] for x in found["listings"]] == [
        "Lynfjord Power A/S",
        "Øresund Business Academy",
        "Bogreol Online ApS",
    ]
    assert ok(client.get("/board", params={"work_mode": "remote"}))["listings"]
    assert client.get("/board", params={"work_mode": "sometimes"}).status_code == 422
    assert ok(client.get("/board", params={"location": "Berlin"}))["listings"][0][
        "company"
    ] == ("Kornmod Foods A/S")
    one = ok(client.get("/board/board-ravnekaer-mobility"))
    assert one["title"] == "Senior Machine Learning Engineer"
    assert one["vacancies"] == 1
    assert "Hands-on PyTorch" in one["ad"]
    assert client.get("/board/nothing").status_code == 404
    for body in (found, one, ok(client.get("/board"))):
        assert_no_rubric(body)


def test_a_draft_job_is_not_on_the_board(client):
    name = ok(client.post("/demos/job"), 201)["name"]
    ok(client.post(f"/jobs/{name}/extract"))
    assert ok(client.get("/board"))["listings"] == []
    assert client.get(f"/board/{name}").status_code == 404


# Connecting and withdrawing


def test_connect_and_withdraw_in_the_package(repo, board, pool):
    store_board(repo, pool)
    job = "board-bogreol-online"
    repo.create_candidate("jane")
    with pytest.raises(ConnectError, match="approve your profile"):
        connect(repo, "jane", job)
    with pytest.raises(NotFound):
        connect(repo, "nobody", job)
    with pytest.raises(ConnectError, match="aren't connected"):
        withdraw(repo, "jane", job)


def test_only_approved_profiles_connect(client):
    board_demo(client)
    ok(client.post("/demos/candidate"), 201)
    name = "john-doe-demo"
    response = client.put(f"/candidates/{name}/connections/board-fjord-grocery")
    assert response.status_code == 409
    assert "approve your profile" in response.json()["detail"]
    ok(client.post(f"/candidates/{name}/extract"))  # A draft isn't enough.
    response = client.put(f"/candidates/{name}/connections/board-fjord-grocery")
    assert response.status_code == 409
    assert ok(client.get(f"/candidates/{name}/connections")) == []


def test_connect_list_and_withdraw(client, repo):
    jobs = board_demo(client)
    name = approved_demo(client)
    assert ok(client.get(f"/candidates/{name}/connections")) == []
    before = datetime.now()
    first = ok(client.put(f"/candidates/{name}/connections/{jobs[1]}"))
    assert first["job"] == jobs[1]
    assert datetime.fromisoformat(first["connected_at"]) >= before.replace(
        microsecond=0
    )
    assert first["listing"]["company"] == "Lynfjord Power A/S"
    assert_no_rubric(first)
    # Connecting again keeps the first time.
    again = ok(client.put(f"/candidates/{name}/connections/{jobs[1]}"))
    assert again["connected_at"] == first["connected_at"]
    ok(client.put(f"/candidates/{name}/connections/{jobs[0]}"))
    listed = ok(client.get(f"/candidates/{name}/connections"))
    assert [c["job"] for c in listed] == [jobs[0], jobs[1]]  # Newest first.
    assert repo.consent(name, jobs[1]) is not None

    assert client.delete(f"/candidates/{name}/connections/{jobs[1]}").status_code == 204
    assert repo.consent(name, jobs[1]) is None
    assert [c["job"] for c in ok(client.get(f"/candidates/{name}/connections"))] == [
        jobs[0]
    ]
    response = client.delete(f"/candidates/{name}/connections/{jobs[1]}")
    assert response.status_code == 409
    assert client.put(f"/candidates/{name}/connections/nothing").status_code == 404
    assert client.get("/candidates/nobody/connections").status_code == 404


def test_matching_ranks_only_connected_candidates(client, repo):
    jobs = board_demo(client)
    job = jobs[0]  # Fjord Grocery.
    name = approved_demo(client)
    profile_id = ok(client.get(f"/candidates/{name}/profile"))["id"]

    # Not connected: the pool is ranked, John isn't.
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    assert len(ranking) == 12
    assert profile_id not in {c["profile_id"] for c in ranking}

    ok(client.put(f"/candidates/{name}/connections/{job}"))
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    assert len(ranking) == 13
    assert profile_id in {c["profile_id"] for c in ranking}
    stored = ok(client.get(f"/jobs/{job}/ranking"))["candidates"]
    assert profile_id in {c["profile_id"] for c in stored}
    entries = len(repo.audit_log(kind=AuditKind.RANKING))

    # Withdrawn: out of the next ranking; earlier audit entries stay.
    assert client.delete(f"/candidates/{name}/connections/{job}").status_code == 204
    after = ok(client.get(f"/jobs/{job}/ranking"))["candidates"]
    assert len(after) == 12
    assert profile_id not in {c["profile_id"] for c in after}
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    assert profile_id not in {c["profile_id"] for c in shortlist["candidates"]}
    log = repo.audit_log(kind=AuditKind.RANKING)
    assert len(log) == entries + 2
    earlier = log[entries - 1].payload["ranking"]
    assert profile_id in {r["match"]["profile_id"] for r in earlier}
    # Matching again leaves them out too.
    again = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    assert profile_id not in {c["profile_id"] for c in again}


def test_withdrawing_is_refused_once_revealed(client, repo):
    jobs = board_demo(client)
    job = jobs[0]
    name = approved_demo(client)
    ok(client.put(f"/candidates/{name}/connections/{job}"))
    ok(client.post(f"/jobs/{job}/match"))
    profile_id = ok(client.get(f"/candidates/{name}/profile"))["id"]
    ok(
        client.post(
            f"/jobs/{job}/intents", json={"profile_id": profile_id, "kind": "reveal"}
        ),
        201,
    )
    response = client.delete(f"/candidates/{name}/connections/{job}")
    assert response.status_code == 409
    assert "revealed" in response.json()["detail"]
    assert repo.consent(name, job) is not None


def test_llm_scoring_needs_recordings_for_the_job(client):
    jobs = board_demo(client)
    response = client.post(f"/jobs/{jobs[1]}/match?scorer=llm")
    assert response.status_code == 409
    assert "baseline" in response.json()["detail"]
    assert len(ok(client.post(f"/jobs/{jobs[1]}/match"))["candidates"]) == 12
    # Fjord Grocery has the pool's recordings, so its LLM scorer is free.
    llm = ok(client.post(f"/jobs/{jobs[0]}/match?scorer=llm"))["candidates"]
    assert len(llm) == 12
    assert all(c["model"].startswith("replay:") for c in llm)


def test_each_board_job_ranks_the_pool_through_the_api(client, repo):
    jobs = board_demo(client)
    for job in jobs:
        ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
        best = repo.candidate_of(UUID(ranking[0]["profile_id"]))
        folder = repo.job_settings(job)["board"]
        if folder in BEST:
            assert best == DEMO_PREFIX + BEST[folder], job
        else:
            assert best == DEMO_PREFIX + "priya-raman"
