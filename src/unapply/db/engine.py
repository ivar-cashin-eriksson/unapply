"""Connecting to the database and building its schema with Alembic.

The database is `$UNAPPLY_DATABASE_URL`, by default a SQLite file in the data folder
(`sqlite:///data/unapply.db`). Any SQLAlchemy URL works; Postgres needs the `db` extra
(`uv sync --extra db`) and a URL such as `postgresql+psycopg://user@host/unapply`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url

from unapply.workspace import data_dir

DATABASE_URL = "UNAPPLY_DATABASE_URL"
MIGRATIONS = Path(__file__).parent / "migrations"


def database_url() -> str:
    """Return the database URL: `$UNAPPLY_DATABASE_URL`, or SQLite in the data folder.

    Returns
    -------
    str
        A SQLAlchemy URL, by default `sqlite:///data/unapply.db` (the data folder
        follows `$UNAPPLY_DATA`).
    """
    url = os.environ.get(DATABASE_URL)
    if url:
        return url
    return f"sqlite:///{(data_dir() / 'unapply.db').as_posix()}"


def make_engine(url: str | None = None) -> Engine:
    """Create an engine for the database.

    For a SQLite file, its folder is created if needed and foreign keys are switched
    on, which SQLite otherwise leaves off, so it behaves like Postgres.

    Parameters
    ----------
    url : str or None, optional
        SQLAlchemy URL, by default `database_url()`.

    Returns
    -------
    Engine
        The engine. Nothing is connected until it is used.
    """
    parsed = make_url(url or database_url())
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(parsed)
        event.listen(engine, "connect", _sqlite_foreign_keys)
        return engine
    return create_engine(parsed)


def _sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:  # noqa: ANN401
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def alembic_config(url: str | None = None) -> Config:
    """Build the Alembic configuration for the package's migrations.

    Parameters
    ----------
    url : str or None, optional
        SQLAlchemy URL, by default `database_url()`.

    Returns
    -------
    Config
        Configuration pointing at `unapply/db/migrations`, without an ini file.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    # Alembic's configparser treats "%" as interpolation, which URLs can contain.
    config.set_main_option("sqlalchemy.url", (url or database_url()).replace("%", "%%"))
    return config


def init_db(url: str | None = None) -> str:
    """Create the database's tables, or migrate them to the newest version.

    Running it again on an up-to-date database changes nothing.

    Parameters
    ----------
    url : str or None, optional
        SQLAlchemy URL, by default `database_url()`.

    Returns
    -------
    str
        The URL migrated, with any password hidden.
    """
    url = url or database_url()
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            config = alembic_config(url)
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    return make_url(url).render_as_string(hide_password=True)
