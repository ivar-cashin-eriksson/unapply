"""A small gazetteer, so that place names can be compared with some geography.

Each country has its English and native names, and its larger cities theirs, so
"København" is Copenhagen and Copenhagen is in Denmark. `place_ids` turns a place as
written into the ids of the places it names; `unapply.matching.filters.same_place`
compares those. Places it doesn't know are compared by their words, as before.

Kept deliberately small and unambiguous: no regions ("Nordics", "Europe"), no
country codes ("IN" and "US" are also words), and no city whose name is a common
word. A city is placed in one country only.
"""

from __future__ import annotations

import re

# Country id (ISO 3166-1 alpha-2, lowercase) -> (names of the country, its cities).
# Every city is a list of names, the first in English.
_COUNTRIES: dict[str, tuple[list[str], list[list[str]]]] = {
    "dk": (
        ["Denmark", "Danmark"],
        [
            ["Copenhagen", "København", "Kobenhavn"],
            ["Aarhus", "Århus"],
            ["Odense"],
            ["Aalborg", "Ålborg"],
            ["Esbjerg"],
            ["Roskilde"],
            ["Kolding"],
            ["Vejle"],
            ["Horsens"],
            ["Randers"],
            ["Herning"],
            ["Silkeborg"],
            ["Billund"],
            ["Lyngby", "Kongens Lyngby"],
            ["Frederiksberg"],
        ],
    ),
    "se": (
        ["Sweden", "Sverige"],
        [
            ["Stockholm"],
            ["Gothenburg", "Göteborg", "Goteborg"],
            ["Malmö", "Malmo"],
            ["Uppsala"],
            ["Lund"],
            ["Linköping", "Linkoping"],
            ["Helsingborg"],
        ],
    ),
    "no": (
        ["Norway", "Norge"],
        [["Oslo"], ["Bergen"], ["Trondheim"], ["Stavanger"]],
    ),
    "fi": (
        ["Finland", "Suomi"],
        [["Helsinki", "Helsingfors"], ["Espoo"], ["Tampere"], ["Turku", "Åbo"]],
    ),
    "is": (["Iceland", "Ísland"], [["Reykjavik", "Reykjavík"]]),
    "de": (
        ["Germany", "Deutschland"],
        [
            ["Berlin"],
            ["Hamburg"],
            ["Munich", "München", "Muenchen"],
            ["Cologne", "Köln", "Koeln"],
            ["Frankfurt"],
            ["Stuttgart"],
            ["Düsseldorf", "Dusseldorf"],
            ["Leipzig"],
        ],
    ),
    "nl": (
        ["Netherlands", "The Netherlands", "Nederland", "Holland"],
        [
            ["Amsterdam"],
            ["Rotterdam"],
            ["The Hague", "Den Haag"],
            ["Utrecht"],
            ["Eindhoven"],
        ],
    ),
    "be": (
        ["Belgium", "België", "Belgique"],
        [["Brussels", "Bruxelles", "Brussel"], ["Antwerp", "Antwerpen"], ["Ghent"]],
    ),
    "fr": (
        ["France"],
        [["Paris"], ["Lyon"], ["Marseille"], ["Toulouse"], ["Bordeaux"]],
    ),
    "es": (
        ["Spain", "España"],
        [["Madrid"], ["Barcelona"], ["Valencia"], ["Seville", "Sevilla"]],
    ),
    "pt": (["Portugal"], [["Lisbon", "Lisboa"], ["Porto"]]),
    "it": (
        ["Italy", "Italia"],
        [["Rome", "Roma"], ["Milan", "Milano"], ["Turin", "Torino"]],
    ),
    "at": (["Austria", "Österreich"], [["Vienna", "Wien"], ["Graz"]]),
    "ch": (
        ["Switzerland", "Schweiz", "Suisse"],
        [["Zurich", "Zürich"], ["Geneva", "Genève"], ["Basel"], ["Lausanne"]],
    ),
    "pl": (
        ["Poland", "Polska"],
        [
            ["Warsaw", "Warszawa"],
            ["Kraków", "Krakow", "Cracow"],
            ["Wrocław", "Wroclaw"],
        ],
    ),
    "ee": (["Estonia", "Eesti"], [["Tallinn"], ["Tartu"]]),
    "cz": (["Czechia", "Czech Republic"], [["Prague", "Praha"], ["Brno"]]),
    "ie": (["Ireland", "Éire"], [["Dublin"], ["Cork"]]),
    "gb": (
        ["United Kingdom", "UK", "Great Britain"],
        [
            ["London"],
            ["Manchester"],
            ["Edinburgh"],
            ["Cambridge"],
            ["Oxford"],
            ["Bristol"],
        ],
    ),
    "us": (
        ["United States", "USA", "United States of America"],
        [["New York", "New York City", "NYC"], ["San Francisco"], ["Seattle"]],
    ),
    "in": (
        ["India"],
        [
            ["Bengaluru", "Bangalore"],
            ["Mumbai", "Bombay"],
            ["Delhi", "New Delhi"],
            ["Hyderabad"],
            ["Pune"],
            ["Chennai"],
        ],
    ),
}


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _build() -> dict[tuple[str, ...], frozenset[str]]:
    names: dict[tuple[str, ...], frozenset[str]] = {}
    for code, (country_names, cities) in _COUNTRIES.items():
        country = f"country:{code}"
        for name in country_names:
            names[tuple(_words(name))] = frozenset({country})
        for city in cities:
            ids = frozenset({f"city:{code}:{_words(city[0])[0]}", country})
            for name in city:
                names[tuple(_words(name))] = ids
    return names


_NAMES = _build()
_LONGEST = max(len(name) for name in _NAMES)


def place_ids(text: str) -> set[str]:
    """Read the places a place name, as written, refers to.

    Known names (the longest first) become the ids of what they name: a country
    its own, a city its own and its country's. Other words stay as they are,
    casefolded, so unknown places can still be compared by their words.

    Parameters
    ----------
    text : str
        A place name as written, such as "København" or "Greater Copenhagen".

    Returns
    -------
    set of str
        Ids such as "country:dk" and "city:dk:copenhagen", and the other words.
        Empty for a text without words.

    Examples
    --------
    >>> sorted(place_ids("Copenhagen, Denmark"))
    ['city:dk:copenhagen', 'country:dk']
    >>> sorted(place_ids("Greater København"))
    ['city:dk:copenhagen', 'country:dk', 'greater']
    """
    words = _words(text)
    ids: set[str] = set()
    i = 0
    while i < len(words):
        for n in range(min(_LONGEST, len(words) - i), 0, -1):
            found = _NAMES.get(tuple(words[i : i + n]))
            if found:
                ids |= found
                i += n
                break
        else:
            ids.add(words[i])
            i += 1
    return ids
