"""Ingestion tests. Synthetic data only; the model is faked."""

import json
import zipfile
from datetime import date

import pytest

from unapply.ingest.documents import SourceDocument, load_path
from unapply.ingest.extract import (
    ExtractedExperience,
    ExtractedPreferences,
    ExtractedProfile,
    ExtractedQuote,
    ExtractedSkill,
    build_profile,
    extract_profile,
    render_sources,
)
from unapply.ingest.github import cached_fetcher, fetch_github
from unapply.schemas import SkillCategory, SkillLevel, Source, SourceKind

CV = """Alex Example - alex@example.com
Senior Data Engineer, Acme Corp 2021–now
• Built Kafka pipelines processing 5M events/day.
• Mentored two junior engineers.
Skills: Python, Kafka, SQL. Languages: Danish (fluent)."""


class FakeLLM:
    model = "fake"

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def parse(self, *, system, prompt, output_type):
        self.calls.append((system, prompt))
        assert output_type is ExtractedProfile
        return self.answer


def _doc(text=CV, kind=SourceKind.CV):
    return SourceDocument(source=Source(kind=kind), name="cv.pdf", text=text)


def _q(quote, source="S1"):
    return ExtractedQuote(source=source, quote=quote)


def _answer(experiences=(), skills=()):
    return ExtractedProfile(
        headline="Data engineer",
        experiences=list(experiences),
        skills=list(skills),
        preferences=ExtractedPreferences(
            locations=["Copenhagen"],
            work_modes=["hybrid"],
            work_permits=[],
            dealbreakers=[],
        ),
    )


def _skill(name, *quotes, level=None, category="technology"):
    return ExtractedSkill(
        name=name, category=category, self_level=level, evidence=list(quotes)
    )


def test_quotes_match_despite_dash_case_and_whitespace_differences():
    exp = ExtractedExperience(
        title="Senior Data Engineer",
        organisation="Acme Corp",
        start="2021",
        end=None,
        summary="Data pipelines.",
        skills=["Kafka", " python "],
        # En dash in the source, hyphen and extra spaces here.
        evidence=[_q("senior data engineer, acme corp   2021-now")],
    )
    result = build_profile(_answer([exp]), [_doc()])
    [x] = result.profile.experiences
    assert x.start == date(2021, 1, 1) and x.end is None
    assert x.skills == ["kafka", "python"]
    assert result.rejected_quotes == []


def test_invented_quotes_are_rejected_and_unsupported_claims_dropped():
    skills = [
        _skill("Kafka", _q("Built Kafka pipelines processing 5M events/day.")),
        _skill("Kubernetes", _q("Ran Kubernetes clusters in production")),
        _skill("Rust", _q("Python, Kafka", source="S9")),
    ]
    result = build_profile(_answer(skills=skills), [_doc()])
    assert [s.name for s in result.profile.skills] == ["kafka"]
    assert len(result.rejected_quotes) == 2
    assert result.unsupported == ["skill: Kubernetes", "skill: Rust"]


def test_duplicate_skills_merge_and_shared_quotes_become_one_evidence():
    quote = _q("Skills: Python, Kafka, SQL.")
    skills = [
        _skill("Python", quote),
        _skill("python", quote, level=4),
        _skill("SQL", quote),
    ]
    result = build_profile(_answer(skills=skills), [_doc()])
    python = result.profile.skill("python")
    assert python.self_level == SkillLevel.ADVANCED
    assert python.category == SkillCategory.TECHNOLOGY
    assert len(python.evidence_ids) == 1
    assert len(result.profile.evidence) == 1


def test_self_level_outside_scale_is_ignored():
    skills = [_skill("Danish", _q("Danish (fluent)"), level=9)]
    result = build_profile(_answer(skills=skills), [_doc()])
    assert result.profile.skill("danish").self_level is None


def test_extract_profile_sends_sources_and_prompt():
    llm = FakeLLM(_answer(skills=[_skill("SQL", _q("SQL"))]))
    result = extract_profile([_doc()], llm)
    system, prompt = llm.calls[0]
    assert "verbatim" in system
    assert prompt.startswith('<source id="S1" kind="cv" name="cv.pdf">')
    assert result.profile.skill("sql") is not None


def test_extract_profile_needs_documents():
    with pytest.raises(ValueError):
        extract_profile([], FakeLLM(_answer()))


def test_render_sources_numbers_from_one():
    out = render_sources([_doc("a"), _doc("b", SourceKind.GITHUB)])
    assert '<source id="S2" kind="github"' in out


def test_load_path_reads_text_files_and_skips_unknown(tmp_path):
    (tmp_path / "notes.md").write_text("I like Python.", encoding="utf-8")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
    [doc] = load_path(tmp_path)
    assert doc.source.kind == SourceKind.FREE_TEXT
    assert doc.text == "I like Python."


def test_load_path_reads_linkedin_export_zip(tmp_path):
    export = tmp_path / "Basic_LinkedInDataExport.zip"
    with zipfile.ZipFile(export, "w") as zf:
        zf.writestr(
            "Positions.csv", "Company Name,Title,Started On\nAcme,Engineer,Jan 2021\n"
        )
        zf.writestr("Skills.csv", "Name\nPython\nKafka\n")
        zf.writestr("Empty.csv", "Name\n")
    [doc] = load_path(export)
    assert doc.source.kind == SourceKind.LINKEDIN
    assert (
        "## Positions\nCompany Name: Acme; Title: Engineer; Started On: Jan 2021"
        in doc.text
    )
    assert "Name: Kafka" in doc.text
    assert "Empty" not in doc.text


def test_fetch_github_skips_forks_and_handles_missing_readme():
    repos = [
        {
            "name": "tool",
            "fork": False,
            "language": "Python",
            "description": "A tool",
            "html_url": "https://github.com/u/tool",
            "pushed_at": "2025-03-01T00:00:00Z",
        },
        {"name": "forked", "fork": True},
        {"name": "bare", "fork": False},
    ]

    def fetch(path, raw):
        if path.startswith("/users/"):
            return json.loads(json.dumps(repos))
        if path == "/repos/u/tool/readme":
            return "# Tool\nDoes things."
        raise FileNotFoundError(path)

    doc = fetch_github("u", fetch=fetch)
    assert doc.source.kind == SourceKind.GITHUB
    assert "## tool" in doc.text and "Primary language: Python" in doc.text
    assert "### README\n# Tool\nDoes things." in doc.text
    assert "## bare" in doc.text and "forked" not in doc.text


def test_cached_fetcher_fetches_each_path_once_including_missing(tmp_path):
    calls = []

    def fetch(path, raw):
        calls.append(path)
        if path == "/missing":
            raise FileNotFoundError(path)
        return {"path": path}

    for _ in range(2):
        cached = cached_fetcher(tmp_path, fetch)
        assert cached("/a", False) == {"path": "/a"}
        with pytest.raises(FileNotFoundError):
            cached("/missing", True)
    assert calls == ["/a", "/missing"]


def test_linkedin_export_keeps_profile_data_and_drops_private_data(tmp_path):
    export = tmp_path / "export.zip"
    with zipfile.ZipFile(export, "w") as zf:
        zf.writestr("Positions.csv", "Company Name,Title\nAcme,Engineer\n")
        zf.writestr(
            "Profile.csv",
            "First Name,Last Name,Address,Headline,Geo Location\n"
            "Alex,Example,1 Secret Street,Data engineer,Copenhagen\n",
        )
        zf.writestr("messages.csv", "FROM,CONTENT\nSam Other,private message\n")
        zf.writestr("Connections.csv", "First Name,Last Name\nSam,Other\n")
        zf.writestr("PhoneNumbers.csv", "Number\n+45 00000000\n")
        zf.writestr(
            "Endorsement_Received_Info.csv",
            "Skill Name,Endorser First Name,Endorser Last Name,Endorsement Status\n"
            "Python,Sam,Other,ACCEPTED\nPython,Kim,Third,ACCEPTED\n"
            "Kafka,Sam,Other,REJECTED\n",
        )
        zf.writestr(
            "Learning.csv",
            "Content Title,Content Type,Content Completed At (if completed)\n"
            "Intro to Rust,Course,2025-01-02\nUnfinished Thing,Course,\n",
        )
    [doc] = load_path(export)
    assert "Headline: Data engineer; Geo Location: Copenhagen" in doc.text
    assert "## Endorsements received (per skill)\nPython: 2" in doc.text
    assert "Intro to Rust (Course), completed 2025-01-02" in doc.text
    for private in [
        "Alex",
        "Secret Street",
        "Sam",
        "Kim",
        "private message",
        "+45",
        "Kafka",
        "Unfinished",
    ]:
        assert private not in doc.text
