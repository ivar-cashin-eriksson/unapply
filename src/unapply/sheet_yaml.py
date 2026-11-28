"""Read the YAML sheets people edit by hand, with only true and false as booleans.

`yaml.safe_load` follows YAML 1.1, where plain words such as `NO`, `no`, `yes`,
`on` and `off` become booleans. On a sheet, `NO` is more likely Norway and `yes` a
note. `load_sheet` reads booleans as YAML 1.2 does: only `true` and `false` (in
any of the cases `true`, `True`, `TRUE`); every other word stays text. Numbers,
nulls and the rest are read as `yaml.safe_load` reads them.
"""

from __future__ import annotations

import re

import yaml


class _SheetLoader(yaml.SafeLoader):
    """A safe loader whose booleans are only true and false."""


_SheetLoader.yaml_implicit_resolvers = {
    first: [
        (tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_SheetLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def load_sheet(text: str) -> object:
    """Read a hand-edited YAML sheet.

    Parameters
    ----------
    text : str
        The sheet's YAML.

    Returns
    -------
    object
        What `yaml.safe_load` returns, except that only `true` and `false` are
        booleans: `NO`, `yes`, `on` and `off` stay strings.

    Raises
    ------
    yaml.YAMLError
        If the text isn't valid YAML.
    """
    return yaml.load(text, Loader=_SheetLoader)  # noqa: S506 - a SafeLoader subclass
