"""Database abstraction layer (DBAL) package.

Exposes a single entry point :func:`get_connection` that returns a backend
connection implementing the :class:`DbConnection` protocol, selected by the
``DB_TYPE`` setting (``sqlite`` by default, ``postgresql`` supported).

The rest of ``api/`` should prefer the helpers here over importing a specific
backend directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from api.config import settings
from api.db.base import DbConnection, DbRow, split_script, translate_sql
from api.db.dialect import last_insert_id, table_columns, table_exists

if TYPE_CHECKING:
    pass


__all__ = [
    "DbConnection",
    "DbRow",
    "get_connection",
    "last_insert_id",
    "split_script",
    "table_columns",
    "table_exists",
    "translate_sql",
    "current_backend",
]


def current_backend() -> str:
    """Return the configured backend id (``sqlite`` or ``postgresql``)."""

    return settings.db_type


def get_connection() -> DbConnection:
    """Return a new backend connection.

    The returned object implements the :class:`DbConnection` protocol: for
    SQLite it is a raw ``sqlite3.Connection``; for PostgreSQL it is a
    :class:`api.db.postgres_backend.PostgresConnection` wrapper.
    """

    backend = settings.db_type
    if backend == "postgresql":
        from api.db.postgres_backend import connect as pg_connect

        return pg_connect()
    # Default / fallback: SQLite.
    from api.db.sqlite_backend import connect as sqlite_connect

    return sqlite_connect()
