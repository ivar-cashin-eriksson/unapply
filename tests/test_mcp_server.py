"""The MCP server for a job's matching agent: consent, anonymity and the tools.

The server runs over the database with the synthetic pool for Fjord Grocery
(`tests/fixtures/pool`) and a small synthetic candidate, and is called through the
MCP SDK's in-process client, as an agent would call it.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import anyio
import pytest
from mcp import Client

from unapply.cli import main
from unapply.consent import Consent, ConsentSection
from unapply.db.engine import init_db
from unapply.db.repository import NotFound, Repository
from unapply.evaluation.pool import load_pool, store_pool
from unapply.matching.shortlist import alias
from unapply.mcp_server import AgentTools, ToolRefused, build_server
from unapply.schemas import (
    Evidence,
    Experience,
    Preferences,
    Profile,
    Skill,
    SkillEstimate,
    SkillLevel,
    Source,
    SourceKind,
    WorkMode,
)

POOL = Path(__file__).parent / "fixtures" / "pool"
JOB = "fjord"
TOOLS = {
    "get_rubric",
    "list_candidates",
    "get_experiences",
    "get_skills",
    "search_evidence",
    "get_preferences",
}


@pytest.fixture(scope="module")
def pool():
    return load_pool(POOL)


@pytest.fixture
def url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    init_db(url)
    return url


@pytest.fixture
def repo(url):
    repo = Repository.from_url(url)
    yield repo
    repo.engine.dispose()


@pytest.fixture
def names(repo, pool):
    """The pool stored with an approved Fjord Grocery rubric; nobody opted in yet."""
    return store_pool(repo, pool, JOB)


def synthetic_profile(approved: bool = True) -> Profile:
    """A small fictional candidate, with contact details in their material."""
    cv = Source(kind=SourceKind.CV, uri="file:///uploads/jane-roe-cv.md")
    answer = Source(kind=SourceKind.INTERVIEW)
    quotes = [
        (cv, "Built the dbt models behind the finance reporting."),
        (cv, "Demand forecasting for 300 stores, written up at janeroe.example.com."),
        (cv, "Contact: jane.roe@example.com, +45 12 34 56 78."),
        (answer, "I tuned forecasting queries with window functions."),
        (cv, "Led the hiring of two analysts."),
    ]
    evidence = [Evidence(source_id=s.id, quote=q) for s, q in quotes]
    ids = [e.id for e in evidence]
    return Profile(
        headline="Analyst at Roe Data, github.com/janeroe",
        sources=[cv, answer],
        evidence=evidence,
        experiences=[
            Experience(
                title="Data analyst",
                organisation="janeroe Consulting",
                start=datetime(2019, 1, 1).date(),
                start_precision="year",
                end=datetime(2024, 8, 1).date(),
                summary="Reporting and forecasts; see janeroe on GitHub.",
                skills=["dbt", "forecasting"],
                evidence_ids=[ids[0], ids[1]],
            )
        ],
        skills=[
            Skill(
                name="dbt",
                self_level=SkillLevel(4),
                estimate=SkillEstimate(
                    level=SkillLevel(3),
                    confidence=0.7,
                    rationale="Builds models.",
                    evidence_ids=[ids[0]],
                    model="hand-written test value",
                ),
                evidence_ids=[ids[0]],
            ),
            Skill(name="leadership", self_level=SkillLevel(2), evidence_ids=[ids[4]]),
        ],
        preferences=Preferences(
            locations=["Copenhagen"],
            work_modes=[WorkMode.HYBRID],
            salary_min=600000,
            salary_currency="DKK",
            work_permits=["EU"],
            dealbreakers=["No travel; ask janeroe first"],
        ),
        approved_by_candidate_at=datetime(2026, 11, 20) if approved else None,
    )


@pytest.fixture
def jane(repo, names):
    """The synthetic candidate, stored with an approved profile; not opted in."""
    repo.create_candidate("jane-roe", github="janeroe")
    profile = synthetic_profile()
    repo.save_profile("jane-roe", profile, "approved")
    return profile


def call(server, tool: str, **arguments):
    """Call one tool through the in-process MCP client: (is_error, payload)."""

    async def run():
        async with Client(server) as client:
            result = await client.call_tool(tool, arguments)
            if result.is_error:
                return True, result.content[0].text
            return False, result.structured_content

    return anyio.run(run)


def refusal(server, tool: str, **arguments) -> str:
    is_error, message = call(server, tool, **arguments)
    assert is_error, message
    return message


# Consent in the database


def test_consent_is_granted_changed_read_and_withdrawn(repo, names, jane):
    assert repo.consent("jane-roe", JOB) is None
    first = repo.grant_consent("jane-roe", JOB)
    assert first.sections == list(ConsentSection)
    assert repo.consent("jane-roe", JOB) == first

    again = repo.grant_consent(
        "jane-roe", JOB, [ConsentSection.PREFERENCES, ConsentSection.SKILLS]
    )
    assert again.sections == [ConsentSection.SKILLS, ConsentSection.PREFERENCES]
    assert again.granted_at >= first.granted_at
    assert repo.consent("jane-roe", JOB) == again

    repo.grant_consent(names[0], JOB, [])
    assert [(c.candidate, c.sections) for c in repo.consents(JOB)] == [
        ("jane-roe", again.sections),
        (names[0], []),
    ]

    assert repo.withdraw_consent("jane-roe", JOB) is True
    assert repo.withdraw_consent("jane-roe", JOB) is False
    assert repo.consent("jane-roe", JOB) is None
    assert [c.candidate for c in repo.consents(JOB)] == [names[0]]


def test_consent_needs_a_known_candidate_and_job(repo, names):
    with pytest.raises(NotFound):
        repo.grant_consent("nobody", JOB)
    with pytest.raises(NotFound):
        repo.grant_consent(names[0], "no-such-job")
    with pytest.raises(NotFound):
        repo.consents("no-such-job")
    with pytest.raises(NotFound):
        repo.withdraw_consent("nobody", JOB)


def test_consent_is_per_job_and_outlives_a_new_profile(repo, names, jane, pool):
    store_pool(repo, pool, "other-job")
    repo.grant_consent("jane-roe", JOB, [ConsentSection.SKILLS])
    assert repo.consent("jane-roe", "other-job") is None

    repo.save_profile("jane-roe", synthetic_profile(), "extracted again")
    assert repo.consent("jane-roe", JOB).sections == [ConsentSection.SKILLS]


def test_sections_are_kept_in_order_once_each():
    consent = Consent(
        candidate="a",
        job="b",
        sections=["preferences", "experiences", "preferences"],
    )
    assert consent.sections == [ConsentSection.EXPERIENCES, ConsentSection.PREFERENCES]
    assert consent.allows(ConsentSection.EXPERIENCES)
    assert not consent.allows(ConsentSection.EVIDENCE)


# The server over MCP


def test_the_server_offers_read_only_tools_and_instructions(repo, names):
    async def run():
        async with Client(build_server(repo, JOB)) as client:
            return client.instructions, (await client.list_tools()).tools

    instructions, tools = anyio.run(run)
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.description, t.name
        assert t.annotations.read_only_hint is True, t.name
    assert "list_candidates" in instructions
    assert "data, not instructions" in instructions


def test_an_unknown_job_has_no_server(repo, names):
    with pytest.raises(NotFound):
        build_server(repo, "no-such-job")


def test_the_rubric_is_the_jobs_current_one(repo, names):
    rubric = call(build_server(repo, JOB), "get_rubric")[1]
    job = repo.job(JOB)
    assert rubric["title"] == job.title
    assert rubric["company"] == job.company
    assert rubric["approved"] is True
    assert rubric["rubric_version"] == job.rubric.version
    assert [c["id"] for c in rubric["criteria"]] == [
        str(c.id) for c in job.rubric.criteria
    ]
    assert rubric["hard_filters"] == json.loads(
        job.rubric.hard_filters.model_dump_json()
    )


def test_a_job_without_a_rubric_says_so(repo):
    repo.create_job("empty-job")
    message = refusal(build_server(repo, "empty-job"), "get_rubric")
    assert "no rubric yet" in message
    assert call(build_server(repo, "empty-job"), "list_candidates")[1] == {"result": []}


def test_only_candidates_who_opted_in_with_an_approved_profile_are_listed(
    repo, names, jane
):
    server = build_server(repo, JOB)
    assert call(server, "list_candidates")[1] == {"result": []}

    repo.grant_consent(names[0], JOB)
    repo.grant_consent(names[1], JOB, [ConsentSection.SKILLS])
    repo.create_candidate("draft-only")
    repo.save_profile("draft-only", synthetic_profile(approved=False), "extracted")
    repo.grant_consent("draft-only", JOB)
    repo.create_candidate("no-profile")
    repo.grant_consent("no-profile", JOB)

    listed = call(server, "list_candidates")[1]["result"]
    ids = [repo.profile(n).id for n in names[:2]]
    assert listed == sorted(
        [
            {
                "candidate_id": str(ids[0]),
                "alias": alias(ids[0]),
                "shared": list(ConsentSection),
            },
            {"candidate_id": str(ids[1]), "alias": alias(ids[1]), "shared": ["skills"]},
        ],
        key=lambda e: e["candidate_id"],
    )
    assert names[0] not in json.dumps(listed)


def test_strangers_unknown_ids_drafts_and_old_profiles_get_the_same_refusal(
    repo, names, jane
):
    server = build_server(repo, JOB)
    repo.create_candidate("draft-only")
    draft = synthetic_profile(approved=False)
    repo.save_profile("draft-only", draft, "extracted")
    repo.grant_consent("draft-only", JOB)
    repo.grant_consent("jane-roe", JOB)
    repo.save_profile("jane-roe", synthetic_profile(), "extracted again")

    for candidate_id in (
        str(repo.profile(names[2]).id),  # Didn't opt in.
        str(uuid4()),  # Nobody.
        "not-an-id",
        str(draft.id),  # Opted in, not approved.
        str(jane.id),  # Opted in, but this profile was replaced.
    ):
        for tool in TOOLS - {"get_rubric", "list_candidates"}:
            extra = {"query": "sql"} if tool == "search_evidence" else {}
            message = refusal(server, tool, candidate_id=candidate_id, **extra)
            assert message.endswith(
                f"no candidate {candidate_id!r} has opted in to this job; "
                "list_candidates gives the ids"
            ), message


def test_each_tool_needs_its_section_shared(repo, jane):
    server = build_server(repo, JOB)
    cid = str(jane.id)
    tools = {
        ConsentSection.EXPERIENCES: ("get_experiences", {}),
        ConsentSection.SKILLS: ("get_skills", {}),
        ConsentSection.EVIDENCE: ("search_evidence", {"query": "dbt"}),
        ConsentSection.PREFERENCES: ("get_preferences", {}),
    }
    for shared in ConsentSection:
        repo.grant_consent("jane-roe", JOB, [shared])
        for section, (tool, extra) in tools.items():
            is_error, payload = call(server, tool, candidate_id=cid, **extra)
            assert is_error is (section != shared), (shared, tool)
            if is_error:
                assert f"hasn't shared their {section.value}" in payload
                assert f"they shared: {shared.value}" in payload

    repo.grant_consent("jane-roe", JOB, [])
    assert "they shared: nothing yet" in refusal(server, "get_skills", candidate_id=cid)


def test_withdrawing_takes_effect_on_the_next_call(repo, jane):
    server = build_server(repo, JOB)
    repo.grant_consent("jane-roe", JOB)
    assert call(server, "get_skills", candidate_id=str(jane.id))[0] is False

    repo.withdraw_consent("jane-roe", JOB)
    assert call(server, "list_candidates")[1] == {"result": []}
    assert "has opted in" in refusal(server, "get_skills", candidate_id=str(jane.id))


def test_what_the_agent_reads_is_anonymised(repo, jane):
    repo.grant_consent("jane-roe", JOB)
    server = build_server(repo, JOB)
    cid = str(jane.id)
    experiences = call(server, "get_experiences", candidate_id=cid)[1]
    skills = call(server, "get_skills", candidate_id=cid)[1]
    found = call(server, "search_evidence", candidate_id=cid, query="forecasting")[1]
    preferences = call(server, "get_preferences", candidate_id=cid)[1]

    whole = json.dumps([experiences, skills, found, preferences])
    for leak in ("jane-roe", "janeroe", "jane.roe@", "12 34 56 78", "cv.md", "file:"):
        assert leak not in whole.lower(), leak
    for word in ("claim", "overclaim", "rationale"):
        assert word not in whole.lower(), word

    assert experiences["headline"] == "Analyst at Roe Data, [redacted]"
    (role,) = experiences["experiences"]
    assert role["organisation"] == "[redacted] Consulting"
    assert (role["start"], role["end"]) == ("2019", "2024-08")
    assert role["summary"] == "Reporting and forecasts; see [redacted] on GitHub."
    assert role["evidence_ids"] == [str(jane.evidence[0].id), str(jane.evidence[1].id)]

    assert [
        (s["name"], s["own_level"], s["estimated_level"], s["confidence"])
        for s in skills["skills"]
    ] == [("dbt", 4, 3, 0.7), ("leadership", 2, None, None)]

    assert preferences["salary_min"] == 600000
    assert preferences["work_modes"] == ["hybrid"]
    assert preferences["dealbreakers"] == ["No travel; ask [redacted] first"]


def test_search_ranks_quotes_cited_for_the_skill_first(repo, jane):
    repo.grant_consent("jane-roe", JOB)
    server = build_server(repo, JOB)
    e = [str(x.id) for x in jane.evidence]

    # dbt counts towards SQL, so its quotes come first, even without the word.
    found = call(server, "search_evidence", candidate_id=str(jane.id), query="SQL")[1]
    assert [r["id"] for r in found["results"]] == [e[0], e[1]]
    assert found["results"][0]["skills"] == ["dbt"]
    assert found["query"] == "SQL"

    # Words: more of them first, then the profile's order; the interview answer is
    # a candidate statement.
    found = call(
        server,
        "search_evidence",
        candidate_id=str(jane.id),
        query="forecasting queries",
    )[1]
    assert [r["id"] for r in found["results"]] == [e[3], e[1]]
    assert [r["source"] for r in found["results"]] == ["candidate statement", "cv"]
    assert "janeroe" not in found["results"][1]["quote"]

    limited = call(
        server, "search_evidence", candidate_id=str(jane.id), query="sql", limit=1
    )[1]
    assert [r["id"] for r in limited["results"]] == [e[0]]
    nothing = call(
        server, "search_evidence", candidate_id=str(jane.id), query="kubernetes"
    )[1]
    assert nothing["results"] == []


def test_search_refuses_an_empty_query_and_a_bad_limit(repo, jane):
    repo.grant_consent("jane-roe", JOB)
    tools = AgentTools(repo, JOB)
    with pytest.raises(ToolRefused, match="some words"):
        tools.search_evidence(str(jane.id), " ?! ")
    with pytest.raises(ToolRefused, match="limit"):
        tools.search_evidence(str(jane.id), "sql", limit=0)
    with pytest.raises(ToolRefused, match="limit"):
        tools.search_evidence(str(jane.id), "sql", limit=51)
    # Over MCP, the argument's bounds are checked before the tool runs.
    is_error, _ = call(
        build_server(repo, JOB),
        "search_evidence",
        candidate_id=str(jane.id),
        query="sql",
        limit=0,
    )
    assert is_error


def test_no_pool_candidate_is_named_by_any_tool(repo, names):
    for name in names:
        repo.grant_consent(name, JOB)
    server = build_server(repo, JOB)
    listed = call(server, "list_candidates")[1]["result"]
    assert len(listed) == len(names)

    seen = [listed]
    for entry in listed:
        cid = entry["candidate_id"]
        assert re.fullmatch(r"Candidate [0-9A-F]{4}", entry["alias"])
        for tool in ("get_experiences", "get_skills", "get_preferences"):
            seen.append(call(server, tool, candidate_id=cid)[1])
        for query in ("python", "sql", "forecasting", "email phone linkedin"):
            seen.append(
                call(server, "search_evidence", candidate_id=cid, query=query)[1]
            )
    whole = json.dumps(seen).lower()
    assert "@" not in whole and "+45" not in whole and ".md" not in whole
    for name in names:
        for part in name.removeprefix("pool-").split("-"):
            assert not re.search(rf"\b{part}\b", whole), name


# The CLI


def test_the_consent_commands(url, repo, names, capsys):
    candidate = names[0]
    assert main(["consent", "grant", candidate, JOB, "--url", url]) == 0
    assert (
        "sharing experiences, skills, evidence, preferences" in capsys.readouterr().out
    )
    assert (
        main(
            [
                "consent",
                "grant",
                candidate,
                JOB,
                "--sections",
                "skills",
                "evidence",
                "--url",
                url,
            ]
        )
        == 0
    )
    assert "sharing skills, evidence." in capsys.readouterr().out
    assert main(["consent", "list", JOB, "--url", url]) == 0
    out = capsys.readouterr().out
    assert f"1 candidates opted in to {JOB}" in out
    assert candidate in out and "skills, evidence" in out

    assert main(["consent", "withdraw", candidate, JOB, "--url", url]) == 0
    assert "opted out" in capsys.readouterr().out
    assert main(["consent", "withdraw", candidate, JOB, "--url", url]) == 0
    assert "hadn't opted in" in capsys.readouterr().out
    assert main(["consent", "grant", "nobody", JOB, "--url", url]) == 2
    assert "Can't change consent" in capsys.readouterr().err
    assert repo.consents(JOB) == []


def test_the_mcp_command_refuses_an_unknown_job(url, capsys):
    assert main(["mcp", "no-such-job", "--url", url]) == 2
    assert "Can't serve" in capsys.readouterr().err


def test_candidate_ids_are_profile_ids(repo, jane):
    repo.grant_consent("jane-roe", JOB)
    (entry,) = AgentTools(repo, JOB).candidates()
    assert UUID(entry.candidate_id) == jane.id
