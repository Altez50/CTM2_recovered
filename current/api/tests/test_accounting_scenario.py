from __future__ import annotations

import pytest

from api.cost_accounting_services import (
    calculate_cost,
    distribute_overhead,
    get_cost_card,
    get_deviations,
    get_profitability,
    get_turnover_balance,
)
from api.scripts.seed_cost_test_scenario import P1, P2, ensure_calc_header, seed_sources


def test_deterministic_accounting_scenario_and_reconciliation(connection) -> None:
    refs = seed_sources(connection)
    distribution = distribute_overhead(connection, P1, refs["base"]["payroll"], object_id=0)
    assert distribution["total_distributed"] == pytest.approx(20_000.0)

    distributed = connection.execute(
        "SELECT object_id, SUM(amount) AS amount FROM overhead_distribution WHERE period = ? GROUP BY object_id",
        (P1,),
    ).fetchall()
    assert {row["object_id"]: row["amount"] for row in distributed} == {
        refs["o1"]: pytest.approx(12_000.0),
        refs["o2"]: pytest.approx(8_000.0),
    }
    assert sum(row["amount"] for row in distributed) == pytest.approx(20_000.0)

    result = calculate_cost(connection, ensure_calc_header(connection))
    assert result["status"] == "calculated"
    completed = {
        row["work_id"]: row
        for row in connection.execute(
            "SELECT work_id, actual_cost, deviation, profit FROM completed_works_cost WHERE period = ?",
            (P1,),
        ).fetchall()
    }
    assert completed[refs["w1"]]["actual_cost"] == pytest.approx(132_000.0)
    assert completed[refs["w2"]]["actual_cost"] == pytest.approx(44_000.0)
    assert completed[refs["w3"]]["actual_cost"] == pytest.approx(88_000.0)
    assert sum(row["deviation"] for row in completed.values()) == pytest.approx(34_000.0)

    card = get_cost_card(connection, refs["o1"], P1, P1)
    assert card["total_planned"] == 170_000.0
    # R-REP1: the card includes distributed overhead (164 000 direct + 12 000 overhead)
    # and its totals match the calculation result and the profitability report.
    assert card["total_actual"] == 176_000.0
    overhead_element = next(
        item for item in card["elements"] if item["cost_element_kind"] == "overhead"
    )
    assert overhead_element["actual_amount"] == 12_000.0
    assert sum(work["actual_cost"] for work in card["works"]) == pytest.approx(176_000.0)
    turnover = get_turnover_balance(connection, P2, P2)
    by_kind = {row["cost_element_kind"]: row for row in turnover["rows"]}
    assert by_kind["materials"]["closing_balance"] == 160_000.0
    assert by_kind["labor"]["closing_balance"] == 55_000.0
    deviations = get_deviations(connection, P1, threshold_pct=10)
    assert [row["work_id"] for row in deviations["rows"]] == [refs["w3"], refs["w2"]]
    profitability = get_profitability(connection, P1)
    assert sum(row["actual_cost"] for row in profitability["rows"]) == 264_000.0
    o1_profitability = next(
        row for row in profitability["rows"] if row["object_id"] == refs["o1"]
    )
    assert o1_profitability["actual_cost"] == pytest.approx(176_000.0)
