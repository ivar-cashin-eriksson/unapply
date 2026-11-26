"""Shared test setup: no test makes a paid API call unless it is run live on purpose."""

import pytest

from unapply.llm import API_SWITCH


@pytest.fixture(autouse=True)
def no_paid_api_calls(monkeypatch, tmp_path):
    """Switch paid API calls off and keep the call log out of the real data folder.

    The switch is set to "0" rather than removed, because the CLI loads `.env` without
    overriding variables that are already set; a "1" in `.env` can't switch it back
    on. Live tests (UNAPPLY_LIVE=1) pass `--allow-api` explicitly.
    """
    monkeypatch.setenv(API_SWITCH, "0")
    monkeypatch.setenv("UNAPPLY_DATA", str(tmp_path / "data"))
