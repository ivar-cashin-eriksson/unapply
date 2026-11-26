"""The HTTP API, through FastAPI's TestClient.

Every model answer is replayed from John Doe's and Fjord Grocery's recordings: demos
replay them by design, and other candidates get a fake model factory that replays
them too, so the tests check when a paid call would be made without making one.
"""

import json
from datetime import datetime
from pathlib import Path

import anthropic
import pytest
import uvicorn
from fastapi.testclient import TestClient

from unapply.api import candidates, create_app
from unapply.app import demo
from unapply.cli import main
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.llm import API_SWITCH, ReplayLLM
from unapply.schemas import Match

FIXTURES = Path(__file__).parent / "fixtures"
JOHN = FIXTURES / "john_doe"
FJORD = FIXTURES / "jobs" / "fjord_grocery"
# Words of the assessment, which no candidate route may return.
ASSESSMENT_WORDS = [
    "overclaim",
    "underclaim",
    "unverified",
    "statement_only",
    "estimate",
    "confidence",
    "claim_support",
]


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the API created an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


class FakeFactory:
    """Stands in for Claude: records each call it is asked for and replays John."""

    def __init__(self):
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, purpose: str, allow: bool):
        self.calls.append((purpose, allow))
        path = {
            "extract": JOHN / "extraction.json",
            "estimate": JOHN / "estimation.json",
            "questions": JOHN / "questions.json",
            "rubric": FJORD / "extraction.json",
        }[purpose]
        return ReplayLLM(path)


@pytest.fixture
def repo():
    init_db()
    repo = Repository.from_url(database_url())
    yield repo
    repo.engine.dispose()


@pytest.fixture
def fake():
    return FakeFactory()


def make_client(repo, tmp_path, fake=None, internal=False) -> TestClient:
    app = create_app(
        repo=repo,
        uploads=tmp_path / "uploads",
        llm_factory=fake,
        internal_routes=internal,
    )
    return TestClient(app)


@pytest.fixture
def client(repo, tmp_path, fake):
    return make_client(repo, tmp_path, fake)


@pytest.fixture
def internal(repo, tmp_path, fake):
    return make_client(repo, tmp_path, fake, internal=True)


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def assert_no_assessment(body) -> None:
    text = json.dumps(body).lower()
    assert not [w for w in ASSESSMENT_WORDS if w in text], text


def upload_john(client, name="jane"):
    files = [
        ("files", (f.name, f.read_bytes(), "text/markdown"))
        for f in sorted((JOHN / "material").iterdir())
    ]
    return client.post(f"/candidates/{name}/material", files=files)


def with_john_edits(review: dict) -> dict:
    """Make John's review edits (levels, removals, additions) to a review form."""
    edits = demo.review_edits()
    for s in review["skills"]:
        s["level"] = edits["levels"].get(s["name"], s["level"])
        s["keep"] = s["name"] not in edits["remove_skills"]
    for x in review["experiences"]:
        x["keep"] = not any(
            x["title"].startswith(t) for t in edits["remove_experiences"]
        )
    review["preferences"].update(edits["preferences"])
    return {**review, "add_skills": edits["add_skills"], "approve": True}


def demo_candidate(client) -> str:
    return ok(client.post("/demos/candidate"), 201)["name"]


def approved_demo(client) -> str:
    name = demo_candidate(client)
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    return name


# The app


def test_docs_and_health(client):
    assert ok(client.get("/health")) == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    paths = ok(client.get("/openapi.json"))["paths"]
    assert "/candidates/{name}/review" in paths
    assert "/jobs/{name}/rubric" in paths
    assert not [p for p in paths if p.startswith("/internal")]


# Candidates


def test_create_list_and_get_candidates(client):
    created = ok(client.post("/candidates", json={"name": "jane"}), 201)
    assert created == {
        "name": "jane",
        "demo": False,
        "github": None,
        "material": [],
        "has_profile": False,
        "approved": False,
        "questions_waiting": 0,
        "history": [],
    }
    ok(client.post("/candidates", json={"name": "ann", "github": " ann-gh "}), 201)
    assert ok(client.get("/candidates")) == ["ann", "jane"]
    assert ok(client.get("/candidates/ann"))["github"] == "ann-gh"
    assert ok(client.patch("/candidates/ann", json={"github": ""}))["github"] is None


def test_candidate_errors(client):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    assert client.post("/candidates", json={"name": "jane"}).status_code == 409
    assert client.post("/candidates", json={"name": "Jane Doe"}).status_code == 422
    assert client.get("/candidates/nobody").status_code == 404
    assert client.get("/candidates/nobody/profile").status_code == 404
    # No profile yet: nothing to review, ask about or show.
    assert client.get("/candidates/jane/review").status_code == 409
    assert client.post("/candidates/jane/questions").status_code == 409
    assert client.get("/candidates/jane/profile").status_code == 404
    # Nothing to extract from (refused before that only if calls aren't allowed).
    response = client.post("/candidates/jane/extract?allow_api=true")
    assert response.status_code == 409
    assert "material" in response.json()["detail"]


def test_upload_list_and_remove_material(client):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    files = ok(upload_john(client), 201)
    assert [f["name"] for f in files] == ["cv.md", "notes.md"]
    assert all(f["size"] > 0 for f in files)
    assert ok(client.get("/candidates/jane"))["material"] == files
    ok(client.delete("/candidates/jane/material/notes.md"), 204)
    assert [f["name"] for f in ok(client.get("/candidates/jane/material"))] == ["cv.md"]
    assert client.delete("/candidates/jane/material/notes.md").status_code == 404


def test_upload_refuses_unsupported_files_and_adds_nothing(client):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    files = [
        ("files", ("cv.md", b"# Jane", "text/markdown")),
        ("files", ("run.exe", b"MZ", "application/octet-stream")),
    ]
    response = client.post("/candidates/jane/material", files=files)
    assert response.status_code == 422
    assert ok(client.get("/candidates/jane/material")) == []
    # Paths in a file name are dropped, so a file can't land outside the folder.
    files = [("files", ("../../escape.md", b"# Jane", "text/markdown"))]
    assert [
        f["name"]
        for f in ok(client.post("/candidates/jane/material", files=files), 201)
    ] == ["escape.md"]


def test_upload_refuses_files_over_the_limit(client, monkeypatch):
    monkeypatch.setattr(candidates, "MAX_UPLOAD_BYTES", 10)
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    files = [
        ("files", ("small.md", b"# Jane", "text/markdown")),
        ("files", ("big.md", b"# Jane " * 10, "text/markdown")),
    ]
    response = client.post("/candidates/jane/material", files=files)
    assert response.status_code == 413
    assert "big.md" in response.json()["detail"]
    assert ok(client.get("/candidates/jane/material")) == []


def test_api_command_starts_uvicorn(monkeypatch):
    started = {}

    def run(app, host, port):
        started.update(app=app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", run)
    assert main(["api", "--port", "8123"]) == 0
    assert (started["host"], started["port"]) == ("127.0.0.1", 8123)
    paths = TestClient(started["app"]).get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/internal")]

    assert main(["api", "--internal"]) == 0
    paths = TestClient(started["app"]).get("/openapi.json").json()["paths"]
    assert "/internal/candidates/{name}/assessment" in paths


# Paid calls


def test_paid_calls_are_refused_unless_allowed(client, fake):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    ok(upload_john(client), 201)
    response = client.post("/candidates/jane/extract")
    assert response.status_code == 403
    assert "allow_api=true" in response.json()["detail"]
    assert fake.calls == []
    assert ok(client.get("/candidates/jane"))["history"] == []

    response = client.post("/candidates/jane/extract?allow_api=true")
    extraction = ok(response)
    assert fake.calls == [("extract", True)]
    assert len(extraction["profile"]["skills"]) == 45
    assert_no_assessment(extraction)
    assert ok(client.get("/candidates/jane"))["history"] == ["extracted"]


def test_the_switch_allows_paid_calls(client, fake, monkeypatch):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    ok(upload_john(client), 201)
    monkeypatch.setenv(API_SWITCH, "1")
    ok(client.post("/candidates/jane/extract"))
    assert fake.calls == [("extract", True)]


def test_claude_is_never_reached_without_allow(repo, tmp_path):
    """With the real factory, a refused request never creates a client."""
    client = make_client(repo, tmp_path)
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    ok(upload_john(client), 201)
    assert client.post("/candidates/jane/extract").status_code == 403
    ok(client.post("/jobs", json={"name": "acme", "ad": "We need a data person."}), 201)
    assert client.post("/jobs/acme/extract").status_code == 403
    assert ok(client.get("/jobs/acme"))["has_rubric"] is False


def test_questions_and_answers_without_allow(client, fake):
    """Questions are refused; answers are saved, and assessed only once allowed."""
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    ok(upload_john(client), 201)
    ok(client.post("/candidates/jane/extract?allow_api=true"))
    review = ok(client.get("/candidates/jane/review"))
    ok(client.put("/candidates/jane/review", json=with_john_edits(review)))

    assert client.post("/candidates/jane/questions").status_code == 403
    assert ok(client.get("/candidates/jane"))["history"] == ["extracted", "reviewed"]
    assert fake.calls == [("extract", True)]

    waiting = ok(client.post("/candidates/jane/questions?allow_api=true"))["waiting"]
    assert [c[0] for c in fake.calls] == ["extract", "estimate", "questions"]
    assert waiting
    skill = waiting[0]["skill"]
    answered = ok(
        client.post(
            "/candidates/jane/answers",
            json={"answers": {skill: "I used it every day for three years."}},
        )
    )
    assert answered == {"answered": 1}
    assert len(fake.calls) == 3  # No re-assessment without allow.
    summary = ok(client.get("/candidates/jane"))
    assert summary["history"][-1] == "interviewed"
    assert summary["questions_waiting"] == 0


def test_demos_never_need_allow(client, fake):
    name = demo_candidate(client)
    ok(client.post(f"/candidates/{name}/extract"))
    assert fake.calls == []


# John Doe's journey, as a demo


def test_john_doe_demo_journey(client, fake):
    created = ok(client.post("/demos/candidate"), 201)
    name = created["name"]
    assert name == "john-doe-demo"
    assert created["demo"] is True
    assert [f["name"] for f in created["material"]] == ["cv.md", "notes.md"]
    assert ok(client.post("/demos/candidate"), 201)["name"] == "john-doe-demo-2"

    extraction = ok(client.post(f"/candidates/{name}/extract"))
    profile = extraction["profile"]
    assert (len(profile["experiences"]), len(profile["skills"])) == (7, 45)

    review = ok(client.get(f"/candidates/{name}/review"))
    assert review["approve"] is False
    assert len(review["skills"]) == 45
    assert all(s["evidence"] for s in review["skills"])
    assert_no_assessment(review)

    john = ok(client.get(f"/candidates/{name}/demo/review"))
    assert john["approve"] is True
    reviewed = ok(client.put(f"/candidates/{name}/review", json=john))
    assert reviewed["approved_by_candidate_at"]
    rated = [s for s in reviewed["skills"] if s["self_level"]]
    assert (len(reviewed["skills"]), len(rated)) == (30, 26)
    assert_no_assessment(reviewed)

    questions = ok(client.post(f"/candidates/{name}/questions"))
    assert len(questions["waiting"]) == 8
    assert questions["answered"] == []
    assert all(q["why"] and q["text"] for q in questions["waiting"])
    assert_no_assessment(questions)
    assert ok(client.get(f"/candidates/{name}"))["questions_waiting"] == 8
    # Prepared once; answer or discard them before asking again.
    assert client.post(f"/candidates/{name}/questions").status_code == 409

    answers = ok(client.get(f"/candidates/{name}/demo/answers"))
    assert sorted(answers["answers"]) == [
        "deep learning",
        "git",
        "kubernetes",
        "pandas",
    ]
    assert ok(client.post(f"/candidates/{name}/answers", json=answers)) == {
        "answered": 4
    }
    after = ok(client.get(f"/candidates/{name}/questions"))
    assert after["waiting"] == []
    assert [q["skill"] for q in after["answered"]] == [
        q["skill"] for q in questions["waiting"] if q["skill"] in answers["answers"]
    ]
    assert_no_assessment(after)

    shown = ok(client.get(f"/candidates/{name}/profile"))
    assert_no_assessment(shown)
    assert all(
        set(s) == {"name", "category", "self_level", "evidence_ids"}
        for s in shown["skills"]
    )
    summary = ok(client.get(f"/candidates/{name}"))
    assert summary["approved"] is True
    assert summary["history"] == [
        "extracted",
        "reviewed",
        "assessed",
        "interviewed",
        "assessed",
    ]
    assert fake.calls == []


def test_review_errors(client):
    name = demo_candidate(client)
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/review"))
    # Not approved: no questions yet.
    ok(client.put(f"/candidates/{name}/review", json=review))
    assert client.post(f"/candidates/{name}/questions").status_code == 409
    # An added skill must say where it was used.
    bad = {
        **review,
        "add_skills": [{"name": "matlab", "category": "technology", "note": " "}],
    }
    response = client.put(f"/candidates/{name}/review", json=bad)
    assert response.status_code == 422
    assert "where you used" in response.json()["detail"]
    # Dates are YYYY or YYYY-MM.
    experiences = [{**review["experiences"][0], "start": "last spring"}]
    bad = {**review, "experiences": experiences + review["experiences"][1:]}
    assert client.put(f"/candidates/{name}/review", json=bad).status_code == 422
    assert ok(client.get(f"/candidates/{name}"))["history"] == ["extracted", "reviewed"]


def test_review_merges_synonyms_and_keeps_added_skills(client):
    name = demo_candidate(client)
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/review"))
    review["add_skills"] = [
        {
            "name": "Matlab",
            "category": "technology",
            "level": 2,
            "note": "Signal processing coursework, 2014.",
        }
    ]
    review["skills"][0]["keep"] = False
    reviewed = ok(client.put(f"/candidates/{name}/review", json=review))
    names = [s["name"] for s in reviewed["skills"]]
    assert "matlab" in names
    assert review["skills"][0]["name"] not in names


def test_answer_errors(client):
    name = approved_demo(client)
    assert (
        client.post(
            f"/candidates/{name}/answers", json={"answers": {"git": "Daily."}}
        ).status_code
        == 409
    )
    ok(client.post(f"/candidates/{name}/questions"))
    response = client.post(
        f"/candidates/{name}/answers", json={"answers": {"cobol": "Daily."}}
    )
    assert response.status_code == 422
    # Nothing answered: nothing changes, and the questions keep waiting.
    blank = {"answers": {"git": "  "}}
    assert ok(client.post(f"/candidates/{name}/answers", json=blank)) == {"answered": 0}
    assert ok(client.get(f"/candidates/{name}"))["questions_waiting"] == 8
    ok(client.delete(f"/candidates/{name}/questions"), 204)
    assert ok(client.get(f"/candidates/{name}"))["questions_waiting"] == 0


def test_demo_material_is_fixed(client):
    name = demo_candidate(client)
    files = [("files", ("extra.md", b"# More", "text/markdown"))]
    assert client.post(f"/candidates/{name}/material", files=files).status_code == 409
    assert client.delete(f"/candidates/{name}/material/cv.md").status_code == 409
    assert client.patch(f"/candidates/{name}", json={"github": "x"}).status_code == 409


def test_demo_helpers_only_for_demos(client):
    ok(client.post("/candidates", json={"name": "jane"}), 201)
    assert client.get("/candidates/jane/demo/review").status_code == 404
    assert client.get("/candidates/jane/demo/answers").status_code == 404


# The internal assessment


def test_assessment_routes_exist_only_when_internal(client, internal):
    name = approved_demo(client)
    assert client.get(f"/internal/candidates/{name}/assessment").status_code == 404
    paths = ok(internal.get("/openapi.json"))["paths"]
    assert "/internal/candidates/{name}/assessment" in paths


def test_internal_assessment_after_interview(client, internal):
    name = approved_demo(client)
    ok(client.post(f"/candidates/{name}/questions"))
    answers = ok(client.get(f"/candidates/{name}/demo/answers"))
    ok(client.post(f"/candidates/{name}/answers", json=answers))

    assessment = ok(internal.get(f"/internal/candidates/{name}/assessment"))
    assert assessment["not_estimated"] == []
    assert assessment["summary"].startswith("3 overclaims")
    skills = {s["name"]: s for s in assessment["profile"]["skills"]}
    # John's detailed pandas answer raised the estimate (see interview_answers.yaml).
    assert skills["pandas"]["estimate"]["level"] == 4
    assert skills["kubernetes"]["estimate"]["confidence"] <= 0.3


def test_internal_estimate(internal, fake):
    name = demo_candidate(internal)
    ok(internal.post(f"/candidates/{name}/extract"))
    review = ok(internal.get(f"/candidates/{name}/demo/review"))
    ok(internal.put(f"/candidates/{name}/review", json=review))
    before = ok(internal.get(f"/internal/candidates/{name}/assessment"))
    assert before["summary"] is None
    assert len(before["not_estimated"]) == 30

    after = ok(internal.post(f"/internal/candidates/{name}/estimate"))
    assert after["not_estimated"] == []
    assert after["summary"]
    # Nothing left to estimate: no model call, claim support recomputed.
    again = ok(internal.post(f"/internal/candidates/{name}/estimate"))
    assert again["summary"] == after["summary"]
    assert fake.calls == []

    ok(internal.post("/candidates", json={"name": "jane"}), 201)
    ok(upload_john(internal), 201)
    ok(internal.post("/candidates/jane/extract?allow_api=true"))
    assert internal.post("/internal/candidates/jane/estimate").status_code == 403
    ok(internal.post("/internal/candidates/jane/estimate?allow_api=true&all=true"))
    assert fake.calls[-1] == ("estimate", True)


# Jobs


def test_fjord_grocery_demo_job(client, fake):
    created = ok(client.post("/demos/job"), 201)
    name = created["name"]
    assert name == "fjord-grocery-demo"
    assert "Fjord Grocery" in created["ad"]["ad"]
    assert created["has_rubric"] is False
    response = client.put(f"/jobs/{name}/ad", json={"ad": "Another ad."})
    assert response.status_code == 409

    extraction = ok(client.post(f"/jobs/{name}/extract"))
    job = extraction["job"]
    assert job["title"] == "Senior Data Scientist, Pricing and Forecasting"
    rubric = job["rubric"]
    kinds = [c["kind"] for c in rubric["criteria"]]
    assert (kinds.count("must_have"), kinds.count("nice_to_have")) == (6, 4)
    assert rubric["hard_filters"]["min_years_experience"] == 4
    assert extraction["dropped"] == []
    assert ok(client.get(f"/jobs/{name}/rubric")) == rubric

    summary = ok(client.get(f"/jobs/{name}"))
    assert (summary["has_rubric"], summary["rubric_version"]) == (True, 1)
    assert summary["approved"] is False
    assert fake.calls == []


def test_edit_and_approve_a_rubric(client):
    name = ok(client.post("/demos/job"), 201)["name"]
    job = ok(client.post(f"/jobs/{name}/extract"))["job"]
    criteria = [
        {
            "id": c["id"],
            "kind": c["kind"],
            "description": c["description"],
            "skill": c["skill"],
            "min_level": c["min_level"],
            "weight": int(c["weight"]),
        }
        for c in job["rubric"]["criteria"]
    ]
    form = {
        "company": job["company"],
        "title": job["title"],
        "hard_filters": job["rubric"]["hard_filters"],
        "criteria": criteria,
        "approve": True,
    }
    # Unchanged and approved: the same version.
    approved = ok(client.put(f"/jobs/{name}/rubric", json=form))
    assert (approved["version"], bool(approved["approved_at"])) == (1, True)

    # A changed weight, a removed and an added criterion: a new draft version.
    criteria[0]["weight"] = 1
    criteria[1]["keep"] = False
    criteria.append(
        {"kind": "nice_to_have", "description": "Has used Kubernetes", "skill": "k8s"}
    )
    edited = ok(
        client.put(
            f"/jobs/{name}/rubric",
            json={**form, "criteria": criteria, "approve": False},
        )
    )
    assert (edited["version"], edited["approved_at"]) == (2, None)
    assert len(edited["criteria"]) == 10
    assert edited["criteria"][-1]["skill"] == "kubernetes"
    assert ok(client.get(f"/jobs/{name}/rubric/1"))["criteria"][0]["weight"] != 1
    assert client.get(f"/jobs/{name}/rubric/9").status_code == 404
    assert ok(client.get(f"/jobs/{name}"))["history"] == [
        "extracted",
        "rubric",
        "rubric",
    ]

    # Invalid edits are refused with the sheet's message.
    bad = {**form, "criteria": [{**criteria[0], "id": "not-a-criterion"}]}
    response = client.put(f"/jobs/{name}/rubric", json=bad)
    assert response.status_code == 422
    assert "unknown criterion" in response.json()["detail"]
    nothing = {**form, "criteria": [{**c, "keep": False} for c in criteria]}
    assert client.put(f"/jobs/{name}/rubric", json=nothing).status_code == 422


def test_create_and_set_a_job_ad(client, fake):
    created = ok(client.post("/jobs", json={"name": "acme"}), 201)
    assert created["ad"] == {"ad": "", "company": None, "title": None}
    assert client.post("/jobs", json={"name": "acme"}).status_code == 409
    assert client.get("/jobs/acme/rubric").status_code == 409
    assert client.post("/jobs/acme/extract?allow_api=true").status_code == 409

    ad = (FJORD / "ad.md").read_text(encoding="utf-8")
    body = {"ad": ad, "company": "Fjord Grocery A/S", "title": None}
    assert ok(client.put("/jobs/acme/ad", json=body))["ad"] == body
    assert ok(client.get("/jobs")) == ["acme"]
    job = ok(client.post("/jobs/acme/extract?allow_api=true"))["job"]
    assert job["company"] == "Fjord Grocery A/S"
    assert fake.calls == [("rubric", True)]


def test_a_matched_rubric_is_not_replaced(client, repo):
    name = ok(client.post("/demos/job"), 201)["name"]
    job = ok(client.post(f"/jobs/{name}/extract"))["job"]
    repo.save_match(
        Match(
            job_id=job["id"],
            profile_id=job["id"],
            rubric_version=1,
            passed_hard_filters=True,
            model="test",
            scored_at=datetime(2026, 11, 26),
        )
    )
    response = client.post(f"/jobs/{name}/extract")
    assert response.status_code == 409
    assert ok(client.get(f"/jobs/{name}/rubric"))["version"] == 1
