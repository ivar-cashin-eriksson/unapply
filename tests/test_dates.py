"""Dates known to the year or to the month, from extraction to display. Synthetic."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from unapply.app import forms
from unapply.dates import format_partial_date, parse_partial_date
from unapply.db.engine import init_db
from unapply.db.repository import Repository
from unapply.estimation.skills import render_roles
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.jobs.extract import extract_job
from unapply.llm import ReplayLLM
from unapply.matching.llm_scorer import render_match_prompt
from unapply.matching.shortlist import anonymous_candidate
from unapply.review import ReviewError, apply_review_sheet, export_review_sheet
from unapply.schemas import DatePrecision, Experience, Profile

FIXTURES = Path(__file__).parent / "fixtures"
JOHN = FIXTURES / "john_doe"
YEAR, MONTH = DatePrecision.YEAR, DatePrecision.MONTH


@pytest.fixture(scope="module")
def john() -> Profile:
    """John's draft: "2018-01" to "2019-07" at Kestrel, "2017" to "2019" for his MSc."""
    documents = load_path(JOHN / "material")
    return extract_profile(documents, ReplayLLM(JOHN / "extraction.json")).profile


def _by_title(profile: Profile, start: str) -> Experience:
    return next(x for x in profile.experiences if x.title.startswith(start))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2019", (date(2019, 1, 1), YEAR)),
        (2019, (date(2019, 1, 1), YEAR)),
        ("2019-01", (date(2019, 1, 1), MONTH)),
        (" 2019-8 ", (date(2019, 8, 1), MONTH)),
        ("", None),
        (None, None),
    ],
)
def test_parse_partial_date(text, expected):
    assert parse_partial_date(text) == expected


@pytest.mark.parametrize("text", ["2019-13", "2019-00", "Aug 2019", "19", "2019-08-01"])
def test_parse_partial_date_refuses_other_forms(text):
    with pytest.raises(ValueError, match="YYYY or YYYY-MM"):
        parse_partial_date(text)


def test_format_partial_date_writes_only_what_is_known():
    assert format_partial_date(date(2019, 1, 1), YEAR) == "2019"
    assert format_partial_date(date(2019, 1, 1), MONTH) == "2019-01"
    assert format_partial_date(date(2019, 8, 1)) == "2019-08"
    assert format_partial_date(None, YEAR) == ""


def test_extraction_keeps_the_precision_the_model_gave(john):
    kestrel = _by_title(john, "Data Analyst")
    assert (kestrel.start, kestrel.start_precision) == (date(2018, 1, 1), MONTH)
    assert (kestrel.end, kestrel.end_precision) == (date(2019, 7, 1), MONTH)
    msc = _by_title(john, "MSc")
    assert (msc.start, msc.start_precision) == (date(2017, 1, 1), YEAR)
    assert (msc.end, msc.end_precision) == (date(2019, 1, 1), YEAR)


def test_unreadable_model_dates_are_unknown_and_a_bad_month_keeps_the_year():
    from unapply.ingest.extract import _parse_date

    assert _parse_date("2019-13") == (date(2019, 1, 1), YEAR)
    assert _parse_date("sometime") == (None, MONTH)
    assert _parse_date(None) == (None, MONTH)


def test_review_sheet_shows_january_as_a_month_and_a_year_as_a_year(john):
    sheet = yaml.safe_load(export_review_sheet(john))
    rows = {r["title"]: r for r in sheet["experiences"]}
    assert rows["Data Analyst (student job)"]["start"] == "2018-01"
    assert rows["MSc in Business Analytics"]["start"] == 2017
    assert rows["MSc in Business Analytics"]["end"] == 2019
    assert apply_review_sheet(john, export_review_sheet(john)) == john.model_copy(
        update={"approved_by_candidate_at": None}
    )


def test_review_edits_set_the_precision(john):
    sheet = yaml.safe_load(export_review_sheet(john))
    for row in sheet["experiences"]:
        if row["title"] == "MSc in Business Analytics":
            row["start"], row["end"] = "2017-09", 2019
        if row["title"] == "Data Analyst (student job)":
            row["start"] = 2018
    reviewed = apply_review_sheet(john, yaml.safe_dump(sheet))
    msc = _by_title(reviewed, "MSc")
    assert (msc.start, msc.start_precision) == (date(2017, 9, 1), MONTH)
    assert msc.end_precision == YEAR
    kestrel = _by_title(reviewed, "Data Analyst")
    assert (kestrel.start, kestrel.start_precision) == (date(2018, 1, 1), YEAR)
    assert kestrel.end_precision == MONTH


def test_review_refuses_a_date_it_cannot_read(john):
    sheet = yaml.safe_load(export_review_sheet(john))
    sheet["experiences"][0]["start"] = "March 2022"
    with pytest.raises(ReviewError, match="isn't YYYY or YYYY-MM"):
        apply_review_sheet(john, yaml.safe_dump(sheet))


def test_dates_known_to_the_year_are_compared_by_year():
    # "Aug 2019 to 2019" is in order; stored as 1 January, the end looked earlier.
    x = Experience(
        title="Intern",
        organisation="Acme",
        start=date(2019, 8, 1),
        end=date(2019, 1, 1),
        end_precision=YEAR,
    )
    assert x.end_precision == YEAR
    with pytest.raises(ValueError, match="ends before it starts"):
        Experience(title="Intern", organisation="Acme", start=date(2019, 8, 1),
                   end=date(2019, 1, 1))  # fmt: skip
    with pytest.raises(ValueError, match="ends before it starts"):
        Experience(title="Intern", organisation="Acme", start=date(2019, 8, 1),
                   end=date(2018, 1, 1), end_precision=YEAR)  # fmt: skip


def test_the_app_and_the_prompts_write_dates_as_known(john):
    rows = {r["title"]: r for r in forms.experience_rows(john)}
    assert rows["Data Analyst (student job)"]["start"] == "2018-01"
    assert rows["MSc in Business Analytics"]["start"] == "2017"
    assert forms.period(_by_title(john, "MSc")) == "2017 to 2019"
    assert forms.period(_by_title(john, "Data Analyst")) == "2018-01 to 2019-07"
    assert "2017 to 2019" in render_roles(john)

    ad = (FIXTURES / "jobs" / "fjord_grocery" / "ad.md").read_text(encoding="utf-8")
    rubric = extract_job(
        ad, ReplayLLM(FIXTURES / "jobs" / "fjord_grocery" / "extraction.json")
    ).job.rubric
    prompt, _, _ = render_match_prompt(john, rubric)
    assert 'from="2017" to="2019"' in prompt
    assert 'from="2018-01" to="2019-07"' in prompt
    shortlisted = anonymous_candidate(john, rubric)
    msc = next(x for x in shortlisted.experiences if x.title.startswith("MSc"))
    assert (msc.start_precision, msc.end_precision) == (YEAR, YEAR)


def test_precision_survives_the_database(john, tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    init_db(url)
    repo = Repository.from_url(url)
    try:
        repo.create_candidate("john")
        repo.save_profile("john", john, "extracted")
        loaded = repo.profile("john")
    finally:
        repo.engine.dispose()
    assert loaded == john
    assert _by_title(loaded, "MSc").start_precision == YEAR
