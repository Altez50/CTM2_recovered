"""Executable CTM subset. Missing capabilities are tracked by suite.py, never skipped here."""
import json
import os
from pathlib import Path

import pytest

from api.tests.trade_scenario_engine import execute_scenario

CATALOG = Path(__file__).resolve().parents[3] / "runner" / "trade_harness" / "scenarios" / "catalog.json"
SCENARIOS = json.loads(CATALOG.read_text(encoding="utf-8"))["scenarios"]
SELECTED = set(json.loads(os.environ.get("CTM_TRADE_SCENARIO_IDS", "[]")))
EXECUTABLE = [s for s in SCENARIOS if s["execution"]["ctm"] == "api-v1" and (not SELECTED or s["id"] in SELECTED)]
if SELECTED - {s["id"] for s in EXECUTABLE}:
    raise RuntimeError("Selection contains unknown scenarios or scenarios without an executor")


@pytest.mark.parametrize("scenario", EXECUTABLE, ids=[s["id"] for s in EXECUTABLE])
def test_trade_catalog(scenario, client, admin_headers, connection):
    execute_scenario(scenario, client, admin_headers, connection)
