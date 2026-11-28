"""Tests for asking about a revealed candidate: a faked model, or the demo stand-ins.

No test calls a model: paid calls go to a fake factory, and the pool's demo
questions replay their hand-written stand-ins.
"""

from pathlib import Path
from uuid import UUID

import anthropic
import pytest
from fastapi.testclient import TestClient

from unapply import cli
from unapply.api.app import create_app
from unapply.db.engine import database_url, init_db
from unapply.db.repository import Repository
from unapply.evaluation.pool import DEFAULT_POOL, load_pool
from unapply.jobs.ask import (
    MAX_HISTORY,
    MAX_QUESTION_CHARS,
    BadQuestion,
    ModelAnswer,
    Turn,
    ask_candidate,
    check_question,
    demo_questions,
    demo_recording,
    render_ask_prompt,
)
from unapply.llm import ReplayLLM

PRODUCTION = "Has this candidate deployed models to production?"


@pytest.fixture(autouse=True)
def no_client(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the API created an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


class FakeLLM:
    """Answers every question with a fixed answer, and keeps what it was sent."""

    model = "fake-model"

    def __init__(self, answer: ModelAnswer):
        self.answer = answer
        self.prompts: list[str] = []

    def parse(self, *, system, prompt, output_type):
        assert output_type is ModelAnswer
        self.prompts.append(prompt)
        return self.answer


class FakeFactory:
    """Stands in for Claude; records each model asked for."""

    def __init__(self, answer: ModelAnswer):
        self.calls: list[tuple[str, bool]] = []
        self.llm = FakeLLM(answer)

    def __call__(self, purpose: str, allow: bool):
        self.calls.append((purpose, allow))
        return self.llm


@pytest.fixture(scope="module")
def pool():
    return load_pool()


@pytest.fixture
def astrid(pool):
    return pool.candidates["astrid-holm"].profile


# The prompt and the answer


def test_the_model_sees_only_the_candidates_own_material(astrid):
    history = [Turn(question="Do they know <SQL>?", answer="Yes, E6 says so.")]
    prompt, evidence = render_ask_prompt(astrid, "And Spark & PySpark?", history)
    # Every quote, with an id that maps back to it.
    assert set(evidence) == {f"E{i}" for i in range(1, len(astrid.evidence) + 1)}
    assert all(e.quote.split()[0] in prompt for e in astrid.evidence)
    assert evidence["E2"] == astrid.evidence[1].id
    # Own levels, but nothing of the assessment or the candidate's preferences.
    assert 'own_level="5"' in prompt
    for hidden in ("estimated_level", "confidence=", "claim", "salary", "DKK"):
        assert hidden not in prompt
    assert all(s.estimate.rationale not in prompt for s in astrid.skills if s.estimate)
    # No rubric: nothing of the job, its criteria or its weights.
    for hidden in ("criteri", "weight", "min_level", "Fjord"):
        assert hidden not in prompt
    # The earlier turns, then the question last; all escaped.
    assert "<question>Do they know &lt;SQL&gt;?</question>" in prompt
    assert prompt.rstrip().endswith("<question>And Spark &amp; PySpark?</question>")


def test_an_answer_cites_the_candidates_quotes(astrid):
    llm = FakeLLM(
        ModelAnswer(answered=True, answer=" In production. ", evidence=["E2", "E2"])
    )
    answer = ask_candidate(astrid, PRODUCTION, llm)
    assert answer.answered and answer.answer == "In production."
    assert [q.id for q in answer.evidence] == [astrid.evidence[1].id]
    assert answer.evidence[0].quote == astrid.evidence[1].quote
    assert answer.evidence[0].source == "cv"
    assert answer.model == "fake-model" and answer.problems == []


def test_ids_that_arent_the_candidates_are_dropped(astrid):
    llm = FakeLLM(ModelAnswer(answered=True, answer="Yes.", evidence=["E2", "E99"]))
    answer = ask_candidate(astrid, PRODUCTION, llm)
    assert [q.id for q in answer.evidence] == [astrid.evidence[1].id]
    assert answer.answered
    assert answer.problems == ["cited ['E99'], which aren't the candidate's; dropped"]


def test_an_answer_without_valid_citations_isnt_answered_by_the_material(astrid):
    for cited in ([], ["E99", "C1"]):
        llm = FakeLLM(ModelAnswer(answered=True, answer="Surely.", evidence=cited))
        answer = ask_candidate(astrid, PRODUCTION, llm)
        assert not answer.answered and answer.evidence == []
        assert "answered without citing the candidate's quotes" in answer.problems
    # Saying the material doesn't answer it is a valid answer, with or without quotes.
    llm = FakeLLM(ModelAnswer(answered=False, answer="Nothing says.", evidence=[]))
    answer = ask_candidate(astrid, "Do they speak Japanese?", llm)
    assert not answer.answered and answer.problems == []


def test_questions_are_checked():
    assert check_question("  Has she led a team? ", []) == "Has she led a team?"
    with pytest.raises(BadQuestion, match="write a question"):
        check_question("   ", [])
    with pytest.raises(BadQuestion, match="at most"):
        check_question("x" * (MAX_QUESTION_CHARS + 1), [])
    turn = Turn(question="q", answer="a")
    check_question("q", [turn] * MAX_HISTORY)
    with pytest.raises(BadQuestion, match="earlier questions"):
        check_question("q", [turn] * (MAX_HISTORY + 1))
    with pytest.raises(BadQuestion, match="too long"):
        check_question("q", [Turn(question="q", answer="a" * 5000)])


# The demo stand-ins


def test_the_demo_questions_replay_and_cite_only_real_quotes(pool):
    found = 0
    for name, candidate in pool.candidates.items():
        for question, path in demo_questions(name).items():
            found += 1
            answer = ask_candidate(candidate.profile, question, ReplayLLM(path))
            assert answer.problems == [], (name, question)
            assert answer.model.startswith("replay:hand-written placeholder")
            if answer.answered:
                assert answer.evidence, (name, question)
    # Two questions for each of the three candidates the baseline ranks first.
    assert found == 6
    assert len(demo_questions("astrid-holm")) == 2
    assert demo_questions("clara-jensen") == {} and demo_questions(None) == {}


def test_a_demo_question_is_matched_ignoring_case_and_spaces():
    path = DEFAULT_POOL / "astrid-holm" / "ask_production.json"
    assert demo_recording("astrid-holm", PRODUCTION) == path
    asked = "  has this candidate   deployed models to production "
    assert demo_recording("astrid-holm", asked) == path
    assert demo_recording("astrid-holm", "Has she deployed anything?") is None
    assert demo_recording(None, PRODUCTION) is None


def test_every_stand_in_is_listed_to_record():
    listed = (Path(__file__).parents[1] / "docs" / "to-record.md").read_text(
        encoding="utf-8"
    )
    assert "ask_<question>.json" in listed or "ask_production.json" in listed
    assert "uv run unapply ask" in listed


def test_the_command_line_replays_and_refuses_paid_calls(capsys):
    path = DEFAULT_POOL / "sofie-krag" / "ask_team.json"
    assert cli.main(["ask", "sofie-krag", "team", "--replay", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Q: Has this candidate managed a team?" in out
    assert "Answered by the material: no" in out
    assert "Explain forecast uncertainty" in out
    assert cli.main(["ask", "sofie-krag", "production"]) == 3
    assert "paid API call" in capsys.readouterr().err


# The API


@pytest.fixture
def repo():
    init_db()
    repo = Repository.from_url(database_url())
    yield repo
    repo.engine.dispose()


@pytest.fixture
def factory():
    return FakeFactory(
        ModelAnswer(answered=True, answer="Yes, in production.", evidence=["E2", "E77"])
    )


@pytest.fixture
def client(repo, tmp_path, factory):
    app = create_app(repo=repo, uploads=tmp_path / "uploads", llm_factory=factory)
    return TestClient(app)


def ok(response, code=200):
    assert response.status_code == code, response.text
    return response.json()


@pytest.fixture
def shortlist(client):
    """A pool demo job, matched; its name and profile ids by pool folder."""
    job = ok(client.post("/demos/shortlist"), 201)["name"]
    ok(client.post(f"/jobs/{job}/match"))
    candidates = ok(client.get(f"/jobs/{job}/shortlist"))["candidates"]
    ids = {c["contact"] and c["contact"]["name"]: c["profile_id"] for c in candidates}
    assert None in ids  # Nobody is revealed yet.
    ranking = ok(client.get(f"/jobs/{job}/ranking"))["candidates"]
    return job, [c["profile_id"] for c in ranking]


def reveal(client, job, profile_id):
    ok(client.post(f"/jobs/{job}/candidates/{profile_id}/reveal"), 201)


def test_asking_is_refused_before_the_reveal(client, shortlist, factory):
    job, ids = shortlist
    url = f"/jobs/{job}/candidates/{ids[0]}/ask"
    for allow in ("false", "true"):
        response = client.post(f"{url}?allow_api={allow}", json={"question": "Hi?"})
        assert response.status_code == 409
        assert "reveal the candidate" in response.json()["detail"]
    # Not even the demo questions are offered, nor replayed.
    assert client.get(url).status_code == 404
    assert client.post(url, json={"question": PRODUCTION}).status_code == 409
    assert factory.calls == []
    # A candidate who isn't on the job isn't found, revealed or not.
    other = ok(client.post("/demos/shortlist"), 201)["name"]
    assert client.get(f"/jobs/{other}/candidates/{ids[0]}/ask").status_code == 404


def test_a_paid_question_is_refused_unless_allowed(client, shortlist, factory):
    job, ids = shortlist
    reveal(client, job, ids[0])
    url = f"/jobs/{job}/candidates/{ids[0]}/ask"
    response = client.post(url, json={"question": "Has she used Kubernetes?"})
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "paid API call" in detail and "suggested demo questions" in detail
    assert factory.calls == []


def test_an_allowed_question_is_answered_with_checked_citations(
    client, repo, shortlist, factory
):
    job, ids = shortlist
    reveal(client, job, ids[0])
    profile = repo.profile_by_id(UUID(ids[0]))
    earlier = [{"question": "Is she senior?", "answer": "She is a lead."}]
    answer = ok(
        client.post(
            f"/jobs/{job}/candidates/{ids[0]}/ask?allow_api=true",
            json={"question": "Has she used Kubernetes?", "history": earlier},
        )
    )
    assert factory.calls == [("ask", True)]
    assert answer["answered"] and answer["model"] == "fake-model"
    # E2 is hers; E77 isn't, so it is dropped and said so.
    assert [q["quote"] for q in answer["evidence"]] == [profile.evidence[1].quote]
    assert answer["problems"] == [
        "cited ['E77'], which aren't the candidate's; dropped"
    ]
    # The earlier turns sent by the page reach the model; the rubric doesn't.
    prompt = factory.llm.prompts[0]
    assert "<question>Is she senior?</question>" in prompt
    assert "weight" not in prompt and "estimated_level" not in prompt


def test_a_revealed_pool_candidate_has_free_demo_questions(client, repo, shortlist):
    job, ids = shortlist
    reveal(client, job, ids[0])
    profile = repo.profile_by_id(UUID(ids[0]))
    assert repo.candidate_of(UUID(ids[0])) == "pool-astrid-holm"
    url = f"/jobs/{job}/candidates/{ids[0]}/ask"
    suggested = ok(client.get(url))["suggested"]
    assert suggested == [PRODUCTION, "Has this candidate managed a team?"]
    # Replayed without allow_api, so no model is asked for (the factory isn't used).
    answer = ok(client.post(url, json={"question": PRODUCTION.lower()}))
    assert answer["answered"] and answer["model"].startswith("replay:")
    quotes = {e.quote for e in profile.evidence}
    assert answer["evidence"] and all(q["quote"] in quotes for q in answer["evidence"])
    team = ok(client.post(url, json={"question": suggested[1]}))
    assert not team["answered"] and team["answer"].startswith("Nothing in the material")


def test_bad_questions_are_refused(client, shortlist):
    job, ids = shortlist
    reveal(client, job, ids[0])
    url = f"/jobs/{job}/candidates/{ids[0]}/ask?allow_api=true"
    assert client.post(url, json={"question": "   "}).status_code == 422
    assert client.post(url, json={"question": "x" * 1000}).status_code == 422
    turns = [{"question": "q", "answer": "a"}] * (MAX_HISTORY + 1)
    assert client.post(url, json={"question": "q", "history": turns}).status_code == 422


def test_conversations_arent_saved(client, shortlist, tmp_path):
    job, ids = shortlist
    reveal(client, job, ids[0])
    question = "Has she ever worked with satellite telemetry, uniquely?"
    ok(
        client.post(
            f"/jobs/{job}/candidates/{ids[0]}/ask?allow_api=true",
            json={"question": question},
        )
    )
    db = tmp_path / "data" / "unapply.db"
    assert db.is_file()
    stored = b"".join(p.read_bytes() for p in db.parent.glob("unapply.db*"))
    assert question.encode() not in stored
    assert b"Yes, in production." not in stored
