"""Validate trade contracts, report gaps, or execute their implemented CTM subset."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree as ET

from build_catalog import AREAS, PENDING, SCENARIOS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATALOG = HERE / "scenarios" / "catalog.json"
TYPE_DIRS = {"Catalog": "Catalogs", "Document": "Documents", "AccumulationRegister": "AccumulationRegisters",
             "InformationRegister": "InformationRegisters", "Report": "Reports"}
OPS = {"receipt", "issue", "payment", "transfer", "return", "refund", "adjustment", "opening", "reference", "post", "unpost", "delete", "assert", "business_contract", "observe"}


def validate(catalog, metadata=None):
    errors = []
    seen = set()
    required = {s["id"]: s["area"] for s in SCENARIOS}
    required.update({case[0]: area for area, cases in PENDING.items() for case in cases})
    present = {s.get("id"): s.get("area") for s in catalog.get("scenarios", [])}
    for ident in sorted(required.keys() - present.keys()):
        errors.append(f"Required business scenario missing: {ident}")
    for ident in sorted(present.keys() - required.keys(), key=str):
        errors.append(f"Scenario has no authoring definition: {ident}")
    for ident in required.keys() & present.keys():
        if required[ident] != present[ident]:
            errors.append(f"Scenario moved out of its required area: {ident}")
    if set(catalog.get("areas", {})) != set(AREAS):
        errors.append("Catalog omits or invents a required trade area")
    if catalog.get("schema_version") != 1 or catalog.get("reference_version") != "11.5.20.80":
        errors.append("Unsupported catalog schema or reference version")
    fixture_path = HERE / "scenarios" / "fixture.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if catalog.get("fixture") != fixture["id"]:
        errors.append("Catalog references an unknown fixture")
    for scenario in catalog.get("scenarios", []):
        ident = scenario.get("id", "<missing>")
        if not re.fullmatch(r"[A-Z]+-\d{3}", ident) or ident in seen:
            errors.append(f"Invalid or duplicate ID: {ident}")
        seen.add(ident)
        for field in ("title", "preconditions", "ut_objects", "steps", "dimensions"):
            if not scenario.get(field):
                errors.append(f"{ident}: empty {field}")
        if scenario.get("area") not in catalog.get("areas", {}):
            errors.append(f"{ident}: unknown area")
        if scenario.get("priority") not in ("P0", "P1", "P2"):
            errors.append(f"{ident}: unknown priority")
        if scenario.get("profile") not in ("core", "extended", "integration-sandbox"):
            errors.append(f"{ident}: unknown profile")
        execution = scenario.get("execution", {})
        if execution.get("ctm") not in (None, "api-v1"):
            errors.append(f"{ident}: unknown CTM executor")
        if execution.get("ctm") is None and not execution.get("blocker"):
            errors.append(f"{ident}: missing explicit blocker")
        if execution.get("ut") is not None or scenario.get("oracle", {}).get("ut_verified") is not False:
            errors.append(f"{ident}: unsupported claim of verified 1C scenario execution")
        if not any(step.get("expect") for step in scenario.get("steps", [])):
            errors.append(f"{ident}: no expected observations")
        saved = set()
        for index, step in enumerate(scenario.get("steps", [])):
            op = step.get("op")
            if execution.get("ctm") == "api-v1":
                if op not in OPS:
                    errors.append(f"{ident}/{index}: no executor for {op}")
                if op in ("receipt", "issue", "payment", "transfer", "return", "refund", "adjustment", "opening", "reference"):
                    if not step.get("ref") or step["ref"] in saved:
                        errors.append(f"{ident}/{index}: missing or duplicate document alias")
                    saved.add(step.get("ref"))
                if op in ("return", "refund", "adjustment") and step.get("source") not in saved:
                    errors.append(f"{ident}/{index}: unknown source alias")
                if op in ("post", "unpost", "delete") and step.get("ref") not in saved:
                    errors.append(f"{ident}/{index}: unknown document alias")
                if "contract" in step and step["contract"] not in fixture["contracts"]:
                    errors.append(f"{ident}/{index}: unknown fixture contract")
                if op in ('business_contract', 'observe'):
                    authored = {case[0]: case[4] for area in ('lifecycle', 'procurement','sales') for case in PENDING[area]
                                if case[0] in {'LIFE-005', 'LIFE-006', 'LIFE-008', 'LIFE-009', 'LIFE-010', 'LIFE-011', 'PUR-005', 'PUR-006', 'PUR-007', 'PUR-008', 'PUR-009', 'PUR-010','SAL-006','SAL-007','SAL-008','SAL-009','SAL-010'}}
                    if ident not in authored or (op == 'observe' and step.get('expect') != authored[ident]):
                        errors.append(f'{ident}/{index}: unknown business adapter or changed authored expectations')
                elif "expect" in step and not set(step["expect"]) <= {"debts", "stock", "movements", "turnover", "advances", "financials", "dimensions"}:
                    errors.append(f"{ident}/{index}: unsupported assertion")
            elif op not in ("business_contract", "observe"):
                errors.append(f"{ident}/{index}: unknown specification action")
        for obj in scenario.get("ut_objects", []):
            kind, _, name = obj.partition(".")
            if kind not in TYPE_DIRS or not name:
                errors.append(f"{ident}: invalid metadata reference {obj}")
            elif metadata and not (metadata / TYPE_DIRS[kind] / f"{name}.xml").is_file():
                errors.append(f"{ident}: missing UT metadata {obj}")
    for area in catalog.get("areas", {}):
        if not any(s["area"] == area for s in catalog.get("scenarios", [])):
            errors.append(f"Area without scenarios: {area}")
    if not seen:
        errors.append("Empty scenario catalog")
    return errors


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit_reference(scenarios):
    from ut_connection import connect, query
    ib = connect()
    if ib.Metadata.Name != "УправлениеТорговлей" or ib.Metadata.Version != "11.5.20.80":
        raise RuntimeError("Reference configuration does not match the catalog")
    objects = sorted({obj for s in scenarios for obj in s["ut_objects"]})
    rows = []
    for obj in objects:
        kind, name = obj.split(".", 1)
        collection = getattr(ib.Metadata, TYPE_DIRS[kind])
        found = collection.Find(name)
        if found is None:
            raise RuntimeError(f"Reference metadata object not found: {obj}")
        result = {"object": obj, "exists": True, "scenario_execution": "not_run"}
        if kind == "Document":
            for row in query(ib, f"ВЫБРАТЬ КОЛИЧЕСТВО(*) ИЗ Документ.{name} ГДЕ Проведен И НЕ ПометкаУдаления"):
                result["posted_documents"] = int(row.Get(0))
        rows.append(result)
    return {"mode": "metadata-and-source-availability-only", "read_only": True,
            "scenario_execution": "not_run", "objects": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "coverage", "run", "audit-reference"))
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--metadata", type=Path, help="UT XML source directory for metadata validation")
    parser.add_argument("--implemented-only", action="store_true", help="exit successfully for a passing implemented subset; full coverage remains incomplete")
    parser.add_argument("--area", help="select one area")
    parser.add_argument("--profile", choices=("core", "extended", "integration-sandbox"))
    parser.add_argument("--ids", help="comma-separated scenario IDs")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "trade-harness" / "suite-report.json")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    errors = validate(catalog, args.metadata)
    if errors:
        print("\n".join(errors))
        save(args.report, {"contracts_valid": False, "errors": errors})
        return 1
    wanted = set(args.ids.split(",")) if args.ids else set()
    unknown = wanted - {s["id"] for s in catalog["scenarios"]}
    if unknown or (args.area and args.area not in catalog["areas"]):
        parser.error(f"Unknown IDs/area: {sorted(unknown)} / {args.area}")
    scenarios = [s for s in catalog["scenarios"] if (not wanted or s["id"] in wanted)
                 and (not args.area or s["area"] == args.area) and (not args.profile or s["profile"] == args.profile)]
    if not scenarios:
        parser.error("Empty selection")
    outcomes = {s["id"]: {"id": s["id"], "area": s["area"], "title": s["title"],
                "ctm": "not_run" if s["execution"]["ctm"] else "blocked", "ut": "not_run",
                "blocker": s["execution"]["blocker"]} for s in scenarios}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "contracts_valid": True,
              "selection": {"area": args.area, "profile": args.profile, "ids": sorted(wanted)},
              "selected": len(scenarios), "full_scope_passed": False, "reference_scenarios_passed": False,
              "mode": args.mode, "implemented_subset_only": args.implemented_only}
    if args.mode == "audit-reference":
        try:
            report["reference_audit"] = audit_reference(scenarios)
        except Exception as error:
            message = str(error)
            secret = os.environ.get("CTM_UT_PASSWORD")
            report["error"] = message.replace(secret, "***") if secret else message
    if args.mode == "run":
        runnable = [s["id"] for s in scenarios if s["execution"]["ctm"]]
        if runnable:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            junit = args.report.with_suffix(".junit.xml")
            junit.unlink(missing_ok=True)
            log = args.report.with_suffix(".pytest.log")
            env = dict(os.environ, CTM_TRADE_SCENARIO_IDS=json.dumps(runnable))
            with log.open("w", encoding="utf-8") as output:
                process = subprocess.run([sys.executable, "-m", "pytest", "api/tests/test_trade_catalog_scenarios.py",
                                          "--junitxml", str(junit.resolve()), "--disable-warnings"],
                                         cwd=ROOT / "current", env=env, stdout=output, stderr=subprocess.STDOUT)
            if junit.exists():
                for case in ET.parse(junit).iter("testcase"):
                    match = re.search(r"\[([A-Z]+-\d{3})\]$", case.get("name", ""))
                    if match and match[1] in outcomes:
                        failure = case.find("failure")
                        error = case.find("error")
                        skipped = case.find("skipped")
                        record = outcomes[match[1]]
                        record["ctm"] = "failed" if failure is not None else "error" if error is not None else "blocked" if skipped is not None else "passed"
                        if failure is not None or error is not None:
                            record["details"] = (failure if failure is not None else error).get("message")
            for ident in runnable:
                if outcomes[ident]["ctm"] == "not_run":
                    outcomes[ident].update(ctm="error", details=f"No test result; pytest exit code {process.returncode}")
            report["pytest_exit_code"] = process.returncode
            report["pytest_log"] = str(log)
    counts = Counter(row["ctm"] for row in outcomes.values())
    report["counts"] = dict(counts)
    report["areas"] = {area: dict(Counter(row["ctm"] for row in outcomes.values() if row["area"] == area))
                       for area in catalog["areas"] if any(row["area"] == area for row in outcomes.values())}
    report["scenarios"] = list(outcomes.values())
    # Full CTM success must never be inferred from structural validation or omissions.
    report["selected_scope_passed"] = args.mode == "run" and counts.get("passed", 0) == len(scenarios) and report.get("pytest_exit_code") == 0
    report["full_scope_passed"] = report["selected_scope_passed"] and len(scenarios) == len(catalog["scenarios"])
    save(args.report, report)
    print(json.dumps({key: report[key] for key in ("contracts_valid", "selected", "counts", "full_scope_passed", "reference_scenarios_passed")}, ensure_ascii=False))
    print(f"Report: {args.report}")
    if "error" in report:
        print(report["error"])
        return 1
    if args.mode == "run":
        return 0 if report["selected_scope_passed"] or (args.implemented_only and counts.get("passed", 0) > 0
                      and not counts.get("failed") and not counts.get("error") and not counts.get("not_run")
                      and report.get("pytest_exit_code") == 0) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
