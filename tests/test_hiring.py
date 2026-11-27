"""Tests for revealing candidates, requesting applications, and applying or declining.

Everything runs on the demo jobs and John Doe's demo candidate, or the synthetic
pool, with the baseline scorer: no model is called.
"""

import json
from uuid import uuid4

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply.api.app import create_app
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.evaluation.pool import DEFAULT_POOL, DEMO_PREFIX
from unapply.jobs.hiring import ChargeIntent, Progress, Stage, contact_from_cv
from unapply.matching.audit import AuditKind

JOHN = ("John Doe", "john.doe@example.com", "+45 00 00 00 00")


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
def app(repo, tmp_path):
    return create_app(repo=repo, uploads=tmp_path / "uploads", llm_factory=NoModel())


@pytest.fixture
def client(app):
    return TestClient(app)


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def john_on(client, *jobs: str) -> tuple[str, str]:
    """John Doe's approved demo candidate, connected to jobs; his name and profile id."""
    name = ok(client.post("/demos/candidate"), 201)["name"]
    ok(client.post(f"/candidates/{name}/extract"))
    review = ok(client.get(f"/candidates/{name}/demo/review"))
    ok(client.put(f"/candidates/{name}/review", json=review))
    for job in jobs:
        ok(client.put(f"/candidates/{name}/connections/{job}"))
        ok(client.post(f"/jobs/{job}/match"))
    return name, ok(client.get(f"/candidates/{name}/profile"))["id"]


def board(client) -> list[str]:
    return ok(client.post("/demos/board"), 201)["jobs"]


def card(client, job: str, profile_id: str) -> dict:
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    return next(c for c in shortlist["candidates"] if c["profile_id"] == profile_id)


def counts(client, job: str) -> dict:
    return ok(client.get(f"/jobs/{job}/shortlist"))["counts"]


def connection(client, name: str, job: str) -> dict:
    found = ok(client.get(f"/candidates/{name}/connections"))
    return next(c for c in found if c["job"] == job)


# Contact details


def test_contact_details_come_from_the_top_of_a_demo_cv():
    john = (DEFAULT_POOL.parent / "john_doe" / "material" / "cv.md").read_text("utf-8")
    assert contact_from_cv(john, "x").model_dump() == dict(
        zip(("name", "email", "phone"), JOHN, strict=True)
    )
    astrid = (DEFAULT_POOL / "astrid-holm" / "material" / "cv.md").read_text("utf-8")
    found = contact_from_cv(astrid, "x")
    assert (found.name, found.email) == ("Astrid Holm", "astrid.holm@example.com")
    assert contact_from_cv("No heading, no email", "someone").name == "someone"


def test_a_candidate_sets_their_contact_details(client):
    ok(client.post("/candidates", json={"name": "real"}), 201)
    assert ok(client.get("/candidates/real/contact")) == {
        "name": "real",
        "email": None,
        "phone": None,
    }
    saved = ok(
        client.put(
            "/candidates/real/contact",
            json={"name": " Kim Berg ", "email": "kim@example.org", "phone": ""},
        )
    )
    assert saved == {"name": "Kim Berg", "email": "kim@example.org", "phone": None}
    assert ok(client.get("/candidates/real/contact")) == saved
    assert client.put("/candidates/real/contact", json={"name": ""}).status_code == 422
    name, _ = john_on(client)
    assert ok(client.get(f"/candidates/{name}/contact"))["name"] == "John Doe"
    response = client.put(f"/candidates/{name}/contact", json={"name": "Other"})
    assert response.status_code == 409
    assert client.get("/candidates/nobody/contact").status_code == 404


# The whole flow


def test_reveal_request_and_apply(client, repo):
    jobs = board(client)
    job = jobs[0]  # Fjord Grocery, with the pool connected.
    name, profile_id = john_on(client, job)
    url = f"/jobs/{job}/candidates/{profile_id}"

    # Connected: anonymous, no quotes, and counted.
    before = card(client, job, profile_id)
    assert before["progress"]["stage"] == "connected"
    assert before["contact"] is None and before["evidence"] == []
    assert counts(client, job) == {
        "connected": 13,
        "revealed": 0,
        "requested": 0,
        "applied": 0,
    }
    assert ok(client.get(f"/board/{job}"))["counts"]["connected"] == 13
    assert connection(client, name, job)["stage"] == "connected"

    # Asking to apply before a reveal is refused, in the API.
    response = client.post(f"{url}/request-application")
    assert response.status_code == 409
    assert "reveal" in response.json()["detail"]
    assert repo.progress(name, job) is None

    # Reveal: once, with a charge intent and an audit entry.
    revealed = ok(client.post(f"{url}/reveal"), 201)
    assert revealed["stage"] == "revealed" and revealed["profile_id"] == profile_id
    assert "John" not in json.dumps(revealed)
    assert ok(client.post(f"{url}/reveal"))["revealed_at"] == revealed["revealed_at"]
    progress = repo.progress(name, job)
    assert progress.charge == ChargeIntent.model_validate(progress.charge)
    assert progress.charge.charged is False
    entries = repo.audit_log(repo.job(job).id, AuditKind.REVEAL)
    assert len(entries) == 1
    assert str(entries[0].profile_id) == profile_id
    assert entries[0].profile_hash is not None
    assert entries[0].payload["charge"]["charged"] is False
    assert "John" not in json.dumps(entries[0].model_dump(mode="json"))

    # Now the employer sees who it is, and the quotes behind each score.
    shown = card(client, job, profile_id)
    assert shown["contact"] == dict(zip(("name", "email", "phone"), JOHN, strict=True))
    quotes = {e["id"] for e in shown["evidence"]}
    assert quotes
    ranked = ok(client.get(f"/jobs/{job}/ranking"))["candidates"]
    mine = next(r for r in ranked if r["profile_id"] == profile_id)
    for score in mine["criterion_scores"]:
        assert set(score["evidence_ids"]) <= quotes
    assert counts(client, job)["revealed"] == 1
    assert connection(client, name, job)["stage"] == "revealed"
    # Revealed: the connection can't be withdrawn.
    assert client.delete(f"/candidates/{name}/connections/{job}").status_code == 409

    # Applying before being asked is refused.
    response = client.post(f"/candidates/{name}/applications/{job}", data={"x": "y"})
    assert response.status_code == 409

    # Request an application: once.
    asked = ok(client.post(f"{url}/request-application"), 201)
    assert asked["stage"] == "requested"
    again = ok(client.post(f"{url}/request-application"))
    assert again["requested_at"] == asked["requested_at"]
    assert counts(client, job)["requested"] == 1
    mine = connection(client, name, job)
    assert mine["stage"] == "requested"
    assert mine["listing"]["company"] == "Fjord Grocery ApS"
    assert mine["listing"]["ad"]
    assert mine["listing"]["counts"]["requested"] == 1

    # Applying needs a letter or a file, of a kind that is allowed.
    apply = f"/candidates/{name}/applications/{job}"
    assert client.post(apply, data={"letter": "  "}).status_code == 409
    bad = client.post(apply, files={"files": ("run.exe", b"MZ", "application/x")})
    assert bad.status_code == 422
    assert repo.progress(name, job).answer is None
    applied = ok(
        client.post(
            apply,
            data={"letter": "Dear Fjord Grocery, I would like to apply."},
            files=[
                ("files", ("cv.md", b"# John Doe\n", "text/markdown")),
                ("files", ("../../letter.txt", b"Hello", "text/plain")),
            ],
        )
    )
    assert applied["stage"] == "applied"
    assert [f["name"] for f in applied["progress"]["files"]] == ["cv.md", "letter.txt"]
    assert client.post(apply, data={"letter": "Again"}).status_code == 409
    assert client.post(f"{apply}/decline").status_code == 409

    # The employer sees the application, and can download its files.
    seen = card(client, job, profile_id)["progress"]
    assert seen["stage"] == "applied"
    assert seen["letter"] == "Dear Fjord Grocery, I would like to apply."
    first = seen["files"][0]
    download = client.get(f"{url}/files/{first['id']}")
    assert download.status_code == 200 and download.content == b"# John Doe\n"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["content-type"] == "application/octet-stream"
    own = client.get(f"/candidates/{name}/applications/{job}/files/{first['id']}")
    assert own.content == b"# John Doe\n"
    assert client.get(f"{url}/files/999").status_code == 404
    assert (
        client.get(f"/jobs/{jobs[1]}/candidates/{profile_id}/files/1").status_code
        == 404
    )
    assert counts(client, job) == {
        "connected": 13,
        "revealed": 1,
        "requested": 1,
        "applied": 1,
    }


def test_a_candidate_declines(client, repo):
    jobs = board(client)
    job = jobs[1]
    name, profile_id = john_on(client, job)
    url = f"/jobs/{job}/candidates/{profile_id}"
    ok(client.post(f"{url}/reveal"), 201)
    ok(client.post(f"{url}/request-application"), 201)
    declined = ok(client.post(f"/candidates/{name}/applications/{job}/decline"))
    assert declined["stage"] == "declined"
    assert declined["progress"]["letter"] == "" and declined["progress"]["files"] == []
    assert card(client, job, profile_id)["progress"]["stage"] == "declined"
    assert (
        client.post(f"/candidates/{name}/applications/{job}/decline").status_code == 409
    )
    shown = ok(client.get(f"/jobs/{job}/shortlist"))["counts"]
    assert (shown["requested"], shown["applied"]) == (1, 0)


def test_reveal_errors_and_the_quota(client):
    job = ok(client.post("/demos/shortlist"), 201)["name"]
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    ids = [c["profile_id"] for c in ranking]
    stranger = uuid4()
    assert client.post(f"/jobs/{job}/candidates/{stranger}/reveal").status_code == 404
    assert client.post(f"/jobs/{job}/candidates/x/reveal").status_code == 422
    assert client.post(f"/jobs/nothing/candidates/{ids[0]}/reveal").status_code == 404
    assert (
        client.post(f"/jobs/{job}/candidates/{stranger}/request-application")
    ).status_code == 404

    # Ten reveals, the job's quota; then no more, though revealing again works.
    for profile_id in ids[:10]:
        ok(client.post(f"/jobs/{job}/candidates/{profile_id}/reveal"), 201)
    response = client.post(f"/jobs/{job}/candidates/{ids[10]}/reveal")
    assert response.status_code == 409
    assert "all 10 reveals" in response.json()["detail"]
    ok(client.post(f"/jobs/{job}/candidates/{ids[0]}/reveal"))
    # A revealed pool candidate shows their name from their CV.
    shortlist = ok(client.get(f"/jobs/{job}/shortlist"))
    names = {c["contact"]["name"] for c in shortlist["candidates"] if c["contact"]}
    assert len(names) == 10 and "Astrid Holm" in names
    assert shortlist["counts"]["revealed"] == 10


def test_pool_candidates_see_their_connection_to_demo_jobs(client):
    job = ok(client.post("/demos/shortlist"), 201)["name"]
    ranking = ok(client.post(f"/jobs/{job}/match"))["candidates"]
    ok(client.post(f"/jobs/{job}/candidates/{ranking[0]['profile_id']}/reveal"), 201)
    name = DEMO_PREFIX + "astrid-holm"
    # The shortlist job isn't on the board, but the progress is still there.
    response = client.post(f"/candidates/{name}/applications/{job}/decline")
    assert response.status_code == 409


# Nothing identifying before a reveal


def employer_gets(app) -> list[str]:
    """Every employer route that reads: GET under /jobs, and the board's."""
    return sorted(
        path
        for path, methods in app.openapi()["paths"].items()
        if "get" in methods and path.startswith(("/jobs", "/board"))
    )


def test_nothing_identifying_or_quoted_reaches_the_employer_before_a_reveal(
    app, client, repo
):
    jobs = board(client)
    job = jobs[0]
    name, profile_id = john_on(client, job)
    profile = repo.profile(name)
    secrets = [*JOHN, name, *(e.quote for e in profile.evidence if len(e.quote) > 20)]
    assert len(secrets) > 10
    values = {
        "name": job,
        "job": job,
        "profile_id": profile_id,
        "file_id": "1",
        "version": "1",
    }

    def read_everything() -> dict[str, str]:
        found = {}
        for path in employer_gets(app):
            url = path
            for key, value in values.items():
                url = url.replace("{" + key + "}", value)
            response = client.get(url)
            assert response.status_code in (200, 404), (url, response.text)
            found[path] = response.text
            for scorer in ("baseline", "llm"):
                if path.endswith(("/ranking", "/shortlist", "/overview")):
                    found[f"{path}?{scorer}"] = client.get(
                        f"{url}?scorer={scorer}"
                    ).text
        found["POST match"] = client.post(f"/jobs/{job}/match").text
        return found

    pages = read_everything()
    # Every employer route that reads was asked.
    assert {p for p in pages if p.startswith("/") and "?" not in p} == set(
        employer_gets(app)
    )
    assert "/jobs/{name}/shortlist" in pages
    for path, text in pages.items():
        leaked = [s for s in secrets if s in text]
        assert not leaked, (path, leaked)

    # Revealed: the shortlist names him and quotes him; other routes still don't.
    ok(client.post(f"/jobs/{job}/candidates/{profile_id}/reveal"), 201)
    after = read_everything()
    shortlist = after["/jobs/{name}/shortlist"]
    assert "John Doe" in shortlist and "john.doe@example.com" in shortlist
    assert any(e.quote in json.loads(shortlist).__repr__() for e in profile.evidence)
    for path, text in after.items():
        if "shortlist" not in path:
            assert not [s for s in secrets if s in text], path


# The package


def test_progress_round_trips_with_files(repo, client):
    jobs = board(client)
    name, _ = john_on(client, jobs[0])
    assert repo.progress(name, jobs[0]) is None
    progress = Progress(candidate=name, job=jobs[0])
    assert progress.stage is Stage.CONNECTED
    repo.save_progress(progress.model_copy(update={"revealed_at": progress_time()}))
    repo.save_progress(
        repo.progress(name, jobs[0]).model_copy(
            update={"requested_at": progress_time(), "answer": "applied"}
        ),
        [("a.md", b"A"), ("b.pdf", b"BB")],
    )
    found = repo.progress(name, jobs[0])
    assert found.stage is Stage.APPLIED
    assert [(f.name, f.size) for f in found.files] == [("a.md", 1), ("b.pdf", 2)]
    assert repo.progresses(job=jobs[0]) == [found]
    assert repo.progresses(candidate=name) == [found]
    assert repo.application_file(name, jobs[0], found.files[1].id) == ("b.pdf", b"BB")
    assert repo.application_file(name, jobs[1], found.files[1].id) is None


def progress_time():
    from datetime import datetime

    return datetime(2026, 11, 27, 12, 0)
