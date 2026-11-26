"""Alembic environment: runs the migrations in `versions/`.

`unapply db init` passes an open connection in `config.attributes["connection"]`;
the `alembic` command line (with `alembic.ini` in the project) connects to
`$UNAPPLY_DATABASE_URL` or the default SQLite file instead. With `--sql` (offline
mode) the SQL is printed rather than run.
"""

from __future__ import annotations

from alembic import context

from unapply.db.engine import database_url, make_engine
from unapply.db.models import Base

config = context.config
target_metadata = Base.metadata
# `alembic.ini` sets no URL, so the `alembic` command uses the app's database.
url = config.get_main_option("sqlalchemy.url") or database_url()


def _run_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with(connection)
        return
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            _run_with(connection)
    finally:
        engine.dispose()


def _run_with(connection: object) -> None:
    # Batch mode lets later migrations alter columns on SQLite too.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    _run_offline()
else:
    _run_online()
