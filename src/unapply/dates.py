"""Dates known to the year or to the month, as CVs give them.

A CV says "2019" or "Aug 2019", rarely a day. Such a date is stored as a `date` on
the first day of the year or month, together with a `DatePrecision`, and written
back the way it was given: "2019" or "2019-08". Without the precision, "2019"
(stored as 1 January) and "2019-01" can't be told apart.
"""

from __future__ import annotations

import re
from datetime import date

from unapply.schemas import DatePrecision

_PATTERN = re.compile(r"\s*(\d{4})(?:-(\d{1,2}))?\s*")


def parse_partial_date(value: str | int | None) -> tuple[date, DatePrecision] | None:
    """Read 'YYYY' or 'YYYY-MM' as a date with its precision.

    Parameters
    ----------
    value : str, int or None
        Such as "2019-08", "2019" or 2019 (YAML reads a bare year as a number).

    Returns
    -------
    tuple of (date, DatePrecision) or None
        The first day of the year or month, and whether it is known to the year or
        the month. None if `value` is None or blank.

    Raises
    ------
    ValueError
        If `value` isn't 'YYYY' or 'YYYY-MM' with a month from 1 to 12.
    """
    if value is None or str(value).strip() == "":
        return None
    m = _PATTERN.fullmatch(str(value))
    if not m or (m.group(2) and not 1 <= int(m.group(2)) <= 12):
        raise ValueError(f"{value!r} isn't YYYY or YYYY-MM")
    year = int(m.group(1))
    if m.group(2) is None:
        return date(year, 1, 1), DatePrecision.YEAR
    return date(year, int(m.group(2)), 1), DatePrecision.MONTH


def format_partial_date(
    value: date | None, precision: DatePrecision = DatePrecision.MONTH
) -> str:
    """Write a date as 'YYYY' or 'YYYY-MM', as precise as it is known.

    Parameters
    ----------
    value : date or None
        The date.
    precision : DatePrecision, optional
        How much of it is known; by default the month.

    Returns
    -------
    str
        Such as "2019" or "2019-08"; empty for None.
    """
    if value is None:
        return ""
    if precision == DatePrecision.YEAR:
        return str(value.year)
    return f"{value:%Y-%m}"
