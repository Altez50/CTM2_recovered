"""Database abstraction layer (DBAL).

Provides a uniform connection interface over SQLite and PostgreSQL so the rest
of ``api/`` can keep using ``?``-placeholder SQL together with both positional
(``row[0]``) and named (``row["col"]``) row access, regardless of backend.

Design:
- SQLite passes through a raw ``sqlite3.Connection`` (its ``sqlite3.Row``
  already supports both access styles natively).
- PostgreSQL is wrapped: ``?`` placeholders are translated to ``%s`` (pyformat)
  and fetched rows are materialized as :class:`DbRow` instances that support
  both positional and name-based access.

This module contains the backend-agnostic pieces: the :class:`DbRow` row type,
the :class:`DbCursor` wrapper, a SQL placeholder translator and a
:class:`DbConnection` :class:`typing.Protocol` describing the shared surface.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Protocol, runtime_checkable


class DbRow(Sequence[Any]):
    """A result row that supports both positional and name-based access.

    Mirrors the subset of ``sqlite3.Row`` behaviour that the codebase relies on:
    ``row[0]``, ``row["col"]``, ``len(row)`` and ``row.keys()``.
    """

    __slots__ = ("_values", "_index")

    def __init__(self, values: Sequence[Any], column_names: Sequence[str]) -> None:
        self._values = tuple(values)
        self._index = {name: i for i, name in enumerate(column_names)}

    def __getitem__(self, key: Any) -> Any:  # type: ignore[override]
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, str):
            try:
                return self._values[self._index[key]]
            except KeyError as exc:
                raise KeyError(key) from exc
        raise TypeError(f"indices must be int or str, not {type(key).__name__}")

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def keys(self) -> list[str]:
        return list(self._index.keys())

    def values(self) -> tuple[Any, ...]:
        return self._values

    def items(self) -> list[tuple[str, Any]]:
        return [(name, self._values[i]) for name, i in self._index.items()]

    def get(self, key: str, default: Any = None) -> Any:
        i = self._index.get(key)
        return default if i is None else self._values[i]

    def __repr__(self) -> str:
        return f"DbRow({dict(self.items())})"


class DbCursor(Protocol):
    """Minimal cursor surface used by the repositories."""

    description: Sequence[Any]

    def execute(self, operation: str, parameters: Sequence[Any] | dict[str, Any] = ...) -> "DbCursor": ...

    def executemany(self, operation: str, seq_of_parameters: Iterable[Sequence[Any]]) -> "DbCursor": ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...

    def close(self) -> None: ...


@runtime_checkable
class DbConnection(Protocol):
    """Shared connection surface across backends.

    SQLite satisfies this structurally via ``sqlite3.Connection``; PostgreSQL
    satisfies it via the wrapper in :mod:`api.db.postgres_backend`.
    """

    def execute(self, operation: str, parameters: Sequence[Any] | dict[str, Any] = ...) -> DbCursor: ...

    def executemany(self, operation: str, seq_of_parameters: Iterable[Sequence[Any]]) -> DbCursor: ...

    def executescript(self, script: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


def translate_sql(sql: str, *, escape_percent: bool) -> str:
    """Translate ``?`` placeholders to ``%s`` and optionally escape literal ``%``.

    Postgres uses pyformat (``%s``) placeholders; SQLite uses qmark (``?``).
    A literal ``%`` in the SQL text must become ``%%`` so psycopg does not try
    to interpret it as a format spec.

    The translation respects SQL lexical structure so that ``?`` or ``%`` inside
    string literals, quoted identifiers and comments are handled consistently:
    ``?`` is only replaced outside literals/identifiers (a ``?`` inside a string
    literal is data, not a placeholder), while ``%`` is escaped everywhere
    because psycopg scans the whole query string.
    """

    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]

        # Single-quoted string literal ('...' with '' escape)
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                c = sql[i]
                out.append(c)
                if c == "'" and i + 1 < n and sql[i + 1] == "'":
                    out.append(sql[i + 1])
                    i += 2
                    continue
                if c == "'":
                    i += 1
                    break
                if escape_percent and c == "%":
                    out.append("%")
                i += 1
            continue

        # Double-quoted identifier ("..." with "" escape)
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                c = sql[i]
                out.append(c)
                if c == '"' and i + 1 < n and sql[i + 1] == '"':
                    out.append(sql[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                i += 1
            continue

        # Line comment -- until newline
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                out.append(sql[i])
                i += 1
            continue

        # Block comment /* ... */
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            out.append("/*")
            i += 2
            while i < n:
                if sql[i] == "*" and i + 1 < n and sql[i + 1] == "/":
                    out.append("*/")
                    i += 2
                    break
                out.append(sql[i])
                i += 1
            continue

        if ch == "?":
            out.append("%s")
            i += 1
            continue

        if escape_percent and ch == "%":
            out.append("%%")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def split_script(script: str) -> list[str]:
    """Split a multi-statement SQL script on top-level ``;``.

    Respects string literals, quoted identifiers and comments so statements
    containing ``;`` inside them are not split. Empty statements are dropped.
    Used to emulate SQLite's ``executescript`` on backends that lack it.
    """

    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(script)
    while i < n:
        ch = script[i]

        if ch == "'":
            buf.append(ch)
            i += 1
            while i < n:
                c = script[i]
                buf.append(c)
                if c == "'" and i + 1 < n and script[i + 1] == "'":
                    buf.append(script[i + 1])
                    i += 2
                    continue
                if c == "'":
                    i += 1
                    break
                i += 1
            continue

        if ch == '"':
            buf.append(ch)
            i += 1
            while i < n:
                c = script[i]
                buf.append(c)
                if c == '"' and i + 1 < n and script[i + 1] == '"':
                    buf.append(script[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                i += 1
            continue

        if ch == "-" and i + 1 < n and script[i + 1] == "-":
            while i < n and script[i] != "\n":
                buf.append(script[i])
                i += 1
            continue

        if ch == "/" and i + 1 < n and script[i + 1] == "*":
            buf.append("/*")
            i += 2
            while i < n:
                if script[i] == "*" and i + 1 < n and script[i + 1] == "/":
                    buf.append("*/")
                    i += 2
                    break
                buf.append(script[i])
                i += 1
            continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements
