"""Remove names and contact details from text a model or an employer sees.

Profiles don't store the candidate's name or contact details, and extraction is told
to leave them out of quotes, so this is a second line of defence: email addresses,
phone numbers, web addresses and @handles are replaced, and so are any names the
caller knows (such as a GitHub username).
"""

from __future__ import annotations

import re

REDACTED = "[redacted]"

_CONTACTS = [
    # Email addresses.
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # Web addresses, with or without a scheme, such as github.com/johndoe.
    re.compile(
        r"\b(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\."
        r"(?:com|org|net|io|dev|me|dk|se|no|de|eu|co\.uk)/\S*",
        re.IGNORECASE,
    ),
    # @handles, such as @johndoe. Not inside email addresses, which went first.
    re.compile(r"(?<![\w@])@[A-Za-z0-9_-]{2,}"),
]
# Phone numbers: an optional +country code, then digits in groups. Only replaced
# with at least 8 digits that don't look like dates (see `_phone`).
_PHONE = re.compile(
    r"(?<![\w.])\+?\(?\d{1,4}\)?(?:[ .-]?\(?\d{2,4}\)?){2,5}(?!\w|\.\d)"
)


def redact(text: str, names: list[str] | None = None) -> str:
    """Replace contact details and known names in a text.

    Parameters
    ----------
    text : str
        Text from a profile, such as an evidence quote.
    names : list of str or None, optional
        Names to remove, such as the candidate's name or GitHub username. Each is
        matched as a whole word, ignoring case. Names shorter than three
        characters are ignored, so they don't remove ordinary words.

    Returns
    -------
    str
        The text with each match replaced by "[redacted]".
    """
    for pattern in _CONTACTS:
        text = pattern.sub(REDACTED, text)
    text = _PHONE.sub(lambda m: _phone(m.group(0)), text)
    for name in names or []:
        name = name.strip()
        if len(name) >= 3:
            text = re.sub(
                rf"(?<!\w){re.escape(name)}(?!\w)", REDACTED, text, flags=re.IGNORECASE
            )
    return text


def _phone(found: str) -> str:
    """Redact a phone number, but leave dates such as "2019-08-01" alone."""
    digits = re.sub(r"\D", "", found)
    groups = re.findall(r"\d+", found)
    dates = all(len(g) in (2, 4) and _date_like(g) for g in groups)
    # A date has a year; "20 12 15 10" is a phone number, though each part could be
    # a month or day.
    if len(digits) < 8 or (dates and any(len(g) == 4 for g in groups)):
        return found
    return REDACTED


def _date_like(group: str) -> bool:
    n = int(group)
    return 1900 <= n <= 2100 if len(group) == 4 else 1 <= n <= 31
