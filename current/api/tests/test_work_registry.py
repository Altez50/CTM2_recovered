from __future__ import annotations

from api.database import new_uuid, utcnow_iso
from api.services import query_work_execution


def _query(connection, **overrides):
    params = dict(
        page=1,
        page_size=50,
        period_from=None,
        period_to=None,
        object_id=None,
        estimate_id=None,
        work_id=None,
        customer_id=None,
        contract_id=None,
        group_by=None,
        sort_by="period",
        sort_order="asc",
        filters=None,
    )
    params.update(overrides)
    return query_work_execution(connection, **params)


def test_registry_uses_sql_pagination_and_full_export(connection) -> None:
    now = utcnow_iso()
    connection.executemany(
        """INSERT INTO work_execution_register (
               recorder_type, recorder_id, line_number, period,
               quantity_income, quantity_expense, sum_income, sum_expense,
               created_at, modified_at, uuid, updated_at, is_deleted
           ) VALUES ('estimate', ?, 1, ?, ?, 0, ?, 0, ?, ?, ?, ?, 0)""",
        [
            (index, f"2026-01-{(index % 28) + 1:02d}", 1.0, float(index), now, now, new_uuid(), now)
            for index in range(1, 126)
        ],
    )
    connection.commit()

    page_one, pagination, totals = _query(connection)
    assert len(page_one) == 50
    assert pagination.total == 125
    assert pagination.pages == 3
    assert totals["sum_income"] == 7875.0

    page_two, _, _ = _query(connection, page=2, page_size=50)
    assert len(page_two) == 50
    assert {row["id"] for row in page_one}.isdisjoint(row["id"] for row in page_two)

    hundred, pagination, _ = _query(connection, page_size=100)
    assert len(hundred) == 100
    assert pagination.page_size == 100

    exported, export_pagination, export_totals = _query(connection, export_all=True)
    assert len(exported) == 125
    assert export_pagination.total == 125
    assert export_totals == totals


def test_registry_supports_comma_separated_grouping(connection) -> None:
    now = utcnow_iso()
    connection.execute(
        """INSERT INTO work_execution_register (
               recorder_type, recorder_id, line_number, period,
               quantity_income, quantity_expense, sum_income, sum_expense,
               created_at, modified_at, uuid, updated_at, is_deleted
           ) VALUES ('estimate', 1, 1, '2026-01-01', 2, 0, 10, 0, ?, ?, ?, ?, 0)""",
        (now, now, new_uuid(), now),
    )
    connection.commit()
    rows, pagination, totals = _query(connection, group_by=["object,estimate"])
    assert rows
    assert all(row["recorder_type"] == "grouped" for row in rows)
    assert pagination.total == len(rows)
    assert totals["balance_sum"] == totals["sum_income"] - totals["sum_expense"]


def test_registry_http_export_is_complete_and_xlsx_is_real(
    client, admin_headers, connection
) -> None:
    now = utcnow_iso()
    connection.executemany(
        """INSERT INTO work_execution_register (
               recorder_type, recorder_id, line_number, period,
               quantity_income, quantity_expense, sum_income, sum_expense,
               created_at, modified_at, uuid, updated_at, is_deleted
           ) VALUES ('estimate', ?, 1, '2026-09-02', 1, 0, 1, 0, ?, ?, ?, ?, 0)""",
        [(index, now, now, new_uuid(), now) for index in range(1, 76)],
    )
    connection.commit()

    csv_response = client.get(
        "/api/registers/work-execution/export?format=csv", headers=admin_headers
    )
    assert csv_response.status_code == 200
    assert len(csv_response.content.decode("utf-8-sig").splitlines()) == 77

    xlsx_response = client.get(
        "/api/registers/work-execution/export?format=xlsx", headers=admin_headers
    )
    assert xlsx_response.status_code == 200
    assert xlsx_response.content.startswith(b"PK")
    assert xlsx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
