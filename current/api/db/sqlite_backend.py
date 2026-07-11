"""SQLite backend.

SQLite is the default and primary backend. Because the codebase already targets
the ``sqlite3`` API (``?`` placeholders, ``sqlite3.Row``, ``executescript``),
the SQLite backend is essentially a passthrough: it returns a raw
``sqlite3.Connection`` configured with WAL journaling and foreign keys.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from api.config import settings


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def database_exists() -> bool:
    return Path(settings.database_path).exists()
