"""The skill taxonomy: canonical skill names, their synonyms and how skills relate.

Candidates, models and recruiters name the same skill differently ("radiation therapy
planning" and "radiotherapy planning", "sklearn" and "scikit-learn"). The taxonomy in
`config/skills.yaml` gives each skill one canonical name, and `canonical_skill` maps
every synonym to it, so a skill extracted from a CV, added in a review or asked for in
a rubric ends up under the same name. Names the taxonomy doesn't know are kept, only
lowercased with single spaces.

It also records two relations, used when matching (a criterion asks for one skill and
the candidate shows another):

- **implies**: using one skill means using the other. "dbt" implies "sql", "pytorch"
  implies "deep learning".
- **broader**: one skill is a kind of the other. "lightgbm" is a kind of "gradient
  boosting".

Both point from the specific skill to the general one, and both carry evidence the
same way: evidence for "lightgbm" is some evidence for "gradient boosting", not the
other way round. `Taxonomy.implied` follows them, transitively.
"""

from __future__ import annotations

import functools
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from unapply.schemas import SkillCategory

SKILLS_FILE = "UNAPPLY_SKILLS"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "skills.yaml"


class TaxonomyError(ValueError):
    """The taxonomy is invalid. The message says what to fix."""


def normalise_skill_name(name: str) -> str:
    """Lowercase a skill name and collapse its whitespace, without the taxonomy.

    Parameters
    ----------
    name : str
        Skill name as written, such as " Scikit-Learn ".

    Returns
    -------
    str
        The name lowercased with single spaces, such as "scikit-learn".
    """
    return " ".join(name.lower().split())


def _key(name: str) -> str:
    """Look-up key: also treats "-" and "_" as spaces, so "time-series" is found."""
    return " ".join(re.sub(r"[-_]", " ", name.lower()).split())


class TaxonomySkill(BaseModel):
    """One canonical skill in the taxonomy.

    Parameters
    ----------
    name : str
        Canonical name, lowercase, such as "scikit-learn".
    category : SkillCategory or None
        What kind of skill it is, if the taxonomy says.
    synonyms : list of str
        Other names for the same skill, such as "sklearn". Merged into `name`.
    implies : list of str
        Canonical names of skills that using this one means using, such as "sql" for
        "dbt".
    broader : list of str
        Canonical names of skills this one is a kind of, such as "gradient boosting"
        for "lightgbm".
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    category: SkillCategory | None = None
    synonyms: list[str] = Field(default_factory=list)
    implies: list[str] = Field(default_factory=list)
    broader: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = normalise_skill_name(v)
        if not v:
            raise ValueError("a skill needs a name")
        return v

    @field_validator("synonyms", "implies", "broader")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        # Sorted and without repeats, so a taxonomy loaded from the database is equal
        # to the one it was saved from.
        return sorted({normalise_skill_name(x) for x in v if x.strip()})


class Taxonomy(BaseModel):
    """Canonical skills with their synonyms and relations.

    Parameters
    ----------
    skills : list of TaxonomySkill
        Every canonical skill, sorted by name once loaded.

    Raises
    ------
    ValueError
        If two skills share a name or synonym, a relation points to a skill that
        isn't in the taxonomy (or to a synonym rather than the canonical name) or to
        the skill itself, or relations form a cycle.
    """

    skills: list[TaxonomySkill] = Field(default_factory=list)

    _by_key: dict[str, str] = PrivateAttr(default_factory=dict)
    _up: dict[str, list[str]] = PrivateAttr(default_factory=dict)

    @field_validator("skills")
    @classmethod
    def _sorted(cls, v: list[TaxonomySkill]) -> list[TaxonomySkill]:
        return sorted(v, key=lambda s: s.name)

    @model_validator(mode="after")
    def _consistent(self) -> Taxonomy:
        by_key: dict[str, str] = {}
        counts = Counter(s.name for s in self.skills)
        twice = sorted(name for name, n in counts.items() if n > 1)
        if twice:
            raise ValueError(f"skills listed more than once: {twice}")
        names = set(counts)
        for s in self.skills:
            for alias in [s.name, *s.synonyms]:
                other = by_key.setdefault(_key(alias), s.name)
                if other != s.name:
                    raise ValueError(
                        f"{alias!r} names both {other!r} and {s.name!r}; "
                        "a name or synonym can belong to only one skill"
                    )
        up: dict[str, list[str]] = {}
        for s in self.skills:
            for target in s.implies + s.broader:
                if target == s.name:
                    raise ValueError(
                        f"{s.name!r} can't imply or be broader than itself"
                    )
                if target not in names:
                    known = by_key.get(_key(target))
                    hint = f"; use its canonical name {known!r}" if known else ""
                    raise ValueError(
                        f"{s.name!r} refers to {target!r}, which isn't a skill in "
                        f"the taxonomy{hint}"
                    )
            up[s.name] = sorted(set(s.implies + s.broader))
        cycle = _find_cycle(up)
        if cycle:
            raise ValueError(
                f"skills imply each other in a cycle: {' -> '.join(cycle)}"
            )
        self._by_key = by_key
        self._up = up
        return self

    @classmethod
    def from_yaml(cls, text: str) -> Taxonomy:
        """Read a taxonomy in the format of `config/skills.yaml`.

        The file has one mapping, `skills`, from each canonical name to its optional
        `category`, `synonyms`, `implies` and `broader`.

        Parameters
        ----------
        text : str
            The YAML text.

        Returns
        -------
        Taxonomy
            The taxonomy.

        Raises
        ------
        TaxonomyError
            If the text isn't valid YAML in that format, or the taxonomy is invalid.
        """
        try:
            data: Any = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise TaxonomyError(f"the taxonomy isn't valid YAML: {e}") from e
        skills = data.get("skills") if isinstance(data, dict) else None
        if not isinstance(skills, dict):
            raise TaxonomyError("the taxonomy needs a `skills` mapping")
        try:
            return cls(
                skills=[
                    TaxonomySkill(name=str(name), **(fields or {}))
                    for name, fields in skills.items()
                ]
            )
        except (ValidationError, TypeError) as e:
            raise TaxonomyError(f"invalid taxonomy: {e}") from e

    @classmethod
    def load(cls, path: Path) -> Taxonomy:
        """Read a taxonomy file.

        Parameters
        ----------
        path : Path
            A YAML file in the format of `config/skills.yaml`.

        Returns
        -------
        Taxonomy
            The taxonomy.

        Raises
        ------
        TaxonomyError
            If the file is invalid; the message names the file.
        """
        try:
            return cls.from_yaml(path.read_text(encoding="utf-8"))
        except TaxonomyError as e:
            raise TaxonomyError(f"{path}: {e}") from e

    def canonical(self, name: str) -> str:
        """Map a skill name to its canonical name.

        Parameters
        ----------
        name : str
            A skill name as written, such as "Radiation Therapy Planning".

        Returns
        -------
        str
            The canonical name if the name or one of its synonyms is in the taxonomy
            ("-" and "_" count as spaces), such as "radiotherapy planning"; otherwise
            the name lowercased with single spaces.
        """
        return self._by_key.get(_key(name), normalise_skill_name(name))

    def get(self, name: str) -> TaxonomySkill | None:
        """Look up a skill by any of its names.

        Parameters
        ----------
        name : str
            Canonical name or synonym.

        Returns
        -------
        TaxonomySkill or None
            The skill, or None if the taxonomy doesn't know it.
        """
        canonical = self._by_key.get(_key(name))
        return next((s for s in self.skills if s.name == canonical), None)

    def implied(self, name: str) -> set[str]:
        """Find every skill a skill implies or is a kind of, directly or not.

        Parameters
        ----------
        name : str
            Canonical name or synonym, such as "pytorch".

        Returns
        -------
        set of str
            Canonical names, such as {"python", "deep learning", "machine
            learning"}. Empty for skills the taxonomy doesn't know. Never includes
            the skill itself.
        """
        found: set[str] = set()
        todo = list(self._up.get(self.canonical(name), []))
        while todo:
            skill = todo.pop()
            if skill not in found:
                found.add(skill)
                todo += self._up[skill]
        return found

    def supporting(self, name: str) -> set[str]:
        """Find every skill whose evidence also counts for a skill.

        The reverse of `implied`: for "sql", the skills that imply it, such as "dbt"
        and "postgresql".

        Parameters
        ----------
        name : str
            Canonical name or synonym.

        Returns
        -------
        set of str
            Canonical names. Never includes the skill itself.
        """
        target = self.canonical(name)
        return {s.name for s in self.skills if target in self.implied(s.name)}


def _find_cycle(up: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle in the relation graph, as a path, or None."""
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str] | None:
        if node in path:
            return path[path.index(node) :] + [node]
        if node in done:
            return None
        for target in up.get(node, []):
            cycle = visit(target, [*path, node])
            if cycle:
                return cycle
        done.add(node)
        return None

    for node in up:
        cycle = visit(node, [])
        if cycle:
            return cycle
    return None


def taxonomy_path() -> Path:
    """Return the taxonomy file in use: `$UNAPPLY_SKILLS`, or `config/skills.yaml`.

    Returns
    -------
    Path
        The file. It isn't checked to exist.
    """
    return Path(os.environ.get(SKILLS_FILE) or DEFAULT_PATH)


@functools.cache
def default_taxonomy() -> Taxonomy:
    """Load the taxonomy file in use, once per process.

    Returns
    -------
    Taxonomy
        The taxonomy from `taxonomy_path()`. Call `default_taxonomy.cache_clear()`
        to read the file again.

    Raises
    ------
    TaxonomyError
        If the file is missing or invalid.
    """
    path = taxonomy_path()
    if not path.is_file():
        raise TaxonomyError(f"no skill taxonomy at {path} (set ${SKILLS_FILE})")
    return Taxonomy.load(path)


def canonical_skill(name: str, taxonomy: Taxonomy | None = None) -> str:
    """Map a skill name to its canonical name through the taxonomy.

    Parameters
    ----------
    name : str
        Skill name as written, such as " Scikit Learn ".
    taxonomy : Taxonomy or None, optional
        The taxonomy to use, by default `default_taxonomy()`.

    Returns
    -------
    str
        Canonical name, such as "scikit-learn". Names the taxonomy doesn't know are
        lowercased with single spaces.
    """
    return (taxonomy or default_taxonomy()).canonical(name)
