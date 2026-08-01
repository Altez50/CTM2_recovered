"""Общие помощники для списочных эндпоинтов: серверная сортировка и быстрый отбор.

Поведение приведено к тонкому клиенту 1С 8.3 (см. DOCUMENT_LIST_SPEC.md, разделы 3.1, 3.2.2, 4.1, 4.2).

- ``resolve_sort`` выбирает колонку сортировки по вайтлисту клиентских ключей и приводит
  направление к ASC/DESC (неизвестное поле → сортировка по умолчанию, как в services.list_estimates).
- ``apply_quick_filters`` добавляет условия быстрого отбора ``f_<field>`` в SQL-фрагмент
  WHERE по декларативному словарю колонок. Текст — LIKE «содержит», число/дата/перечисление — равно.
"""

from __future__ import annotations

from typing import Any, Mapping


def resolve_sort(
    sort_by: str | None,
    sort_order: str | None,
    allowed: Mapping[str, str],
    default_column: str,
    default_order: str = "DESC",
) -> tuple[str, str]:
    """Вернуть ``(sql_column, direction)`` для первичной сортировки.

    ``allowed`` — отображение клиентского ключа колонки на SQL-выражение
    (например ``{"date": "mc.date", "number": "mc.number"}``). Если ``sort_by``
    отсутствует или не входит в вайтлист — используется ``default_column``.
    """
    column = default_column
    if sort_by and sort_by in allowed:
        column = allowed[sort_by]
    direction = default_order
    if sort_order:
        lowered = sort_order.lower()
        if lowered.startswith("desc"):
            direction = "DESC"
        elif lowered.startswith("asc"):
            direction = "ASC"
    return column, direction


def order_by_clause(
    sort_by: str | None,
    sort_order: str | None,
    allowed: Mapping[str, str],
    default_column: str,
    default_order: str = "DESC",
    tiebreaker: str | None = "id",
) -> str:
    """Готовый фрагмент ``ORDER BY ...`` со стабильным тай-брейком по ``tiebreaker``.

    Если выбранная колонка совпадает с тай-брейком (по короткому имени), тай-брейк не дублируется.
    """
    column, direction = resolve_sort(sort_by, sort_order, allowed, default_column, default_order)
    if tiebreaker and not column.lower().endswith(f".{tiebreaker}") and column.lower() != tiebreaker:
        return f"ORDER BY {column} {direction}, {tiebreaker} DESC"
    return f"ORDER BY {column} {direction}"


# Операции быстрого отбора. ``like`` — регистронезависимое «содержит»,
# ``eq`` — точное равенство.
_FILTER_OPS = {"like", "eq"}


def apply_quick_filters(
    where_parts: list[str],
    params: list[Any],
    filters: Mapping[str, str] | None,
    columns: Mapping[str, tuple[str, str]],
) -> None:
    """Дополнить ``where_parts``/``params`` условиями быстрого отбора.

    ``filters`` — отображение ``f_<field>`` → значение (допускается ключ как с префиксом
    ``f_``, так и без). ``columns`` — ``{field: (sql_column, op)}``, где ``op`` ∈ ``{'like','eq'}``.
    Неизвестные поля игнорируются (вайтлист).
    """
    if not filters:
        return
    for raw_key, value in filters.items():
        if value is None or value == "":
            continue
        field = raw_key[2:] if raw_key.startswith("f_") else raw_key
        spec = columns.get(field)
        if spec is None:
            continue
        sql_col, op = spec
        if op not in _FILTER_OPS:
            continue
        if op == "like":
            where_parts.append(f"LOWER({sql_col}) LIKE LOWER(?)")
            params.append(f"%{value}%")
        else:
            where_parts.append(f"{sql_col} = ?")
            params.append(value)


def parse_quick_filters(raw: Mapping[str, Any] | None) -> dict[str, str]:
    """Выбрать из параметров запроса только ``f_*`` (строковые значения)."""
    if not raw:
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not key.startswith("f_"):
            continue
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out
