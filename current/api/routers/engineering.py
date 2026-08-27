"""Инженерный раздел «Таблицы»: каталог, просмотрщик таблиц, консоль запросов.

См. TABLES_ENGINEERING_SPEC.md. Все эндпоинты доступны только роли admin.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from api import engineering_metadata as meta
from api.auth_dependencies import get_current_user, get_db, require_roles
from api.engineering_query import (
    DEFAULT_LIMIT,
    MAX_ROWS,
    QueryError,
    QueryTimeoutError,
    execute_query,
)
from api.list_query import apply_quick_filters, order_by_clause, parse_quick_filters
from api.models.auth import UserInfo
from api.models.common import ApiResponse


router = APIRouter(prefix="/api/engineering", tags=["engineering"])


def _admin(user: Annotated[UserInfo, Depends(require_roles("admin"))]) -> UserInfo:
    return user


# ── Каталог метаданных (синонимы таблиц и полей) ──────────────────────────

@router.get("/catalog", response_model=ApiResponse)
def get_catalog(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[UserInfo, Depends(_admin)],
) -> ApiResponse:
    return ApiResponse(data=meta.catalog_payload(connection))


# ── Просмотрщик таблицы ───────────────────────────────────────────────────

@router.get("/tables/{table_name}", response_model=ApiResponse)
def view_table(
    table_name: str,
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[UserInfo, Depends(_admin)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> ApiResponse:
    descriptor = meta.table_descriptor(connection, table_name)
    if descriptor is None:
        raise HTTPException(status_code=404, detail=f"Таблица «{table_name}» не входит в каталог.")

    from api.db import current_backend

    backend = current_backend()
    columns = meta.table_columns_list(connection, table_name)
    fks = meta.table_fks(table_name)  # {physical_col: (synonym, ref_table)}

    # ── Сборка SELECT с LEFT JOIN для представлений ссылок ──
    select_parts: list[str] = []
    for col in columns:
        select_parts.append(f't."{col}" AS "{col}"')
    joins: list[str] = []
    rep_columns: list[dict[str, Any]] = []
    used_aliases: set[str] = set()
    for col, (_syn, ref_table) in fks.items():
        if col not in columns:
            continue
        disp = meta.ref_display_column(ref_table)
        alias = f"r_{col}"
        # гарантируем уникальность алиаса
        base = alias
        k = 1
        while alias in used_aliases:
            k += 1
            alias = f"{base}_{k}"
        used_aliases.add(alias)
        joins.append(
            f'LEFT JOIN "{ref_table}" AS "{alias}" ON "{alias}"."id" = t."{col}"'
        )
        rep_key = f"{col}__representation"
        select_parts.append(f'"{alias}"."{disp}" AS "{rep_key}"')
        rep_columns.append({
            "name": rep_key,
            "synonym": meta.fk_synonym(table_name, col),
            "type": "text",
            "is_representation": True,
            "for": col,
        })

    # ── Сортировка (вайтлист по физ. колонкам + представлениям) ──
    sort_allowed: dict[str, str] = {c: f't."{c}"' for c in columns}
    for rc in rep_columns:
        sort_allowed[rc["name"]] = f'"{rc["name"]}"'
    order_clause = order_by_clause(
        sort_by, sort_order, sort_allowed,
        default_column=f't."id"', default_order="DESC",
        tiebreaker=f't."id"',
    )

    # ── Быстрый поиск по текстовым полям ──
    where_parts: list[str] = []
    params: list[Any] = []
    text_cols = [c for c in columns if meta.field_descriptor(table_name, c)["type"] == "text"]
    if search:
        like_clauses = [f'CAST(t."{c}" AS TEXT) LIKE ?' for c in text_cols[:6]]
        if like_clauses:
            where_parts.append("(" + " OR ".join(like_clauses) + ")")
            params.extend([f"%{search}%"] * len(like_clauses))

    # ── Быстрый отбор по колонкам (f_<field>) ──
    quick = parse_quick_filters(request.query_params)
    filter_columns: dict[str, tuple[str, str]] = {}
    for c in columns:
        ftype = meta.field_descriptor(table_name, c)["type"]
        op = "like" if ftype == "text" else "eq"
        filter_columns[c] = (f't."{c}"', op)
    apply_quick_filters(where_parts, params, quick, filter_columns)

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    offset = (page - 1) * page_size
    sql = (
        f'SELECT {", ".join(select_parts)} '
        f'FROM "{table_name}" AS t '
        f'{" ".join(joins)} '
        f"{where_sql} "
        f"{order_clause} "
        f"LIMIT ? OFFSET ?"
    )
    params.extend([page_size, offset])

    rows = connection.execute(sql, params).fetchall()
    count_sql = f'SELECT COUNT(*) AS cnt FROM "{table_name}" AS t {where_sql}'
    total = connection.execute(count_sql, params[:-2]).fetchone()["cnt"]

    fields_meta = [meta.field_descriptor(table_name, c) for c in columns]
    # Представления вставляем сразу после соответствующего поля
    columns_meta: list[dict[str, Any]] = []
    rep_by_col = {rc["for"]: rc for rc in rep_columns}
    for fm, col in zip(fields_meta, columns):
        columns_meta.append(fm)
        if col in rep_by_col:
            columns_meta.append(rep_by_col[col])

    data = [{k: row[k] for k in row.keys()} for row in rows]
    pages = max(1, (total + page_size - 1) // page_size)
    return ApiResponse(
        data={"rows": data, "columns": columns_meta, "table": table_name},
        pagination={"page": page, "page_size": page_size, "total": total, "pages": pages},
    )


# ── Консоль запросов ──────────────────────────────────────────────────────

@router.post("/query", response_model=ApiResponse)
def run_query(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[UserInfo, Depends(_admin)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустой запрос.")
    limit = int(payload.get("limit", DEFAULT_LIMIT) or DEFAULT_LIMIT)
    try:
        result = execute_query(connection, text, limit=limit)
    except QueryTimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=result)
