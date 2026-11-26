"""The database: migrations, saving and loading the schemas, and workspace import.

Uses John Doe and Fjord Grocery, built from their recorded model answers, so every
field the schemas have is filled in somewhere.
"""

import io
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from unapply.app import demo, forms
from unapply.cli import main
from unapply.db.engine import alembic_config, database_url, init_db, make_engine
from unapply.db.models import Base
from unapply.db.repository import NotFound, Repository, RubricLocked
from unapply.estimation.claims import claim_support
from unapply.estimation.skills import estimate_skills, skills_without_estimate
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.interview.questions import select_topics, write_questions
from unapply.interview.sheet import apply_interview_sheet
from unapply.jobs.extract import extract_job
from unapply.jobs.sheet import apply_rubric_sheet, export_rubric_sheet
from unapply.llm import ReplayLLM
from unapply.review import apply_review_sheet
from unapply.schemas import CriterionScore, Match, Profile
from unapply.workspace import Workspace

FIXTURES = Path(__file__).parent / "fixtures"
JOHN = FIXTURES / "john_doe"
FJORD = FIXTURES / "jobs" / "fjord_grocery"


def _estimated(profile: Profile, recording: str) -> Profile:
    names = skills_without_estimate(profile)
    result = estimate_skills(profile, ReplayLLM(JOHN / recording), names)
    return result.profile.model_copy(
        update={"claim_support": claim_support(result.profile)}
    )


@pytest.fixture(scope="module")
def john() -> dict[str, Profile]:
    """John's profile after each step, from material to re-estimated."""
    documents = load_path(JOHN / "material")
    draft = extract_profile(documents, ReplayLLM(JOHN / "extraction.json")).profile
    reviewed = apply_review_sheet(draft, demo.john_review_sheet(draft))
    estimated = _estimated(reviewed, "estimation.json")
    topics = select_topics(estimated)
    questions = write_questions(estimated, topics, ReplayLLM(JOHN / "questions.json"))
    asked = [
        {"skill": q.skill, "reason": q.reason.value, "text": q.text} for q in questions
    ]
    sheet = forms.interview_sheet(estimated, asked, demo.john_answers())
    interviewed, _ = apply_interview_sheet(estimated, sheet)
    return {
        "extracted": draft,
        "reviewed": reviewed,
        "estimated": estimated,
        "interviewed": interviewed,
        "reestimated": _estimated(interviewed, "estimation_after_interview.json"),
        "questions": asked,
    }


@pytest.fixture
def fjord():
    """The Fjord Grocery job, as extracted (rubric version 1, a draft)."""
    ad = (FJORD / "ad.md").read_text(encoding="utf-8")
    return extract_job(ad, ReplayLLM(FJORD / "extraction.json")).job


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    init_db(url)
    repo = Repository.from_url(url)
    yield repo
    repo.engine.dispose()


def _approve(job):
    sheet = export_rubric_sheet(job).replace("approve: false", "approve: true")
    return apply_rubric_sheet(job, sheet)


def _reweighted(job):
    sheet = yaml.safe_load(export_rubric_sheet(job))
    sheet["criteria"][0]["weight"] = 1 if sheet["criteria"][0]["weight"] != 1 else 2
    return apply_rubric_sheet(job, yaml.safe_dump(sheet, allow_unicode=True))


def _match(job, profile_id=None, criteria=None):
    criteria = criteria if criteria is not None else job.rubric.criteria
    return Match(
        job_id=job.id,
        profile_id=profile_id or uuid4(),
        rubric_version=job.rubric.version,
        passed_hard_filters=True,
        criterion_scores=[
            CriterionScore(
                criterion_id=c.id,
                score=0.5,
                rationale="Half met.",
                evidence_ids=[uuid4()],
            )
            for c in criteria
        ],
        model="test",
    )


# Migrations


def test_default_url_is_sqlite_in_the_data_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("UNAPPLY_DATABASE_URL")
    monkeypatch.setenv("UNAPPLY_DATA", "data")
    assert database_url() == "sqlite:///data/unapply.db"
    monkeypatch.setenv("UNAPPLY_DATABASE_URL", "postgresql+psycopg://u@h/unapply")
    assert database_url() == "postgresql+psycopg://u@h/unapply"


def test_migrations_build_the_schema_from_empty(tmp_path):
    url = f"sqlite:///{(tmp_path / 'nested' / 'fresh.db').as_posix()}"
    init_db(url)
    init_db(url)  # Again: nothing to do.
    engine = make_engine(url)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert set(Base.metadata.tables) <= tables
        # The migrations build exactly what the models describe.
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
        head = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
        assert MigrationContext.configure(connection).get_current_revision() == head
    # And they can be undone and redone.
    command.downgrade(alembic_config(url), "base")
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
    engine.dispose()
    init_db(url)


def test_migrations_render_for_postgres(capsys):
    # Offline mode writes the SQL without a server, so this checks that nothing in
    # the migrations is SQLite-only.
    config = alembic_config("postgresql+psycopg://user@localhost/unapply")
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    sql = config.output_buffer.getvalue() + capsys.readouterr().out
    assert "CREATE TABLE candidates" in sql
    assert "UUID" in sql and "JSON" in sql


# Profiles


@pytest.mark.parametrize(
    "step", ["extracted", "reviewed", "estimated", "interviewed", "reestimated"]
)
def test_profiles_load_back_equal(repo, john, step):
    repo.create_candidate("john-doe", demo=True)
    repo.save_profile("john-doe", john[step], step)
    assert repo.profile("john-doe") == john[step]
    assert repo.profile_by_id(john[step].id) == john[step]


def test_the_fixture_fills_every_profile_table(john):
    p = john["reestimated"]
    assert p.claim_support is not None and p.approved_by_candidate_at is not None
    assert any(s.estimate and s.estimate.evidence_ids for s in p.skills)
    assert any(s.self_level and s.category for s in p.skills)
    assert any(x.start and x.evidence_ids and x.skills for x in p.experiences)
    assert p.preferences.salary_min and p.preferences.work_modes


def test_candidates_keep_settings_and_history(repo, john):
    repo.create_candidate("john-doe", demo=True)
    assert repo.candidate_names() == ["john-doe"]
    assert repo.profile("john-doe") is None and repo.history("john-doe") == []
    assert repo.settings("john-doe") == {"demo": True}
    repo.save_settings("john-doe", {"demo": True, "github": "johndoe"})
    assert repo.settings("john-doe")["github"] == "johndoe"
    for step in ("extracted", "reviewed", "estimated"):
        repo.save_profile("john-doe", john[step], step)
    assert repo.history("john-doe") == ["extracted", "reviewed", "estimated"]
    assert repo.profile("john-doe") == john["estimated"]


def test_a_new_profile_replaces_the_old_one(repo, john):
    repo.create_candidate("john-doe")
    repo.save_profile("john-doe", john["reestimated"], "estimated")
    fresh = john["extracted"].model_copy(update={"id": uuid4()})
    repo.save_profile("john-doe", fresh, "extracted")
    assert repo.profile("john-doe") == fresh
    assert repo.profile_by_id(john["reestimated"].id) is None


def test_names_and_ids_are_checked(repo, john):
    repo.create_candidate("john-doe")
    with pytest.raises(ValueError, match="already exists"):
        repo.create_candidate("john-doe")
    with pytest.raises(ValueError, match="lowercase"):
        repo.create_candidate("John Doe")
    with pytest.raises(NotFound):
        repo.profile("jane")
    repo.save_profile("john-doe", john["extracted"], "extracted")
    repo.create_candidate("copy")
    with pytest.raises(ValueError, match="belongs to candidate 'john-doe'"):
        repo.save_profile("copy", john["extracted"], "extracted")
    assert repo.profile("copy") is None and repo.history("copy") == []


def test_interview_questions_and_answers(repo, john):
    repo.create_candidate("john-doe")
    assert repo.pending_questions("john-doe") is None
    repo.save_pending_questions("john-doe", john["questions"])
    assert repo.pending_questions("john-doe") == john["questions"]
    answers = demo.john_answers()
    n = repo.record_answers("john-doe", answers)
    assert n == sum(
        bool(answers.get(q["skill"], "").strip()) for q in john["questions"]
    )
    answered = repo.answered_questions("john-doe")
    assert len(answered) == n
    assert all(a["answer"] == answers[a["skill"]].strip() for a in answered)
    # Skipped ones wait until cleared; answers stay.
    assert len(repo.pending_questions("john-doe")) == len(john["questions"]) - n
    repo.save_pending_questions("john-doe", None)
    assert repo.pending_questions("john-doe") is None
    assert len(repo.answered_questions("john-doe")) == n


# Jobs and matches


def test_jobs_load_back_equal_with_every_rubric_version(repo, fjord):
    repo.create_job("fjord", demo=True)
    assert repo.job("fjord") is None and repo.job_settings("fjord") == {"demo": True}
    approved = _approve(fjord)
    edited = _reweighted(approved)
    assert (fjord.rubric.version, approved.rubric.version) == (1, 1)
    assert edited.rubric.version == 2
    for job, step in ((fjord, "extracted"), (approved, "approved"), (edited, "rubric")):
        repo.save_job("fjord", job, step)
        assert repo.job("fjord") == job
    assert repo.job_by_id(fjord.id) == edited
    assert repo.job_history("fjord") == ["extracted", "approved", "rubric"]
    assert repo.rubric(fjord.id, 1) == approved.rubric
    assert repo.rubric(fjord.id, 2) == edited.rubric
    assert repo.rubric(fjord.id, 3) is None
    assert repo.job_names() == ["fjord"]


def test_matches_load_back_and_lock_their_rubric_version(repo, fjord, john):
    repo.create_job("fjord")
    approved = _approve(fjord)
    repo.save_job("fjord", approved, "approved")
    match = _match(approved, john["reestimated"].id)
    repo.save_match(match)
    assert repo.matches(fjord.id) == [match]
    assert repo.matches(fjord.id, rubric_version=2) == []
    with pytest.raises(ValueError, match="already stored"):
        repo.save_match(match)

    # Version 1 is matched: saving it unchanged is fine, changing it isn't.
    repo.save_job("fjord", approved, "again")
    changed = approved.model_copy(
        update={"rubric": approved.rubric.model_copy(update={"approved_at": None})}
    )
    with pytest.raises(RubricLocked, match="version 1"):
        repo.save_job("fjord", changed, "unapproved")
    assert repo.job("fjord") == approved
    # A new version is fine, and the match still points to version 1.
    edited = _reweighted(approved)
    repo.save_job("fjord", edited, "rubric")
    assert repo.matches(fjord.id)[0].rubric_version == 1
    # Extracting the ad again would orphan the match.
    with pytest.raises(RubricLocked, match="has matches"):
        repo.save_job("fjord", fjord.model_copy(update={"id": uuid4()}), "extracted")


def test_matches_must_fit_their_rubric(repo, fjord):
    repo.create_job("fjord")
    repo.save_job("fjord", fjord, "extracted")
    with pytest.raises(NotFound):
        repo.save_match(_match(fjord).model_copy(update={"rubric_version": 2}))
    other = _reweighted(fjord).rubric.criteria[:1]
    other[0] = other[0].model_copy(update={"id": uuid4()})
    with pytest.raises(ValueError, match="criteria not in rubric version 1"):
        repo.save_match(_match(fjord, criteria=other))
    assert repo.matches(fjord.id) == []


def test_extracting_again_replaces_an_unmatched_job(repo, fjord):
    repo.create_job("fjord")
    repo.save_job("fjord", _reweighted(fjord), "rubric")
    again = fjord.model_copy(update={"id": uuid4()})
    repo.save_job("fjord", again, "extracted")
    assert repo.job("fjord") == again
    assert repo.rubric(fjord.id, 2) is None


# Commands


def _candidate_workspace(base, john):
    ws = Workspace.create("john-doe", base, demo=True)
    for step in ("extracted", "reviewed", "estimated"):
        ws.save_profile(john[step], step)
    ws.save_pending_questions(john["questions"])
    return ws


def _job_workspace(base, fjord):
    ws = Workspace.create("fjord", base / "jobs", demo=True)
    approved = _approve(fjord)
    ws.save_job(fjord, "extracted")
    ws.save_job(approved, "approved")
    ws.save_job(_reweighted(approved), "rubric")
    return ws


def test_db_commands_init_and_import_workspaces(tmp_path, john, fjord, capsys):
    base = tmp_path / "data"
    candidate = _candidate_workspace(base, john)
    job = _job_workspace(base, fjord)
    empty_job = Workspace.create("new-job", base / "jobs")

    assert main(["db", "init"]) == 0
    assert "Database ready: sqlite:///" in capsys.readouterr().out
    assert (base / "unapply.db").exists()  # In the (test's) data folder.
    paths = [str(candidate.root), str(job.root), str(empty_job.root)]
    assert main(["db", "import", *paths]) == 0
    printed = capsys.readouterr().out
    assert "Imported candidate 'john-doe'" in printed
    assert "Imported job 'fjord'" in printed and "Imported job 'new-job'" in printed

    repo = Repository.from_url()
    assert repo.profile("john-doe") == candidate.profile()
    assert repo.history("john-doe") == candidate.history()
    assert repo.settings("john-doe") == {"demo": True}
    assert repo.pending_questions("john-doe") == john["questions"]
    assert repo.job("fjord") == job.job()
    assert repo.job_history("fjord") == job.history()
    approved = job.root / "history" / "002_approved.json"
    approved = json.loads(approved.read_text(encoding="utf-8"))
    assert repo.rubric(fjord.id, 1).model_dump(mode="json") == approved["rubric"]
    assert repo.job("new-job") is None
    repo.engine.dispose()

    # Importing again changes nothing and says why.
    assert main(["db", "import", str(candidate.root)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert main(["db", "import", str(tmp_path)]) == 2
    assert "has no workspace.json" in capsys.readouterr().err


def test_a_broken_workspace_imports_nothing(tmp_path, john):
    ws = _candidate_workspace(tmp_path / "data", john)
    broken = json.loads((ws.root / "profile.json").read_text(encoding="utf-8"))
    broken["skills"][0]["evidence_ids"] = [str(uuid4())]
    (ws.root / "profile.json").write_text(json.dumps(broken), encoding="utf-8")
    assert main(["db", "import", str(ws.root)]) == 2
    repo = Repository.from_url()
    assert repo.candidate_names() == []
    repo.engine.dispose()


def test_naive_local_times_round_trip(repo, john):
    profile = john["extracted"].model_copy(
        update={"approved_by_candidate_at": datetime(2026, 1, 2, 3, 4, 5, 678901)}
    )
    repo.create_candidate("john-doe")
    repo.save_profile("john-doe", profile, "x")
    loaded = repo.profile("john-doe")
    assert loaded.approved_by_candidate_at == datetime(2026, 1, 2, 3, 4, 5, 678901)
