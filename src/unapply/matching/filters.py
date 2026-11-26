"""Hard filters: pass/fail requirements, checked in plain code before any scoring.

Each filter compares the rubric's `HardFilters` with the candidate's profile and
answers pass, fail or unknown. Unknown means the profile doesn't say (no locations
given, no dated experience): it doesn't exclude the candidate, because excluding
people for missing information is the worse mistake, but it is reported so the
recruiter can see it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from unapply.schemas import Experience, HardFilters, Profile, WorkMode

# EU member states (ISO 3166-1 alpha-2), for "EU" work permits. Greece is "GR" in
# ISO, though the EU itself writes "EL"; both are accepted.
EU_COUNTRIES = frozenset(
    "AT BE BG CY CZ DE DK EE EL ES FI FR GR HR HU IE IT LT LU LV MT NL PL PT RO SE "
    "SI SK".split()
)

# Titles of experience entries that are education, not work, so they don't count
# towards years of experience. A heuristic: the profile doesn't record the kind of
# entry. "Student job" is work and isn't matched.
_EDUCATION = re.compile(
    r"\b(m\.?sc|b\.?sc|b\.?a|m\.?a|mba|ph\.?d|bachelor'?s?|master'?s?|degree|diploma|"
    r"doctorate|exchange semester|high school|gymnasium)\b",
    re.IGNORECASE,
)
_PERSONAL = re.compile(r"\b(personal|side|hobby) project\b", re.IGNORECASE)


class Outcome(StrEnum):
    """What a hard filter concluded."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # The profile doesn't say; not excluded


@dataclass(frozen=True)
class FilterCheck:
    """One hard filter's result for one candidate.

    Parameters
    ----------
    name : str
        "location", "work_mode", "work_permit" or "min_years_experience".
    outcome : Outcome
        Pass, fail or unknown.
    reason : str
        Why, in plain language, for the recruiter.
    """

    name: str
    outcome: Outcome
    reason: str


@dataclass(frozen=True)
class FilterReport:
    """Every hard filter's result for one candidate.

    Parameters
    ----------
    checks : list of FilterCheck
        One per filter the rubric sets; filters it leaves empty aren't listed.
    """

    checks: list[FilterCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Whether no filter failed. Unknown outcomes don't count as failures."""
        return all(c.outcome != Outcome.FAIL for c in self.checks)

    @property
    def failed(self) -> list[FilterCheck]:
        """The filters that failed."""
        return [c for c in self.checks if c.outcome == Outcome.FAIL]


def check_hard_filters(
    profile: Profile, filters: HardFilters, today: date | None = None
) -> FilterReport:
    """Check a candidate against a rubric's hard filters.

    Parameters
    ----------
    profile : Profile
        The candidate's profile; its preferences and experience dates are used.
    filters : HardFilters
        The rubric's hard filters.
    today : date or None, optional
        The date current roles run to, by default today. Set it for reproducible
        results.

    Returns
    -------
    FilterReport
        One check for each filter the rubric sets.
    """
    checks = []
    if filters.work_modes:
        checks.append(_work_mode(profile, filters))
    if filters.locations:
        checks.append(_location(profile, filters))
    if filters.required_work_permits:
        checks.append(_work_permit(profile, filters))
    if filters.min_years_experience is not None:
        checks.append(
            _min_years(profile, filters.min_years_experience, today or date.today())
        )
    return FilterReport(checks)


def _work_mode(profile: Profile, filters: HardFilters) -> FilterCheck:
    wanted = profile.preferences.work_modes
    offered = ", ".join(m.value for m in filters.work_modes)
    if not wanted:
        # The schema defines no work modes as "any".
        return FilterCheck("work_mode", Outcome.PASS, f"Accepts any; job: {offered}.")
    common = [m for m in filters.work_modes if m in wanted]
    if common:
        return FilterCheck("work_mode", Outcome.PASS, f"Both accept {common[0].value}.")
    return FilterCheck(
        "work_mode",
        Outcome.FAIL,
        f"Wants {', '.join(m.value for m in wanted)}; job offers {offered}.",
    )


def _location(profile: Profile, filters: HardFilters) -> FilterCheck:
    wanted = profile.preferences.locations
    job = ", ".join(filters.locations)
    modes = profile.preferences.work_modes
    if WorkMode.REMOTE in filters.work_modes and (
        not modes or WorkMode.REMOTE in modes
    ):
        return FilterCheck(
            "location", Outcome.PASS, f"Remote work is possible; job is in {job}."
        )
    if not wanted:
        return FilterCheck(
            "location", Outcome.UNKNOWN, f"No locations given; job is in {job}."
        )
    for place in wanted:
        for location in filters.locations:
            if same_place(place, location):
                return FilterCheck(
                    "location", Outcome.PASS, f"Wants {place}; job is in {location}."
                )
    return FilterCheck(
        "location", Outcome.FAIL, f"Wants {', '.join(wanted)}; job is in {job}."
    )


def same_place(a: str, b: str) -> bool:
    """Tell whether two place names mean the same place.

    Compares their words, ignoring case and punctuation: one name's words must all
    be in the other's, so "Copenhagen" matches "Copenhagen, Denmark" and "Greater
    Copenhagen". It knows no geography: "Denmark" doesn't match "Copenhagen".

    Parameters
    ----------
    a, b : str
        Place names as written.

    Returns
    -------
    bool
        True if they match.
    """
    words_a, words_b = _words(a), _words(b)
    if not words_a or not words_b:
        return False
    return words_a <= words_b or words_b <= words_a


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _work_permit(profile: Profile, filters: HardFilters) -> FilterCheck:
    held = [p.strip().upper() for p in profile.preferences.work_permits]
    required = [p.strip().upper() for p in filters.required_work_permits]
    if not held:
        return FilterCheck(
            "work_permit",
            Outcome.UNKNOWN,
            f"No work permits given; job requires {', '.join(required)}.",
        )
    missing = [r for r in required if not any(permit_covers(h, r) for h in held)]
    if missing:
        return FilterCheck(
            "work_permit",
            Outcome.FAIL,
            f"May work in {', '.join(held)}; job requires {', '.join(missing)}.",
        )
    return FilterCheck(
        "work_permit",
        Outcome.PASS,
        f"May work in {', '.join(held)}; job requires {', '.join(required)}.",
    )


def permit_covers(held: str, required: str) -> bool:
    """Tell whether a work permit the candidate holds meets one a job requires.

    An "EU" permit (such as EU citizenship) covers "EU" and every member state. A
    member state's permit covers that state, and "EU", which a job sets to mean
    "may work in the EU", where it is. EEA countries and Switzerland aren't
    treated as EU.

    Parameters
    ----------
    held : str
        ISO country code or "EU", uppercase.
    required : str
        ISO country code or "EU", uppercase.

    Returns
    -------
    bool
        True if `held` meets `required`.
    """
    if held == required:
        return True
    if held == "EU":
        return required in EU_COUNTRIES
    return required == "EU" and held in EU_COUNTRIES


def counts_as_work(experience: Experience) -> bool:
    """Tell whether an experience entry counts towards years of work experience.

    Education (degrees, diplomas) and personal projects don't. This is a heuristic
    on the title and organisation, because the profile doesn't record what kind of
    entry it is.

    Parameters
    ----------
    experience : Experience
        The entry.

    Returns
    -------
    bool
        True if it looks like work.
    """
    text = f"{experience.title} {experience.organisation}"
    return not (_EDUCATION.search(experience.title) or _PERSONAL.search(text))


def years_of_experience(profile: Profile, today: date | None = None) -> float | None:
    """Count the years of work in a profile, counting overlapping roles once.

    Dates are month precision: a role from 2019-08 to 2022-02 covers August 2019
    to February 2022, both included (31 months). A role with no end is current and
    runs to `today`'s month. Roles without a start, education and personal
    projects (see `counts_as_work`) aren't counted.

    Parameters
    ----------
    profile : Profile
        The candidate's profile.
    today : date or None, optional
        The date current roles run to, by default today.

    Returns
    -------
    float or None
        Years, as months divided by 12. None if no work entry has a start date.
    """
    today = today or date.today()
    spans = []
    for x in profile.experiences:
        if x.start is None or not counts_as_work(x):
            continue
        end = x.end or today
        first, last = _month(x.start), _month(end)
        if last >= first:
            spans.append((first, last + 1))
    if not spans:
        return None
    months = 0
    current_start, current_end = None, None
    for start, end in sorted(spans):
        if current_end is None or start > current_end:
            if current_end is not None:
                months += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    months += current_end - current_start
    return months / 12


def _month(d: date) -> int:
    """Months since year 0, so consecutive months differ by 1."""
    return d.year * 12 + d.month - 1


def _min_years(profile: Profile, required: int, today: date) -> FilterCheck:
    years = years_of_experience(profile, today)
    if years is None:
        return FilterCheck(
            "min_years_experience",
            Outcome.UNKNOWN,
            f"No dated work experience; job requires {required} years.",
        )
    outcome = Outcome.PASS if years >= required else Outcome.FAIL
    return FilterCheck(
        "min_years_experience",
        outcome,
        f"{years:.1f} years of work; job requires {required}.",
    )
