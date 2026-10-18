"""Prevent false-green coverage when contracts disappear or lack executors."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "runner" / "trade_harness" / "suite.py"
CATALOG = SUITE.parent / "scenarios" / "catalog.json"


@pytest.mark.parametrize("corruption", ["remove_required_case", "claim_unverified_reference"])
def test_catalog_rejects_lost_contract_or_false_reference_claim(tmp_path, corruption):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if corruption == "remove_required_case":
        catalog["scenarios"] = [case for case in catalog["scenarios"] if case["id"] != "RET-001"]
    else:
        catalog["scenarios"][0]["oracle"]["ut_verified"] = True
    source = tmp_path / "bad-catalog.json"
    source.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    report = tmp_path / "validation.json"
    result = subprocess.run([sys.executable, str(SUITE), "validate", "--catalog", str(source),
                             "--report", str(report)], cwd=ROOT, capture_output=True)
    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["contracts_valid"] is False
    assert any("RET-001" in error if corruption == "remove_required_case" else "verified 1C" in error
               for error in data["errors"])


def test_required_unimplemented_scenario_is_blocked_not_skipped(tmp_path):
    report = tmp_path / "blocked.json"
    result = subprocess.run([sys.executable, str(SUITE), "run", "--ids", "RET-008",
                             "--report", str(report)], cwd=ROOT, capture_output=True)
    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["counts"] == {"blocked": 1}
    assert data["full_scope_passed"] is False
    assert data["reference_scenarios_passed"] is False
    assert data["scenarios"][0]["ut"] == "not_run"
