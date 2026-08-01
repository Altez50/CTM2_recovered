"""Сквозной пример учёта (сценарий 7A из TESTING_PLAN.md).

Наполняет локальную БД детерминированными данными для тестирования отчётов
кост-аккаунтинга: справочники → плановые/фактические затраты → распределение
накладных → калькуляция. Источники регистров проводятся напрямую, а
``overhead_distribution`` и ``completed_works_cost`` строятся **реальными**
сервисами ``distribute_overhead`` и ``calculate_cost``, после чего их числа
сверяются с эталоном из TESTING_PLAN.md (раздел 7A).

Запуск (из каталога ``current/``):

    python -m api.scripts.seed_cost_test_scenario
    python -m api.scripts.seed_cost_test_scenario --force   # очистить и пересеять

Скрипт идемпотентен: очищает только строки своего сценария (по object_id
объектов «Объект А»/«Объект Б» и периодам 2025-01/2025-02), не трогая прочие
данные.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import HTTPException

from api.cost_accounting_services import calculate_cost, distribute_overhead
from api.database import get_connection, new_uuid, utcnow_iso

# Периоды сценария
P1 = "2025-01"
P2 = "2025-02"
PERIODS = (P1, P2)

# Опознавательные номера документов сценария (для очистки)
OH_DOC_NUMBER = "TEST-OH-2025-01"
CALC_NUMBER = "TEST-CALC-2025-01"
# Метка фактических затрат сценария
REGISTRAR_TAG = "TestScenario"


# ── Разрешение ссылок по именам ───────────────────────────────────────────────


def _cost_element_id(conn, kind: str) -> int:
    row = conn.execute(
        "SELECT id FROM cost_elements WHERE kind = ? AND marked_for_deletion = 0",
        (kind,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Предопределённый элемент затрат «{kind}» не найден. "
                           "Выполните инициализацию БД (ensure_runtime_schema).")
    return int(row["id"])


def _allocation_base_id(conn, kind: str) -> int:
    row = conn.execute(
        "SELECT id FROM allocation_bases WHERE kind = ?", (kind,)
    ).fetchone()
    if not row:
        raise RuntimeError(f"База распределения «{kind}» не найдена.")
    return int(row["id"])


def _object_id(conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM objects WHERE name = ? AND marked_for_deletion = 0", (name,)
    ).fetchone()
    return int(row["id"]) if row else None


def _work_id(conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM works WHERE name = ? AND marked_for_deletion = 0", (name,)
    ).fetchone()
    return int(row["id"]) if row else None


def _machine_id(conn, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM machines WHERE name = ? AND marked_for_deletion = 0", (name,)
    ).fetchone()
    return int(row["id"]) if row else None


# ── Создание справочников ────────────────────────────────────────────────────


def _ensure_object(conn, name: str, address: str) -> int:
    existing = _object_id(conn, name)
    if existing:
        return existing
    now = utcnow_iso()
    conn.execute(
        """INSERT INTO objects
           (name, address, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES (?, ?, 0, 0, ?, ?, ?, ?, 0)""",
        (name, address, now, now, new_uuid(), now),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _ensure_work(conn, name: str, unit: str) -> int:
    existing = _work_id(conn, name)
    if existing:
        return existing
    now = utcnow_iso()
    conn.execute(
        """INSERT INTO works
           (name, code, unit, price, labor_rate, marked_for_deletion, is_group,
            created_at, modified_at, uuid, updated_at, is_deleted)
           VALUES (?, '', ?, 0, 0, 0, 0, ?, ?, ?, ?, 0)""",
        (name, unit, now, now, new_uuid(), now),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _ensure_machine(conn, name: str, code: str, cost_per_hour: float) -> int:
    existing = _machine_id(conn, name)
    if existing:
        return existing
    now = utcnow_iso()
    conn.execute(
        """INSERT INTO machines
           (name, code, cost_per_hour, operator_rate_per_hour, unit,
            marked_for_deletion, created_at, modified_at)
           VALUES (?, ?, ?, 0, 'маш.-ч', 0, ?, ?)""",
        (name, code, cost_per_hour, now, now),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


# ── Очистка предыдущего прогона ──────────────────────────────────────────────


def clean(conn) -> dict[str, int]:
    """Удалить только строки сценария (по объектам и периодам)."""
    o1 = _object_id(conn, "Объект А")
    o2 = _object_id(conn, "Объект Б")
    obj_ids = [i for i in (o1, o2) if i]
    deleted: dict[str, int] = {}

    def _del(table: str, sql: str, params: tuple) -> None:
        cur = conn.execute(f"DELETE FROM {table} WHERE {sql}", params)
        deleted[table] = deleted.get(table, 0) + cur.rowcount

    if obj_ids:
        placeholders = ",".join("?" * len(obj_ids))
        _del("actual_costs",
             f"object_id IN ({placeholders}) AND period IN (?, ?)",
             (*obj_ids, P1, P2))
        _del("planned_costs",
             f"object_id IN ({placeholders}) AND period = ?",
             (*obj_ids, P1))
        _del("overhead_distribution",
             f"object_id IN ({placeholders}) AND period = ?",
             (*obj_ids, P1))
        # Калькуляции сценария (по number) + их completed_works_cost
        calc_rows = conn.execute(
            "SELECT id FROM cost_calculations WHERE number = ?", (CALC_NUMBER,)
        ).fetchall()
        for r in calc_rows:
            _del("completed_works_cost", "calculation_id = ?", (int(r["id"]),))
        _del("completed_works_cost",
             f"object_id IN ({placeholders}) AND period = ?",
             (*obj_ids, P1))

    # Документы накладных сценария
    oh_rows = conn.execute(
        "SELECT id FROM overhead_expenses WHERE number = ?", (OH_DOC_NUMBER,)
    ).fetchall()
    for r in oh_rows:
        _del("overhead_expense_lines", "document_id = ?", (int(r["id"]),))
    _del("overhead_expenses", "number = ?", (OH_DOC_NUMBER,))
    _del("cost_calculations", "number = ?", (CALC_NUMBER,))
    return deleted


# ── Сидирование источников ───────────────────────────────────────────────────


def seed_sources(conn) -> dict[str, Any]:
    """Создать справочники и заполнить плановые/фактические регистры."""
    # Элементы затрат и базы (предопределённые)
    ce = {k: _cost_element_id(conn, k) for k in
          ("materials", "labor", "machinery", "subcontract", "other_direct", "overhead")}
    base = {k: _allocation_base_id(conn, k) for k in ("payroll", "direct_costs", "labor_days")}

    # Справочники
    o1 = _ensure_object(conn, "Объект А", "г. Астрахань, ул. Строителей 1")
    o2 = _ensure_object(conn, "Объект Б", "г. Астрахань, ул. Строителей 2")
    w1 = _ensure_work(conn, "Кладка", "м³")
    w2 = _ensure_work(conn, "Монтаж", "т")
    w3 = _ensure_work(conn, "Отделка", "м²")
    _ensure_machine(conn, "Кран", "KRAN-01", 1000.0)

    now = utcnow_iso()

    # Плановые затраты (period = 2025-01)
    planned = [
        (o1, w1, ce["materials"], 100000.0),
        (o1, w1, ce["labor"], 30000.0),
        (o1, w2, ce["machinery"], 40000.0),
        (o2, w3, ce["materials"], 60000.0),
    ]
    conn.executemany(
        """INSERT INTO planned_costs
           (period, object_id, work_id, cost_element_id,
            planned_quantity, planned_amount, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?)""",
        [(P1, oid, wid, cid, amt, now) for oid, wid, cid, amt in planned],
    )

    # Фактические затраты — period 2025-01
    actual_p1 = [
        (o1, w1, ce["materials"], 90000.0, 100.0),
        (o1, w1, ce["labor"], 30000.0, 30.0),
        (o1, w2, ce["machinery"], 44000.0, 40.0),
        (o2, w3, ce["materials"], 60000.0, 60.0),
        (o2, w3, ce["labor"], 20000.0, 20.0),
    ]
    conn.executemany(
        """INSERT INTO actual_costs
           (period, date, registrar_type, registrar_id, object_id, estimate_id,
            work_id, cost_element_id, quantity, amount, created_at)
           VALUES (?, ?, ?, 0, ?, NULL, ?, ?, ?, ?, ?)""",
        [(P1, f"{P1}-15", REGISTRAR_TAG, oid, wid, cid, qty, amt, now)
         for oid, wid, cid, amt, qty in actual_p1],
    )

    # Фактические затраты — period 2025-02 (для входящего сальдо в оборотке)
    actual_p2 = [
        (o1, w1, ce["materials"], 10000.0, 10.0),
        (o1, w1, ce["labor"], 5000.0, 5.0),
    ]
    conn.executemany(
        """INSERT INTO actual_costs
           (period, date, registrar_type, registrar_id, object_id, estimate_id,
            work_id, cost_element_id, quantity, amount, created_at)
           VALUES (?, ?, ?, 0, ?, NULL, ?, ?, ?, ?, ?)""",
        [(P2, f"{P2}-10", REGISTRAR_TAG, oid, wid, cid, qty, amt, now)
         for oid, wid, cid, amt, qty in actual_p2],
    )

    # Документ накладных расходов + строка (пул = 20 000 за 2025-01)
    conn.execute(
        """INSERT INTO overhead_expenses
           (uuid, number, date, period, is_distributed, marked_for_deletion, created_at)
           VALUES (?, ?, ?, ?, 0, 0, ?)""",
        (new_uuid(), OH_DOC_NUMBER, f"{P1}-20", P1, now),
    )
    oh_doc_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """INSERT INTO overhead_expense_lines
           (document_id, line_number, cost_element_id, counterparty_id, sum, description)
           VALUES (?, 1, ?, NULL, ?, 'Тестовый пул накладных 7A')""",
        (oh_doc_id, ce["overhead"], 20000.0),
    )

    conn.commit()

    return {
        "ce": ce, "base": base,
        "o1": o1, "o2": o2, "w1": w1, "w2": w2, "w3": w3,
        "oh_doc_id": oh_doc_id,
    }


def ensure_calc_header(conn) -> int:
    row = conn.execute(
        "SELECT id FROM cost_calculations WHERE number = ?", (CALC_NUMBER,)
    ).fetchone()
    if row:
        return int(row["id"])
    now = utcnow_iso()
    conn.execute(
        """INSERT INTO cost_calculations
           (uuid, number, period, date, object_id, status,
            marked_for_deletion, created_at)
           VALUES (?, ?, ?, ?, 0, 'draft', 0, ?)""",
        (new_uuid(), CALC_NUMBER, P1, f"{P1}-25", now),
    )
    calc_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    return calc_id


# ── Сверка с эталоном 7A ─────────────────────────────────────────────────────


def _approx(a: float, b: float, eps: float = 0.005) -> bool:
    return abs(a - b) <= eps


def reconcile(conn, refs: dict[str, Any]) -> int:
    """Сверить полученные числа с эталоном из TESTING_PLAN.md (7A). Возвращает число провалов."""
    o1, o2 = refs["o1"], refs["o2"]
    w1, w2, w3 = refs["w1"], refs["w2"], refs["w3"]
    fails = 0
    lines: list[str] = []

    def check(label: str, got: float, expected: float) -> None:
        nonlocal fails
        ok = _approx(got, expected)
        lines.append(f"  [{'OK' if ok else 'FAIL'}] {label}: получено {got:.2f} ≈ эталон {expected:.2f}")
        if not ok:
            fails += 1

    lines.append("Сверка completed_works_cost (2025-01) с эталоном 7A:")
    rows = {int(r["work_id"]): r for r in conn.execute(
        """SELECT object_id, work_id, completed_quantity, planned_cost,
                  actual_cost, deviation, contract_value, profit
           FROM completed_works_cost WHERE period = ?""",
        (P1,),
    ).fetchall()}

    # O1/W1
    r = rows.get(w1)
    check("O1/W1 фактическая", float(r["actual_cost"]) if r else 0.0, 132000.0)
    check("O1/W1 отклонение", float(r["deviation"]) if r else 0.0, 2000.0)
    check("O1/W1 прибыль", float(r["profit"]) if r else 0.0, -2000.0)
    # O1/W2
    r = rows.get(w2)
    check("O1/W2 фактическая", float(r["actual_cost"]) if r else 0.0, 44000.0)
    check("O1/W2 отклонение", float(r["deviation"]) if r else 0.0, 4000.0)
    # O2/W3
    r = rows.get(w3)
    check("O2/W3 фактическая", float(r["actual_cost"]) if r else 0.0, 88000.0)
    check("O2/W3 отклонение", float(r["deviation"]) if r else 0.0, 28000.0)

    # Распределение накладных: Σ shares == пул (20 000)
    pool = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM overhead_distribution WHERE period = ?", (P1,)
    ).fetchone()[0])
    check("Σ распределённых накладных == пул", pool, 20000.0)

    # Доля O1 (12 000) и O2 (8 000)
    o1_oh = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM overhead_distribution WHERE period = ? AND object_id = ?",
        (P1, o1),
    ).fetchone()[0])
    o2_oh = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM overhead_distribution WHERE period = ? AND object_id = ?",
        (P1, o2),
    ).fetchone()[0])
    check("Накладные O1 (по ФОТ)", o1_oh, 12000.0)
    check("Накладные O2 (по ФОТ)", o2_oh, 8000.0)

    print("\n".join(lines))
    return fails


# ── Точка входа ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Сквозной пример учёта 7A (TESTING_PLAN.md).")
    parser.add_argument("--force", action="store_true",
                        help="очистить предыдущий прогон и пересеять")
    args = parser.parse_args()

    conn = get_connection()

    if args.force or _scenario_seeded(conn):
        print("Очистка предыдущего прогона сценария ...")
        deleted = clean(conn)
        conn.commit()
        if any(deleted.values()):
            print("  удалено:", ", ".join(f"{k}={v}" for v, k in
                  [(v, k) for k, v in deleted.items()] if v))

    print("Сидирование источников (справочники, плановые/фактические затраты, пул накладных) ...")
    refs = seed_sources(conn)

    print("Создание заголовка калькуляции ...")
    calc_id = ensure_calc_header(conn)

    # Перевести калькуляцию в draft на случай повторного прогона
    conn.execute("UPDATE cost_calculations SET status = 'draft' WHERE id = ?", (calc_id,))
    conn.commit()

    print(f"Распределение накладных (period={P1}, база=payroll, object_id=0) ...")
    try:
        dist = distribute_overhead(conn, P1, refs["base"]["payroll"], object_id=0)
        print(f"  распределено: {dist['total_distributed']:.2f} по {dist['record_count']} записям "
              f"(база «{dist['allocation_base_name']}»)")
    except HTTPException as e:
        print(f"  [!] distribute_overhead не выполнен: {e.detail}")
        print("      Если на периоде уже есть чужое распределение — очистите overhead_distribution "
              "для 2025-01 и повторите с --force.")

    print(f"Расчёт калькуляции id={calc_id} (period={P1}, object_id=0) ...")
    try:
        calc = calculate_cost(conn, calc_id)
        print(f"  статус: {calc['status']}, записей: {calc['record_count']}")
    except HTTPException as e:
        print(f"  [!] calculate_cost не выполнен: {e.detail}")

    fails = reconcile(conn, refs)
    print()
    if fails:
        print(f"[!] Сверка завершена с {fails} расхождением(ями) — возможен баг или эталон устарел.")
    else:
        print("[OK] Все числа сценария 7A совпали с эталоном. Отчёты можно тестировать.")
    print("    База готова к проверке отчётов (раздел 7.2–7.4 TESTING_PLAN.md).")
    conn.close()
    return 0


def _scenario_seeded(conn) -> bool:
    """Признак того, что сценарий уже сеяли (есть объект А или тестовый пул)."""
    return (
        _object_id(conn, "Объект А") is not None
        or conn.execute(
            "SELECT COUNT(*) FROM overhead_expenses WHERE number = ?", (OH_DOC_NUMBER,)
        ).fetchone()[0] > 0
    )


if __name__ == "__main__":
    sys.exit(main())
