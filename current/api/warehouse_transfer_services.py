"""Internal warehouse transfers: one document, two inventory movements."""

from __future__ import annotations
from api.trade_access import add_scope, require_organization, rollback_on_error

import sqlite3
from datetime import date
from decimal import Decimal
from math import ceil
from typing import Any

from fastapi import HTTPException

from api.database import last_insert_id, new_uuid, register_sync_change, row_to_dict, rows_to_dicts, utcnow_iso
from api.trade_settlement_rules import assert_no_future_price_adjustment, assert_no_inventory_consumption, lock_inventory_warehouses, inventory_cost_share, money
from api.models.auth import UserInfo
from api.models.common import Pagination
from api.inventory_dimensions import normalize_line, validate_snapshot, base_quantity, base_unit, axes, hydrate_lines, lock_material_dimensions


def _require_role(user: UserInfo, *, post: bool = False) -> None:
    if user.role not in (("admin",) if post else ("admin", "manager")):
        raise HTTPException(status_code=403, detail="Недостаточно прав для операции")


def _validate_header(connection: sqlite3.Connection, payload: dict[str, Any]) -> None:
    organization_id = int(payload["organization_id"])
    source_id = int(payload["source_warehouse_id"])
    destination_id = int(payload["destination_warehouse_id"])
    if source_id == destination_id:
        raise HTTPException(status_code=400, detail="Склады отправителя и получателя должны различаться")
    require_organization(connection, payload["organization_id"])
    organization = connection.execute(
        "SELECT id FROM organizations WHERE id = ? AND marked_for_deletion = 0", (organization_id,)
    ).fetchone()
    if organization is None:
        raise HTTPException(status_code=400, detail="Организация не найдена")
    warehouses = connection.execute(
        """SELECT id FROM warehouses WHERE id IN (?, ?) AND organization_id = ?
           AND marked_for_deletion = 0 AND COALESCE(is_deleted, 0) = 0""",
        (source_id, destination_id, organization_id),
    ).fetchall()
    if len(warehouses) != 2:
        raise HTTPException(status_code=400, detail="Оба склада должны принадлежать выбранной организации")


def _validate_lines(connection: sqlite3.Connection, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lines:
        raise HTTPException(status_code=400, detail="Добавьте хотя бы одну строку перемещения")
    seen: set[tuple[int, int]] = set()
    normalized: list[dict[str, Any]] = []
    numbers: set[int] = set()
    for raw in lines:
        number = int(raw["line_number"])
        material_id = int(raw["material_id"])
        unit_id = int(raw["unit_id"])
        quantity = round(float(raw["quantity"]), 6)
        if number in numbers:
            raise HTTPException(status_code=400, detail=f"Повторяется номер строки {number}")
        numbers.add(number)
        identity = (material_id, unit_id, raw.get('characteristic_id'), raw.get('series_id'))
        if identity in seen:
            raise HTTPException(status_code=400, detail="Материал и единица повторяются в строках")
        seen.add(identity)
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Количество в строке {number} должно быть больше нуля")
        material = connection.execute(
            """SELECT name, unit_id FROM materials WHERE id = ? AND marked_for_deletion = 0
               AND COALESCE(is_group, 0) = 0""",
            (material_id,),
        ).fetchone()
        unit = connection.execute("SELECT id FROM units WHERE id = ?", (unit_id,)).fetchone()
        if material is None or unit is None:
            raise HTTPException(status_code=400, detail=f"Материал или единица строки {number} не найдены")
        if material["unit_id"] is not None and int(material["unit_id"]) != unit_id:
            raise HTTPException(status_code=400, detail=f"Единица строки {number} не совпадает с единицей материала")
        normalized.append({
            "line_number": number,
            "material_id": material_id,
            "name": str(raw.get("name") or material["name"]).strip(),
            "unit_id": unit_id,
            "quantity": quantity,
            "note": raw.get("note"),
            # Lines are synchronized as part of the document snapshot. A client
            # must not be able to reuse another line's UUID on a draft edit.
            "uuid": new_uuid(),
            **normalize_line(connection, {**raw, 'quantity': quantity}),
        })
    return sorted(normalized, key=lambda line: line["line_number"])


def get_transfer(connection: sqlite3.Connection, transfer_id: int) -> dict[str, Any]:
    row = connection.execute(
        """SELECT t.*, org.name AS organization_name,
                  src.name AS source_warehouse_name, dst.name AS destination_warehouse_name,
                  so.name AS source_object_name, do.name AS destination_object_name,
                  p.full_name AS responsible_name
           FROM goods_transfers t
           JOIN organizations org ON org.id = t.organization_id
           JOIN warehouses src ON src.id = t.source_warehouse_id
           JOIN warehouses dst ON dst.id = t.destination_warehouse_id
           LEFT JOIN objects so ON so.id = t.source_object_id
           LEFT JOIN objects do ON do.id = t.destination_object_id
           LEFT JOIN persons p ON p.id = t.responsible_id
           WHERE t.id = ? AND t.marked_for_deletion = 0""",
        (transfer_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Перемещение не найдено")
    transfer = row_to_dict(row) or {}
    require_organization(connection, transfer["organization_id"])
    transfer["is_posted"] = bool(transfer["is_posted"])
    transfer["marked_for_deletion"] = bool(transfer["marked_for_deletion"])
    lines = connection.execute(
        """SELECT l.*, m.code AS material_code, u.name AS unit_name
           FROM goods_transfer_lines l
           LEFT JOIN materials m ON m.id = l.material_id
           LEFT JOIN units u ON u.id = l.unit_id
           WHERE l.transfer_id = ? AND l.marked_for_deletion = 0
           ORDER BY l.line_number""",
        (transfer_id,),
    ).fetchall()
    transfer["lines"] = hydrate_lines(connection, rows_to_dicts(lines))
    transfer["line_count"] = len(lines)
    transfer["sum"] = round(sum(float(line["sum"] or 0) for line in lines), 2)
    return transfer


def list_transfers(
    connection: sqlite3.Connection, *, page: int = 1, page_size: int = 20,
    search: str | None = None, organization_id: int | None = None,
    source_warehouse_id: int | None = None, destination_warehouse_id: int | None = None,
    is_posted: bool | None = None, date_from: str | None = None, date_to: str | None = None,
    sort_by: str | None = None, sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], Pagination]:
    where = ["t.marked_for_deletion = 0"]
    params: list[Any] = []
    add_scope(connection, where, params, "t.organization_id")
    for field, value in (("organization_id", organization_id),
                         ("source_warehouse_id", source_warehouse_id),
                         ("destination_warehouse_id", destination_warehouse_id)):
        if value is not None:
            where.append(f"t.{field} = ?")
            params.append(value)
    if is_posted is not None:
        where.append("t.is_posted = ?")
        params.append(int(is_posted))
    if date_from:
        where.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        where.append("t.date <= ?")
        params.append(date_to)
    if search:
        where.append("(t.number LIKE ? OR t.description LIKE ? OR src.name LIKE ? OR dst.name LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    where_sql = " AND ".join(where)
    joins = """JOIN warehouses src ON src.id = t.source_warehouse_id
               JOIN warehouses dst ON dst.id = t.destination_warehouse_id"""
    count = int(connection.execute(
        f"SELECT COUNT(*) FROM goods_transfers t {joins} WHERE {where_sql}", params
    ).fetchone()[0])
    sort_column = {"number": "t.number", "date": "t.date", "id": "t.id"}.get(sort_by or "", "t.date")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    rows = connection.execute(
        f"""SELECT t.*, org.name AS organization_name,
                   src.name AS source_warehouse_name, dst.name AS destination_warehouse_name,
                   p.full_name AS responsible_name,
                   (SELECT COUNT(*) FROM goods_transfer_lines l
                    WHERE l.transfer_id = t.id AND l.marked_for_deletion = 0) AS line_count,
                   (SELECT COALESCE(SUM(l.sum), 0) FROM goods_transfer_lines l
                    WHERE l.transfer_id = t.id AND l.marked_for_deletion = 0) AS sum
            FROM goods_transfers t {joins}
            JOIN organizations org ON org.id = t.organization_id
            LEFT JOIN persons p ON p.id = t.responsible_id
            WHERE {where_sql} ORDER BY {sort_column} {direction}, t.id DESC LIMIT ? OFFSET ?""",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    items = rows_to_dicts(rows)
    for item in items:
        item["is_posted"] = bool(item["is_posted"])
    return items, Pagination(page=page, page_size=page_size, total=count, pages=ceil(count / page_size) if count else 1)


@rollback_on_error
def save_transfer(
    connection: sqlite3.Connection, *, payload: dict[str, Any], user: UserInfo,
    transfer_id: int | None = None,
) -> dict[str, Any]:
    _require_role(user)
    if transfer_id is not None:
        connection.execute('UPDATE goods_transfers SET id = id WHERE id = ?', (transfer_id,))
    lock_material_dimensions(connection, *(line.get('material_id') for line in payload['lines']))
    _validate_header(connection, payload)
    lines = _validate_lines(connection, payload["lines"])
    current = get_transfer(connection, transfer_id) if transfer_id is not None else None
    if current and current["is_posted"]:
        raise HTTPException(status_code=400, detail="Проведённое перемещение нельзя изменить")
    stamp = utcnow_iso()
    number = str(payload.get("number") or "").strip()
    if not number:
        last_id = connection.execute("SELECT COALESCE(MAX(id), 0) FROM goods_transfers").fetchone()[0]
        number = f"ПМ-{int(last_id) + 1:04d}"
    fields = {
        "number": number,
        "date": str(payload["date"]),
        "organization_id": payload["organization_id"],
        "source_warehouse_id": payload["source_warehouse_id"],
        "destination_warehouse_id": payload["destination_warehouse_id"],
        "source_object_id": payload.get("source_object_id"),
        "destination_object_id": payload.get("destination_object_id"),
        "responsible_id": payload.get("responsible_id"),
        "description": payload.get("description"),
        "modified_at": stamp,
        "updated_at": stamp,
    }
    try:
        if current is None:
            fields.update(created_at=stamp, uuid=new_uuid())
            columns = ", ".join(fields)
            connection.execute(
                f"INSERT INTO goods_transfers ({columns}) VALUES ({', '.join('?' for _ in fields)})",
                list(fields.values()),
            )
            transfer_id = last_insert_id(connection)
            transfer_uuid = str(fields["uuid"])
            operation = "INSERT"
        else:
            connection.execute(
                f"UPDATE goods_transfers SET {', '.join(f'{key} = ?' for key in fields)} WHERE id = ?",
                [*fields.values(), transfer_id],
            )
            transfer_uuid = str(current["uuid"])
            operation = "UPDATE"
            connection.execute("DELETE FROM goods_transfer_lines WHERE transfer_id = ?", (transfer_id,))
        for line in lines:
            connection.execute(
                """INSERT INTO goods_transfer_lines
                   (transfer_id, line_number, material_id, name, unit_id, quantity,
                    note, uuid, created_at, modified_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (transfer_id, line["line_number"], line["material_id"], line["name"],
                 line["unit_id"], line["quantity"], line["note"], line["uuid"],
                 stamp, stamp, stamp),
            )
            connection.execute('''UPDATE goods_transfer_lines SET package_id = ?, conversion_factor = ?,
                base_quantity = ?, base_unit_id = ?, characteristic_id = ?, series_id = ?
                WHERE transfer_id = ? AND line_number = ?''',
                (line['package_id'], line['conversion_factor'], line['base_quantity'], line['base_unit_id'],
                 line['characteristic_id'], line['series_id'], transfer_id, line['line_number']))
        register_sync_change(connection, entity_type="goods_transfers", entity_uuid=transfer_uuid, operation=operation)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return get_transfer(connection, int(transfer_id))


@rollback_on_error
def delete_transfer(connection: sqlite3.Connection, *, transfer_id: int, user: UserInfo) -> None:
    _require_role(user)
    connection.execute("UPDATE goods_transfers SET id = id WHERE id = ?", (transfer_id,))
    transfer = get_transfer(connection, transfer_id)
    if transfer["is_posted"]:
        raise HTTPException(status_code=400, detail="Сначала отмените проведение")
    stamp = utcnow_iso()
    try:
        connection.execute(
            """UPDATE goods_transfers SET marked_for_deletion = 1, is_deleted = 1,
               modified_at = ?, updated_at = ? WHERE id = ?""", (stamp, stamp, transfer_id),
        )
        connection.execute(
            """UPDATE goods_transfer_lines SET marked_for_deletion = 1, is_deleted = 1,
               modified_at = ?, updated_at = ? WHERE transfer_id = ?""", (stamp, stamp, transfer_id),
        )
        register_sync_change(connection, entity_type="goods_transfers", entity_uuid=str(transfer["uuid"]), operation="DELETE")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _stock(connection: sqlite3.Connection, *, warehouse_id: int, object_id: int | None,
           material_id: int, unit_id: int, on_date: str, characteristic_id=None, series_id=None) -> tuple[float, float]:
    row = connection.execute(
        """SELECT COALESCE(SUM(quantity_income - quantity_expense), 0) AS quantity,
                  COALESCE(SUM(sum_income - sum_expense), 0) AS amount
           FROM inventory_register
           WHERE warehouse_id = ? AND material_id = ? AND unit_id = ?
             AND (object_id = ? OR (object_id IS NULL AND ? IS NULL))
             AND (characteristic_id = ? OR (characteristic_id IS NULL AND ? IS NULL))
             AND (series_id = ? OR (series_id IS NULL AND ? IS NULL))
             AND period <= ? AND COALESCE(is_deleted, 0) = 0""",
        (warehouse_id, material_id, unit_id, object_id, object_id, characteristic_id, characteristic_id, series_id, series_id, on_date),
    ).fetchone()
    return float(row["quantity"]), float(row["amount"])


def post_transfer(connection: sqlite3.Connection, *, transfer_id: int, user: UserInfo) -> None:
    _require_role(user, post=True)
    try:
        connection.execute('UPDATE goods_transfers SET id = id WHERE id = ?', (transfer_id,))
        transfer = get_transfer(connection, transfer_id)
        if transfer["is_posted"]:
            raise HTTPException(status_code=400, detail="Перемещение уже проведено")
        if not transfer["lines"]:
            raise HTTPException(status_code=400, detail="Нет строк для проведения")
        lock_inventory_warehouses(connection, transfer['source_warehouse_id'], transfer['destination_warehouse_id'])
        _validate_header(connection, transfer)
        connection.execute(
            "DELETE FROM inventory_register WHERE recorder_type = 'goods_transfer' AND recorder_id = ?",
            (transfer_id,),
        )
        stamp = utcnow_iso()
        for line in transfer["lines"]:
            validate_snapshot(connection, line)
            quantity = float(base_quantity(line))
            from api.sales_rules import assert_available
            assert_available(connection,warehouse_id=transfer['source_warehouse_id'],object_id=transfer.get('source_object_id'),material_id=line['material_id'],
                             unit_id=base_unit(line),on_date=str(transfer['date']),quantity=quantity,**axes(line))
            assert_no_future_price_adjustment(
                connection, warehouse_id=transfer['source_warehouse_id'], object_id=transfer.get('source_object_id'),
                material_id=line['material_id'], unit_id=base_unit(line), on_date=str(transfer['date']), **axes(line),
            )
            available, amount = _stock(
                connection, warehouse_id=int(transfer["source_warehouse_id"]),
                object_id=transfer.get("source_object_id"), material_id=int(line["material_id"]),
                unit_id=int(base_unit(line)), on_date=str(transfer["date"]), **axes(line),
            )
            if quantity > available + 1e-9:
                raise HTTPException(
                    status_code=400,
                    detail=f"Строка {line['line_number']}: {line['name']}; требуется {quantity:g}, остаток {available:g}",
                )
            base_cost = money(amount) / Decimal(str(available)) if available else Decimal(0)
            unit_cost = float(round(base_cost * Decimal(str(line['conversion_factor'])), 6))
            transfer_sum = float(inventory_cost_share(amount, quantity, available))
            connection.execute(
                "UPDATE goods_transfer_lines SET unit_cost = ?, sum = ?, modified_at = ?, updated_at = ? WHERE id = ?",
                (unit_cost, transfer_sum, stamp, stamp, line["id"]),
            )
            for side, warehouse_id, object_id in (
                ("source", transfer["source_warehouse_id"], transfer.get("source_object_id")),
                ("destination", transfer["destination_warehouse_id"], transfer.get("destination_object_id")),
            ):
                expense = side == "source"
                connection.execute(
                    """INSERT INTO inventory_register
                       (recorder_type, recorder_id, line_number, period, material_id,
                        warehouse_id, movement_side, object_id, unit_id, characteristic_id, series_id,
                        quantity_income, quantity_expense, sum_income, sum_expense,
                        uuid, created_at, updated_at)
                       VALUES ('goods_transfer', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (transfer_id, line["line_number"], str(transfer["date"]), line["material_id"],
                     warehouse_id, side, object_id, base_unit(line), line.get('characteristic_id'), line.get('series_id'),
                     0.0 if expense else quantity, quantity if expense else 0.0,
                     0.0 if expense else transfer_sum, transfer_sum if expense else 0.0,
                     new_uuid(), stamp, stamp),
                )
        connection.execute(
            """UPDATE goods_transfers SET is_posted = 1, posted_at = ?, modified_at = ?, updated_at = ?
               WHERE id = ?""", (stamp, stamp, stamp, transfer_id),
        )
        register_sync_change(connection, entity_type="goods_transfers", entity_uuid=str(transfer["uuid"]), operation="UPDATE")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def unpost_transfer(connection: sqlite3.Connection, *, transfer_id: int, user: UserInfo) -> None:
    _require_role(user, post=True)
    stamp = utcnow_iso()
    try:
        connection.execute('UPDATE goods_transfers SET id = id WHERE id = ?', (transfer_id,))
        transfer = get_transfer(connection, transfer_id)
        if not transfer["is_posted"]:
            raise HTTPException(status_code=400, detail="Перемещение не проведено")
        lock_inventory_warehouses(connection, transfer['source_warehouse_id'], transfer['destination_warehouse_id'])
        # Removing the source expense must not hide a downstream cost dependency
        # from purchase corrections. A positive remaining stock alone is not
        # sufficient: a later expense may already contain the transferred cost.
        for line in transfer['lines']:
            assert_no_inventory_consumption(connection, warehouse_id=transfer['destination_warehouse_id'],
                object_id=transfer.get('destination_object_id'), material_id=line['material_id'],
                unit_id=base_unit(line), on_date=str(transfer['date']), **axes(line))
        connection.execute(
            "DELETE FROM inventory_register WHERE recorder_type = 'goods_transfer' AND recorder_id = ?",
            (transfer_id,),
        )
        connection.execute(
            """UPDATE goods_transfers SET is_posted = 0, posted_at = NULL,
               modified_at = ?, updated_at = ? WHERE id = ?""", (stamp, stamp, transfer_id),
        )
        from api.sales_rules import assert_available
        for line in transfer['lines']:
            assert_available(connection,warehouse_id=transfer['destination_warehouse_id'],object_id=transfer.get('destination_object_id'),material_id=line['material_id'],
                             unit_id=base_unit(line),on_date=str(transfer['date']),quantity=0,**axes(line))
        register_sync_change(connection, entity_type="goods_transfers", entity_uuid=str(transfer["uuid"]), operation="UPDATE")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def copy_transfer(connection: sqlite3.Connection, *, transfer_id: int, user: UserInfo) -> dict[str, Any]:
    source = get_transfer(connection, transfer_id)
    payload = {
        "number": "", "date": date.today().isoformat(),
        "organization_id": source["organization_id"],
        "source_warehouse_id": source["source_warehouse_id"],
        "destination_warehouse_id": source["destination_warehouse_id"],
        "source_object_id": source["source_object_id"],
        "destination_object_id": source["destination_object_id"],
        "responsible_id": source["responsible_id"],
        "description": source["description"],
        "lines": [{"line_number": line["line_number"], "material_id": line["material_id"],
                   "name": line["name"], "unit_id": line["unit_id"],
                   "quantity": line["quantity"], "note": line["note"], 'package_id': line.get('package_id'), **axes(line)} for line in source["lines"]],
    }
    return save_transfer(connection, payload=payload, user=user)


def transfer_movements(connection: sqlite3.Connection, transfer_id: int) -> dict[str, Any]:
    transfer = get_transfer(connection, transfer_id)
    rows = connection.execute(
        """SELECT ir.*, wh.name AS warehouse_name, m.name AS material_name,
                  u.name AS unit_name, ob.name AS object_name
           FROM inventory_register ir
           LEFT JOIN warehouses wh ON wh.id = ir.warehouse_id
           LEFT JOIN materials m ON m.id = ir.material_id
           LEFT JOIN units u ON u.id = ir.unit_id
           LEFT JOIN objects ob ON ob.id = ir.object_id
           WHERE ir.recorder_type = 'goods_transfer' AND ir.recorder_id = ?
           ORDER BY ir.line_number, ir.movement_side DESC""", (transfer_id,),
    ).fetchall()
    return {"document": transfer, "inventory": hydrate_lines(connection, rows_to_dicts(rows)), "settlements": []}
