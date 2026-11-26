"""Skill taxonomy tests: synonyms merge, relations are followed. Synthetic data only."""

import json
from pathlib import Path

import pytest
import yaml

from unapply.cli import main
from unapply.db.engine import init_db
from unapply.db.repository import Repository
from unapply.ingest.documents import SourceDocument
from unapply.ingest.extract import (
    ExtractedExperience,
    ExtractedPreferences,
    ExtractedProfile,
    ExtractedQuote,
    ExtractedSkill,
    build_profile,
)
from unapply.jobs.extract import (
    ExtractedCriterion,
    ExtractedFilters,
    ExtractedJob,
    build_job,
)
from unapply.jobs.sheet import apply_rubric_sheet, export_rubric_sheet
from unapply.review import ReviewError, apply_review_sheet, export_review_sheet
from unapply.schemas import (
    Evidence,
    Experience,
    Profile,
    Skill,
    SkillCategory,
    SkillEstimate,
    SkillLevel,
    Source,
    SourceKind,
)
from unapply.taxonomy import (
    DEFAULT_PATH,
    Taxonomy,
    TaxonomyError,
    TaxonomySkill,
    canonical_skill,
    default_taxonomy,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def taxonomy():
    return default_taxonomy()


# The shipped taxonomy


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("radiation therapy planning", "radiotherapy planning"),
        ("Radiation  Therapy Planning", "radiotherapy planning"),
        ("scikit learn", "scikit-learn"),
        ("Sklearn", "scikit-learn"),
        ("scikit_learn", "scikit-learn"),  # "_" and "-" count as spaces.
        ("time-series forecasting", "time series forecasting"),
        ("Apache Spark", "spark"),
        ("K8s", "kubernetes"),
        ("A/B tests", "a/b testing"),
        # Names the taxonomy doesn't know are only normalised.
        (" Open-Source  Contribution ", "open-source contribution"),
    ],
)
def test_synonyms_map_to_the_canonical_name(taxonomy, written, canonical):
    assert taxonomy.canonical(written) == canonical
    assert canonical_skill(written) == canonical


def test_implied_skills_are_found_transitively(taxonomy):
    assert "sql" in taxonomy.implied("dbt")
    assert taxonomy.implied("pytorch") == {
        "python",
        "deep learning",
        "machine learning",
    }
    assert taxonomy.implied("LightGBM") == {"gradient boosting", "machine learning"}
    assert taxonomy.implied("sparse gaussian processes") == {
        "gaussian processes",
        "machine learning",
    }
    assert taxonomy.implied("python") == set()
    assert taxonomy.implied("a skill nobody listed") == set()
    # The reverse: which skills' evidence also counts for SQL or gradient boosting.
    assert {"dbt", "snowflake", "postgresql"} <= taxonomy.supporting("sql")
    assert taxonomy.supporting("gradient boosting") == {
        "lightgbm",
        "xgboost",
        "catboost",
    }
    assert "machine learning" not in taxonomy.supporting("machine learning")


def test_skills_are_found_by_any_name(taxonomy):
    skill = taxonomy.get("radiation therapy planning")
    assert skill.name == "radiotherapy planning"
    assert skill.category is SkillCategory.DOMAIN
    assert taxonomy.get("nothing like it") is None


def test_the_fixtures_already_use_canonical_names(taxonomy):
    """No skill in John Doe's or Fjord Grocery's recordings is renamed or merged.

    The recordings predate the taxonomy; this keeps their expected results valid.
    """
    john = json.loads((FIXTURES / "john_doe" / "extraction.json").read_text("utf-8"))
    names = {s["name"] for s in john["answer"]["skills"]}
    names |= {s for x in john["answer"]["experiences"] for s in x["skills"]}
    job = FIXTURES / "jobs" / "fjord_grocery" / "extraction.json"
    criteria = json.loads(job.read_text("utf-8"))["answer"]["criteria"]
    names |= {c["skill"] for c in criteria if c["skill"]}
    renamed = {n: taxonomy.canonical(n) for n in names if taxonomy.canonical(n) != n}
    assert renamed == {}


# Validation


def _taxonomy(text: str) -> Taxonomy:
    return Taxonomy.from_yaml(text)


def test_a_taxonomy_loads_sorted_and_normalised():
    t = _taxonomy(
        """
skills:
  SQL:
  dbt: {category: technology, synonyms: [Data Build Tool, dbt core, dbt core],
        implies: [sql]}
"""
    )
    assert [s.name for s in t.skills] == ["dbt", "sql"]
    assert t.skills[0].synonyms == ["data build tool", "dbt core"]
    assert t.skills[1].category is None
    assert t.canonical("DATA BUILD TOOL") == "dbt"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("skills: [python]", "needs a `skills` mapping"),
        ("skills: {python: [", "isn't valid YAML"),
        ("skills: {python: {level: 3}}", "Extra inputs are not permitted"),
        ("skills: {python: {category: tool}}", "category"),
        (
            "skills: {pandas: {synonyms: [pd]}, polars: {synonyms: [PD]}}",
            "'pd' names both 'pandas' and 'polars'",
        ),
        ("skills: {scikit-learn: {}, scikit learn: {}}", "names both"),
        ("skills: {dbt: {implies: [sql]}}", "'sql', which isn't a skill"),
        (
            "skills: {sql: {synonyms: [structured query language]}, "
            "dbt: {implies: [structured query language]}}",
            "use its canonical name 'sql'",
        ),
        ("skills: {sql: {implies: [sql]}}", "can't imply or be broader than itself"),
        (
            "skills: {a: {implies: [b]}, b: {broader: [c]}, c: {implies: [a]}}",
            "cycle: a -> b -> c -> a",
        ),
    ],
)
def test_invalid_taxonomies_are_rejected(text, message):
    with pytest.raises(TaxonomyError, match=message):
        _taxonomy(text)


def test_skills_listed_twice_are_rejected():
    with pytest.raises(ValueError, match="more than once"):
        Taxonomy(skills=[TaxonomySkill(name="SQL"), TaxonomySkill(name="sql")])


def test_the_taxonomy_file_can_be_replaced(monkeypatch, tmp_path):
    path = tmp_path / "skills.yaml"
    path.write_text("skills: {python: {synonyms: [snake language]}}", "utf-8")
    monkeypatch.setenv("UNAPPLY_SKILLS", str(path))
    default_taxonomy.cache_clear()
    try:
        assert canonical_skill("Snake Language") == "python"
        monkeypatch.setenv("UNAPPLY_SKILLS", str(tmp_path / "missing.yaml"))
        default_taxonomy.cache_clear()
        with pytest.raises(TaxonomyError, match="no skill taxonomy"):
            default_taxonomy()
    finally:
        monkeypatch.delenv("UNAPPLY_SKILLS")
        default_taxonomy.cache_clear()
    assert default_taxonomy() == Taxonomy.load(DEFAULT_PATH)


# Extraction, review and rubrics

CV = """Skills: Scikit Learn, sklearn, Apache Spark, radiation therapy planning.
Built churn models with scikit-learn at Acme."""


def _q(quote):
    return ExtractedQuote(source="S1", quote=quote)


def test_synonyms_merge_at_extraction():
    skill = ExtractedSkill
    answer = ExtractedProfile(
        headline="Data scientist",
        experiences=[
            ExtractedExperience(
                title="Data Scientist",
                organisation="Acme",
                start="2020",
                end=None,
                summary="Churn models.",
                skills=["Scikit Learn", "scikit-learn", "Apache Spark"],
                evidence=[_q("Built churn models with scikit-learn at Acme.")],
            )
        ],
        skills=[
            skill(
                name="Scikit Learn",
                category="technology",
                self_level=None,
                evidence=[_q("Scikit Learn")],
            ),
            skill(
                name="sklearn",
                category="technology",
                self_level=3,
                evidence=[_q("sklearn"), _q("Built churn models with scikit-learn")],
            ),
            skill(
                name="Radiation therapy planning",
                category="domain",
                self_level=None,
                evidence=[_q("radiation therapy planning")],
            ),
        ],
        preferences=ExtractedPreferences(
            locations=[], work_modes=[], work_permits=[], dealbreakers=[]
        ),
    )
    doc = SourceDocument(source=Source(kind=SourceKind.CV), name="cv.md", text=CV)
    profile = build_profile(answer, [doc]).profile
    assert [s.name for s in profile.skills] == ["radiotherapy planning", "scikit-learn"]
    merged = profile.skill("scikit-learn")
    assert merged.self_level == SkillLevel.WORKING
    assert len(merged.evidence_ids) == 3
    assert profile.experiences[0].skills == ["scikit-learn", "spark"]


def _old_profile() -> Profile:
    """A profile saved before the taxonomy merged "sklearn" into "scikit-learn"."""
    cv = Source(kind=SourceKind.CV)
    a = Evidence(source_id=cv.id, quote="sklearn")
    b = Evidence(source_id=cv.id, quote="Built churn models with scikit-learn")
    estimate = SkillEstimate(level=3, confidence=0.6, rationale="Used.", model="fake")
    return Profile(
        sources=[cv],
        evidence=[a, b],
        experiences=[
            Experience(
                title="Data Scientist",
                organisation="Acme",
                skills=["sklearn"],
                evidence_ids=[b.id],
            )
        ],
        skills=[
            Skill(name="scikit-learn", self_level=4, evidence_ids=[b.id]),
            Skill(name="sklearn", self_level=2, estimate=estimate, evidence_ids=[a.id]),
        ],
    )


def test_synonyms_merge_at_review():
    old = _old_profile()
    reviewed = apply_review_sheet(old, export_review_sheet(old))
    [skill] = reviewed.skills
    assert skill.name == "scikit-learn"
    assert skill.self_level == SkillLevel.ADVANCED  # The higher of the two.
    assert set(skill.evidence_ids) == {e.id for e in old.evidence}
    assert skill.estimate is None  # Estimated again from the combined evidence.
    assert reviewed.experiences[0].skills == ["scikit-learn"]


def test_an_added_synonym_of_a_kept_skill_is_refused():
    old = _old_profile()
    data = yaml.safe_load(export_review_sheet(old))
    data["skills"] = [r for r in data["skills"] if r["name"] == "scikit-learn"]
    data["add_skills"] = [
        {"name": "SKLearn", "category": "technology", "note": "Used it at Acme."}
    ]
    with pytest.raises(ReviewError, match="'scikit-learn' is already in skills"):
        apply_review_sheet(old, yaml.safe_dump(data))
    data["add_skills"][0]["name"] = "Radiation therapy planning"
    reviewed = apply_review_sheet(old, yaml.safe_dump(data))
    assert reviewed.skill("radiotherapy planning") is not None


AD = "Must have: Apache Spark and PySpark. Nice: Spark streaming, sklearn."


def _criterion(skill, quote, kind="must_have"):
    return ExtractedCriterion(
        kind=kind,
        description=f"Knows {skill}",
        skill=skill,
        min_level=3,
        weight=3,
        quote=quote,
    )


def test_synonyms_merge_at_rubric_time():
    answer = ExtractedJob(
        company="Acme",
        title="Data Engineer",
        hard_filters=ExtractedFilters(
            locations=[],
            work_modes=[],
            required_work_permits=[],
            min_years_experience=None,
        ),
        criteria=[
            _criterion("Apache Spark", "Apache Spark"),
            _criterion("spark", "Spark"),  # The same skill again: dropped.
            _criterion("PySpark", "PySpark"),  # A different skill: kept.
            _criterion("spark", "Spark streaming", kind="nice_to_have"),
        ],
    )
    result = build_job(answer, AD)
    rubric = result.job.rubric
    assert [(c.kind, c.skill) for c in rubric.criteria] == [
        ("must_have", "spark"),
        ("must_have", "pyspark"),
        ("nice_to_have", "spark"),
    ]
    assert result.dropped == ["Knows spark (repeats another criterion)"]

    # The recruiter's sheet is canonicalised too.
    data = yaml.safe_load(export_rubric_sheet(result.job))
    data["criteria"][2]["skill"] = "Sklearn"
    edited = apply_rubric_sheet(result.job, yaml.safe_dump(data, sort_keys=False))
    assert edited.rubric.criteria[2].skill == "scikit-learn"


# The database


def test_the_taxonomy_loads_back_equal(taxonomy):
    init_db()
    repo = Repository.from_url()
    assert repo.taxonomy() == Taxonomy()
    repo.save_taxonomy(taxonomy)
    assert repo.taxonomy() == taxonomy
    # Saving again replaces it.
    small = _taxonomy("skills: {sql: {}, dbt: {synonyms: [dbt core], implies: [sql]}}")
    repo.save_taxonomy(small)
    assert repo.taxonomy() == small
    repo.engine.dispose()


def test_db_init_loads_the_taxonomy(taxonomy, capsys):
    assert main(["db", "init"]) == 0
    assert f"{len(taxonomy.skills)} skills from" in capsys.readouterr().out
    repo = Repository.from_url()
    assert repo.taxonomy() == taxonomy
    repo.engine.dispose()
