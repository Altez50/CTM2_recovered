"""Транслятор и исполнитель запросов консоли (инженерный раздел «Таблицы»).

См. TABLES_ENGINEERING_SPEC.md, разделы 3.2.4 и 4.4.

Поток:
  текст пользователя (синонимы)
    → токенизация (с учётом строковых литералов и комментариев)
    → разрешение синонимов таблиц/полей в физические имена (контекстно, с алиасами)
    → валидация (один SELECT, запрет DML/DDL, вайтлист таблиц)
    → read-only выполнение с LIMIT и таймаутом
    → обратная подстановка синонимов в заголовки результата

Безопасность обеспечивается слоями:
  1) только роль admin (в роутере);
  2) строгая валидация операторов (один SELECT, чёрный список ключевых слов);
  3) вайтлист таблиц (все использованные таблицы должны быть из каталога);
  4) read-only транзакция (query_only / READ ONLY) + rollback;
  5) защитный LIMIT и таймаут выполнения.
"""

from __future__ import annotations

import time
from typing import Any

from api import engineering_metadata as meta
from api.db import current_backend, get_connection
from api.db.dialect import table_columns


MAX_ROWS = 10_000
DEFAULT_LIMIT = 1_000
QUERY_TIMEOUT_SECONDS = 10.0


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Преобразовать строку результата (sqlite3.Row или DbRow) в dict."""
    keys = row.keys() if hasattr(row, "keys") else None
    if keys is not None:
        return {k: row[k] for k in keys}
    # fallback для позиционных строк
    return {f"col{i}": v for i, v in enumerate(row)}


class QueryError(Exception):
    """Ошибка трансляции/выполнения запроса (возвращается клиенту как 400)."""


class QueryTimeoutError(QueryError):
    pass


# ── Ключевые слова SQL, которые НЕ переводятся (оставляются как есть) ──────
# В upper-case. Идентификатор, совпадающий с ключевым словом, не считается
# синонимом таблицы/поля.
_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER",
    "CROSS", "ON", "AS", "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE", "BETWEEN",
    "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC", "LIMIT", "OFFSET", "UNION",
    "ALL", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END", "CAST", "AS",
    "WITH", "RECURSIVE",
}
_SQL_FUNCS = {
    "COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL", "COALESCE", "NULLIF", "CAST",
    "LENGTH", "LOWER", "UPPER", "SUBSTR", "SUBSTRING", "TRIM", "ROUND", "ABS",
    "DATE", "DATETIME", "STRFTIME", "EXTRACT", "REPLACE", "CONCAT", "IFNULL",
    "GREATEST", "LEAST",
}

# Ключевые слова, наличие которых в запросе недопустимо (модификация/DDL/прочее).
_BANNED_KEYWORDS = {
    "INSERT", "INTO", "VALUES", "UPDATE", "DELETE", "MERGE", "REPLACE",
    "CREATE", "ALTER", "DROP", "TRUNCATE", "GRANT", "REVOKE", "PRAGMA",
    "ATTACH", "DETACH", "VACUUM", "REINDEX", "ANALYZE", "EXPLAIN", "QUERY",
    "PLAN", "CALL", "EXECUTE", "EXEC", "PREPARE", "DEALLOCATE", "DECLARE",
    "FETCH", "CLOSE", "COMMIT", "ROLLBACK", "BEGIN", "START",
    "SAVEPOINT", "RELEASE", "SET", "SHOW", "LOCK", "UNLOCK", "COPY", "DO",
    "REFRESH", "MATERIALIZED", "COMMENT", "GRANT", "REFERENCES", "CHECKPOINT",
    "DATABASE", "INDEX", "VIEW", "TRIGGER",
    "SEQUENCE", "FUNCTION", "PROCEDURE", "SCHEMA", "ROLE", "USER", "PASSWORD",
}


# ── Токенизатор ───────────────────────────────────────────────────────────
# Уважает строковые литералы ('...'), экранированные идентификаторы ("..."),
# однострочные (-- ...) и многострочные (/* */) комментарии. Не использует
# регулярные выражения для подстановки синонимов — только токенизация, что
# исключает искажение имён внутри литералов/комментариев.

def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def tokenize(sql: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        # пробелы
        if ch.isspace():
            j = i
            while j < n and sql[j].isspace():
                j += 1
            tokens.append(("ws", sql[i:j]))
            i = j
            continue
        # однострочный комментарий
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = i
            while j < n and sql[j] != "\n":
                j += 1
            tokens.append(("comment", sql[i:j]))
            i = j
            continue
        # многострочный комментарий
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            j = i + 2
            while j < n and not (sql[j] == "*" and j + 1 < n and sql[j + 1] == "/"):
                j += 1
            j = min(n, j + 2)
            tokens.append(("comment", sql[i:j]))
            i = j
            continue
        # строковый литерал
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            tokens.append(("str", sql[i:j]))
            i = j
            continue
        # экранированный идентификатор (физическое имя) — оставляем как есть
        if ch == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            tokens.append(("qid", sql[i:j]))
            i = j
            continue
        # идентификатор (в т.ч. кириллица) / число
        if _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_part(sql[j]):
                j += 1
            tokens.append(("ident", sql[i:j]))
            i = j
            continue
        if ch.isdigit():
            j = i + 1
            while j < n and (sql[j].isdigit() or sql[j] == "."):
                j += 1
            tokens.append(("num", sql[i:j]))
            i = j
            continue
        # прочее — по одному символу (точки, запятые, скобки, звёздочка и т.д.)
        tokens.append(("punct", ch))
        i += 1
    return tokens


# ── Контекст трансляции ───────────────────────────────────────────────────

class _Translator:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.backend = current_backend()
        self.alias_map: dict[str, str] = {}
        self.referenced_tables: set[str] = set()
        self.unresolved_tables: set[str] = set()
        self._field_maps: dict[str, dict[str, str]] = {}

    def _field_map(self, physical: str) -> dict[str, str]:
        """Карта {synonym_lower|col_lower: physical_column} для таблицы."""
        if physical in self._field_maps:
            return self._field_maps[physical]
        m: dict[str, str] = {}
        try:
            cols = table_columns(self.connection, physical, self.backend)
        except Exception:
            cols = []
        for col in cols:
            desc = meta.field_descriptor(physical, col)
            m[desc["synonym"].lower()] = col
            m[col.lower()] = col
        self._field_maps[physical] = m
        return m

    def _resolve_table(self, token_lower: str) -> str | None:
        """Разрешить имя таблицы (синоним или физическое) → физическое."""
        maps = meta.build_translation_maps()
        if token_lower in self.alias_map:
            return self.alias_map[token_lower]
        return maps["table_by_synonym"].get(token_lower)

    def _build_alias_map(self, sig_tokens: list[tuple[int, str]]) -> None:
        """Эвристический разбор FROM/JOIN: алиасы + реестр всех таблиц.

        Заполняет ``referenced_tables`` (разрешённые физические имена) и
        ``unresolved_tables`` (идентификаторы в позиции таблицы, не входящие
        в каталог — например технические таблицы). Последние вызывают ошибку
        на этапе валидации.
        """
        expect_table = False
        expect_alias = False
        last_table: str | None = None
        table_intro = {"FROM", "JOIN"}
        for _, text in sig_tokens:
            upper = text.upper()
            if upper in table_intro:
                expect_table = True
                expect_alias = False
                continue
            if upper == "," and expect_alias:
                # запятая в списке FROM → следующая таблица
                expect_table = True
                expect_alias = False
                continue
            if expect_table:
                if text == "(":
                    # производная таблица (подзапрос) — не идентификатор
                    expect_table = False
                    expect_alias = True
                    continue
                resolved = self._resolve_table(text.lower())
                if resolved:
                    last_table = resolved
                    self.alias_map[text.lower()] = resolved
                    self.referenced_tables.add(resolved)
                else:
                    # не синоним и не таблица из каталога → недопустимая таблица
                    self.unresolved_tables.add(text)
                    last_table = None
                expect_table = False
                expect_alias = True
                continue
            if expect_alias:
                if upper == "AS":
                    continue
                # идентификатор, не ключевое слово → алиас
                if upper not in _SQL_KEYWORDS and upper not in _SQL_FUNCS:
                    if last_table:
                        self.alias_map[text.lower()] = last_table
                expect_alias = False
                continue

    def translate(self, sql: str) -> str:
        tokens = tokenize(sql)
        # значимые токены (без пробелов/комментариев)
        sig_idx = [i for i, (k, _) in enumerate(tokens) if k not in ("ws", "comment")]
        sig_tokens = [(i, tokens[i][1]) for i in sig_idx if tokens[i][0] == "ident" or tokens[i][0] == "punct"]

        self._build_alias_map(sig_tokens)

        out: list[str] = []
        for i, (kind, text) in enumerate(tokens):
            if kind != "ident":
                out.append(text)
                continue
            upper = text.upper()
            lower = text.lower()
            # контекст: предыдущий/следующий значимый токен
            prev_sig = self._neighbor(tokens, i, -1)
            next_sig = self._neighbor(tokens, i, 1)
            # псевдоним колонки после AS — не переводим
            if prev_sig and prev_sig.upper() == "AS":
                out.append(text)
                continue
            # квалифицированное поле:  Qualifier . This
            if prev_sig == ".":
                qualifier_table = self._qualifier_table(tokens, i)
                if qualifier_table:
                    fmap = self._field_map(qualifier_table)
                    col = fmap.get(lower)
                    if col:
                        out.append(f'"{col}"')
                    else:
                        out.append(text)  # неизвестное поле — оставить как есть
                else:
                    out.append(text)
                continue
            # квалификатор таблицы:  This . <field>
            if next_sig == ".":
                resolved = self._resolve_table(lower)
                if resolved:
                    self.referenced_tables.add(resolved)
                    out.append(f'"{resolved}"')
                else:
                    out.append(text)
                continue
            # ключевое слово / функция — не переводим
            if upper in _SQL_KEYWORDS or upper in _SQL_FUNCS:
                out.append(text)
                continue
            # одиночная ссылка на таблицу
            resolved = self._resolve_table(lower)
            if resolved:
                self.referenced_tables.add(resolved)
                out.append(f'"{resolved}"')
                continue
            # глобально однозначный синоним поля
            col = self._global_field(lower)
            if col:
                out.append(f'"{col}"')
                continue
            # прочее — оставить как есть (алиас, физическое поле, неизвестное)
            out.append(text)
        return "".join(out)

    def _neighbor(self, tokens: list[tuple[str, str]], idx: int, step: int) -> str:
        j = idx + step
        while 0 <= j < len(tokens):
            k, t = tokens[j]
            if k in ("ws", "comment"):
                j += step
                continue
            # для punct возвращаем сам символ; для ident — текст
            return t
        return ""

    def _qualifier_table(self, tokens: list[tuple[str, str]], field_idx: int) -> str | None:
        """Найти таблицу-квалификатор для поля по токену перед точкой."""
        # пропускаем точку и пробелы назад
        j = field_idx - 1
        while j >= 0 and tokens[j][0] in ("ws", "comment"):
            j -= 1
        if j < 0 or tokens[j] != ("punct", "."):
            return None
        j -= 1
        while j >= 0 and tokens[j][0] in ("ws", "comment"):
            j -= 1
        if j < 0 or tokens[j][0] != "ident":
            return None
        return self._resolve_table(tokens[j][1].lower())

    def _global_field(self, synonym_lower: str) -> str | None:
        """Однозначный глобальный синоним поля → физическая колонка.

        Используется только для неквалифицированных ссылок; если синоним
        отображается более чем в одну физическую колонку — не разрешается
        (пользователь должен квалифицировать: Таблица.Поле).
        """
        maps = meta.build_translation_maps()
        candidates: set[str] = set()
        for physical in maps["physical_tables"]:
            fmap = self._field_map(physical)
            col = fmap.get(synonym_lower)
            if col:
                candidates.add(col)
        if len(candidates) == 1:
            return next(iter(candidates))
        return None


# ── Валидация ─────────────────────────────────────────────────────────────

def _validate(tokens: list[tuple[str, str]]) -> None:
    sig = [t for k, t in tokens if k not in ("ws", "comment")]
    if not sig:
        raise QueryError("Пустой запрос.")
    # только одна инструкция (запрет на ';')
    if ";" in sig:
        raise QueryError("Запрещено использовать «;» — допустим только один запрос SELECT.")
    first = sig[0].upper() if isinstance(sig[0], str) else ""
    if first not in ("SELECT", "WITH"):
        raise QueryError("Запрос должен начинаться с SELECT (или WITH).")
    # проверка ключевых слов по «чёрному списку»
    for k, t in tokens:
        if k != "ident":
            continue
        if t.upper() in _BANNED_KEYWORDS:
            raise QueryError(f"Ключевое слово «{t}» запрещено в консоли запросов.")


# ── Выполнение ────────────────────────────────────────────────────────────

def execute_query(connection: Any, text: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Транслировать, проверить и выполнить запрос; вернуть результат."""
    raw = (text or "").strip().rstrip(";").strip()
    if not raw:
        raise QueryError("Пустой запрос.")
    if not raw.upper().startswith(("SELECT", "WITH")):
        raise QueryError("Запрос должен начинаться с SELECT (или WITH).")

    tokens = tokenize(raw)
    _validate(tokens)

    translator = _Translator(connection)
    physical_sql = translator.translate(raw)

    # недопустимые таблицы (не из каталога)
    if translator.unresolved_tables:
        names = ", ".join(sorted(translator.unresolved_tables))
        raise QueryError(
            f"Таблицы не из каталога (доступ запрещён): {names}"
        )

    # вайтлист таблиц
    maps = meta.build_translation_maps()
    unknown = translator.referenced_tables - maps["physical_tables"]
    if unknown:
        names = ", ".join(sorted(unknown))
        raise QueryError(f"Таблицы не из каталога: {names}")

    # защитный LIMIT
    upper_sql = physical_sql.upper()
    has_limit = "LIMIT" in upper_sql or "FETCH FIRST" in upper_sql
    effective_limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_ROWS))
    if not has_limit:
        physical_sql = f"{physical_sql}\nLIMIT {effective_limit}"
    else:
        effective_limit = MAX_ROWS

    # обратная карта синонимов для заголовков результата (с сохранением регистра)
    synonym_lookup: dict[str, str] = {}
    for physical in translator.referenced_tables:
        try:
            cols = table_columns(connection, physical, translator.backend)
        except Exception:
            cols = []
        for col in cols:
            desc = meta.field_descriptor(physical, col)
            synonym_lookup.setdefault(col, desc["synonym"])

    start = time.perf_counter()
    rows, column_names = _run_readonly(connection, physical_sql)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    truncated = len(rows) >= effective_limit
    data = [_row_to_dict(row) for row in rows]
    columns_meta = [
        {"name": c, "synonym": synonym_lookup.get(c, c)}
        for c in column_names
    ]
    return {
        "columns": columns_meta,
        "rows": data,
        "row_count": len(data),
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
        "sql": physical_sql,
    }


def _run_readonly(connection: Any, sql: str) -> tuple[list[Any], list[str]]:
    """Выполнить SELECT в read-only режиме с таймаутом; вернуть (rows, col_names).

    Использует отдельное соединение, чтобы не влиять на транзакцию запроса.
    """
    backend = current_backend()
    conn = get_connection()
    try:
        if backend == "sqlite":
            return _run_sqlite(conn, sql)
        return _run_postgres(conn, sql)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_sqlite(conn: Any, sql: str) -> tuple[list[Any], list[str]]:
    import sqlite3

    # query_only запрещает любые записи даже через PRAGMA/Attached.
    try:
        conn.execute("PRAGMA query_only = ON")
    except sqlite3.DatabaseError:
        pass

    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS

    def _progress() -> int:
        if time.monotonic() > deadline:
            return 1  # прервать выполнение
        return 0

    try:
        conn.set_progress_handler(_progress, 10_000)
    except (AttributeError, sqlite3.NotSupportedError):
        pass

    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        names = [d[0] for d in (cur.description or [])]
        return rows, names
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower() or "progress handler" in str(exc).lower():
            raise QueryTimeoutError(
                f"Превышено время выполнения ({QUERY_TIMEOUT_SECONDS:.0f} с)."
            ) from exc
        raise QueryError(f"Ошибка SQL: {exc}") from exc
    except sqlite3.Error as exc:
        raise QueryError(f"Ошибка SQL: {exc}") from exc
    finally:
        try:
            conn.rollback()
        except Exception:
            pass


def _run_postgres(conn: Any, sql: str) -> tuple[list[Any], list[str]]:
    # conn — PostgresConnection (обёртка). Доступ к raw psycopg через .raw.
    raw = getattr(conn, "raw", None)
    try:
        if raw is not None:
            cur = raw.cursor()
            try:
                cur.execute("BEGIN READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = '{int(QUERY_TIMEOUT_SECONDS)}s'")
                cur.execute(sql)
                rows = cur.fetchall()
                names = [d[0] for d in (cur.description or [])]
                return rows, names
            finally:
                try:
                    raw.rollback()
                except Exception:
                    pass
                try:
                    cur.close()
                except Exception:
                    pass
        # fallback: обёрнутый execute (без read-only, но валидация уже отсекла DML)
        cur = conn.execute(sql)
        rows = cur.fetchall()
        names = [d[0] for d in (cur.description or [])]
        return rows, names
    except QueryError:
        raise
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if "statement timeout" in str(exc).lower() or "canceling statement" in str(exc).lower():
            raise QueryTimeoutError(
                f"Превышено время выполнения ({QUERY_TIMEOUT_SECONDS:.0f} с)."
            ) from exc
        raise QueryError(f"Ошибка SQL ({name}): {exc}") from exc
