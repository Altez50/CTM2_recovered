from __future__ import annotations

import csv
import io
import sqlite3
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response

from api.auth_dependencies import get_current_user, get_db
from api.list_query import parse_quick_filters
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.services import query_work_execution


router = APIRouter(prefix="/api/registers", tags=["registers"])

# Состав колонок для экспорта (ключ → заголовок)
_EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("period", "Период"),
    ("recorder_type", "Тип регистратора"),
    ("recorder_number", "Регистратор"),
    ("customer_name", "Заказчик"),
    ("contract_number", "Договор"),
    ("object_name", "Объект"),
    ("estimate_number", "Смета"),
    ("work_name", "Работа"),
    ("quantity_income", "Приход кол-во"),
    ("quantity_expense", "Расход кол-во"),
    ("sum_income", "Приход сумма"),
    ("sum_expense", "Расход сумма"),
    ("balance_sum", "Баланс"),
]


@router.get("/work-execution", response_model=ApiResponse)
def query_work_execution_register(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    period_from: str | None = None,
    period_to: str | None = None,
    object_id: int | None = None,
    estimate_id: int | None = None,
    work_id: int | None = None,
    customer_id: int | None = None,
    contract_id: int | None = None,
    group_by: list[str] = Query(default=[]),
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params)
    items, pagination, totals = query_work_execution(
        connection,
        page=page,
        page_size=page_size,
        period_from=period_from,
        period_to=period_to,
        object_id=object_id,
        estimate_id=estimate_id,
        work_id=work_id,
        customer_id=customer_id,
        contract_id=contract_id,
        group_by=group_by or None,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data={"items": items, "totals": totals}, pagination=pagination)


@router.get("/work-execution/export")
def export_work_execution(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    request: Request,
    format: str = Query(default="csv", regex="^(csv|xlsx)$"),
    period_from: str | None = None,
    period_to: str | None = None,
    object_id: int | None = None,
    estimate_id: int | None = None,
    work_id: int | None = None,
    customer_id: int | None = None,
    contract_id: int | None = None,
    group_by: list[str] = Query(default=[]),
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> Response:
    filters = parse_quick_filters(request.query_params)
    items, _, totals = query_work_execution(
        connection,
        page=1,
        page_size=100_000,
        period_from=period_from,
        period_to=period_to,
        object_id=object_id,
        estimate_id=estimate_id,
        work_id=work_id,
        customer_id=customer_id,
        contract_id=contract_id,
        group_by=group_by or None,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )

    # Заголовки колонок
    headers = [label for _, label in _EXPORT_COLUMNS]
    # Данные
    data_rows: list[list[str]] = []
    for item in items:
        data_rows.append([str(item.get(key, "")) for key, _ in _EXPORT_COLUMNS])
    # Строка итогов
    data_rows.append([
        "", "", "", "", "", "", "", "Итого:",
        str(totals.get("quantity_income", "")),
        str(totals.get("quantity_expense", "")),
        str(totals.get("sum_income", "")),
        str(totals.get("sum_expense", "")),
        str(totals.get("balance_sum", "")),
    ])

    if format == "csv":
        buf = io.StringIO()
        buf.write("\ufeff")  # BOM для корректного открытия в Excel
        writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(data_rows)
        content = buf.getvalue()
        return Response(
            content=content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="work_execution.csv"; '
                    f"filename*=UTF-8''{quote('Регистр_работ.csv')}"
                ),
            },
        )

    # xlsx — генерируем HTML-таблицу (Excel открывает нативно)
    html_rows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in [headers] + data_rows
    )
    html = (
        '<html xmlns:o="urn:schemas-microsoft-com:office:office"'
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"'
        ' xmlns="http://www.w3.org/TR/REC-html40">'
        "<head><meta charset=\"utf-8\"></head><body>"
        f"<table border=\"1\">{html_rows}</table>"
        "</body></html>"
    )
    return Response(
        content=html.encode("utf-8"),
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": (
                'attachment; filename="work_execution.xls"; '
                f"filename*=UTF-8''{quote('Регистр_работ.xls')}"
            ),
        },
    )
