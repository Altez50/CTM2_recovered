"""Read posted 1C documents and replay their debt projection in an isolated CTM DB."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile

from ut_connection import connect, query

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "data" / "trade-harness"
KINDS = {
    "receipt": ("ПриобретениеТоваровУслуг", "РасчетыСПоставщиками", "payable", "Расход"),
    "issue": ("РеализацияТоваровУслуг", "РасчетыСКлиентами", "receivable", "Приход"),
}
DIMS = ("organization", "counterparty", "contract")


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def identity(ib, reference):
    return {"uuid": ib.XMLString(reference), "name": ib.String(reference)}


def discover(ib, count):
    selected = []
    for kind, (document, _, _, _) in KINDS.items():
        candidates = []
        for row in query(ib, f"""
            ВЫБРАТЬ ПЕРВЫЕ 250 Ссылка, Организация, Контрагент, Договор
            ИЗ Документ.{document}
            ГДЕ Проведен И НЕ ПометкаУдаления И СуммаДокумента > 0
                И Валюта.Код = "643"
                И Договор <> ЗНАЧЕНИЕ(Справочник.ДоговорыКонтрагентов.ПустаяСсылка)
                И Контрагент <> ЗНАЧЕНИЕ(Справочник.Контрагенты.ПустаяСсылка)
            УПОРЯДОЧИТЬ ПО Дата УБЫВ, Ссылка
        """):
            candidates.append({"kind": kind, "uuid": ib.XMLString(row.Get(0)),
                               "axes": [ib.XMLString(row.Get(i)) for i in (1, 2, 3)]})
        seen = [set(), set(), set()]
        for _ in range(count):
            if not candidates:
                raise RuntimeError(f"Not enough posted RUB {kind} documents (need {count})")
            item = max(candidates, key=lambda c: sum(
                weight for i, weight in enumerate((100, 10, 1)) if c["axes"][i] not in seen[i]
            ))
            candidates.remove(item)
            for i, value in enumerate(item.pop("axes")):
                seen[i].add(value)
            selected.append(item)
    return selected


def read_document(ib, item):
    kind = item["kind"]
    document, register, direction, positive = KINDS[kind]
    ref = getattr(ib.Documents, document).GetRef(ib.NewObject("УникальныйИдентификатор", item["uuid"]))
    rows = list(query(ib, f"""
        ВЫБРАТЬ Номер, Дата, Организация, Контрагент, Договор, СуммаДокумента,
            Валюта.Код, Проведен, ПометкаУдаления
        ИЗ Документ.{document} ГДЕ Ссылка = &Ref
    """, Ref=ref))
    if len(rows) != 1:
        raise RuntimeError(f"Source document not found: {kind}/{item['uuid']}")
    row = rows[0]
    if not row.Get(7) or row.Get(8) or str(row.Get(6)) != "643":
        raise RuntimeError(f"Source document is no longer an active posted RUB document: {item['uuid']}")
    result = {**item, "number": str(row.Get(0)), "date": row.Get(1).strftime("%Y-%m-%d"),
              "amount": str(money(row.Get(5))), "direction": direction,
              **{dim: identity(ib, row.Get(i)) for dim, i in zip(DIMS, (2, 3, 4))},
              "movements": []}
    for movement in query(ib, f"""
        ВЫБРАТЬ ВидДвижения, Сумма,
            АналитикаУчетаПоПартнерам.Организация,
            АналитикаУчетаПоПартнерам.Контрагент,
            АналитикаУчетаПоПартнерам.Договор, Валюта.Код
        ИЗ РегистрНакопления.{register}
        ГДЕ Регистратор = &Ref И Активность И Сумма <> 0
    """, Ref=ref):
        if str(movement.Get(5)) != "643":
            raise RuntimeError(f"Non-RUB register movement: {item['uuid']}")
        signed = money(movement.Get(1))
        if ib.String(movement.Get(0)) != positive:
            signed = -signed
        result["movements"].append({
            "amount": str(signed),
            **{dim: identity(ib, movement.Get(i)) for dim, i in zip(DIMS, (2, 3, 4))},
        })
    if not result["movements"]:
        raise RuntimeError(f"No active debt movements in {register}: {item['uuid']}")
    return result


def replay(documents, database_path):
    # Set before importing the application: never connect to its working database.
    os.environ.update(DATABASE_PATH=str(database_path), DB_TYPE="sqlite", CTM_ENV="test",
                      ALLOW_SEED_DATA="true", SYNC_TOKEN="", RESET_DATABASE_ON_SCHEMA_MISMATCH="false")
    sys.path.insert(0, str(ROOT / "current"))
    from fastapi.testclient import TestClient
    from api.main import app

    failures = []
    expected = defaultdict(lambda: {"payable": Decimal(0), "receivable": Decimal(0)})
    id_maps = {dim: {} for dim in DIMS}
    reverse = {dim: {} for dim in DIMS}
    compared = []
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        login.raise_for_status()
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}

        def request(method, url, **kwargs):
            response = client.request(method, url, headers=headers, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"CTM {method} {url}: {response.status_code} {response.text}")
            return response.json().get("data")

        def mapped(dim, reference, document):
            uid = reference["uuid"]
            if uid not in id_maps[dim]:
                if dim == "contract":
                    payload = {"number": reference["name"][:100], "vat_rate": 0,
                               "organization_id": mapped("organization", document["organization"], document),
                               "counterparty_id": mapped("counterparty", document["counterparty"], document)}
                else:
                    payload = {"name": reference["name"][:255]}
                collection = {"organization": "organizations", "counterparty": "counterparties",
                              "contract": "contracts"}[dim]
                ident = request("POST", f"/api/references/{collection}", json=payload)["id"]
                id_maps[dim][uid] = ident
                reverse[dim][ident] = uid
            return id_maps[dim][uid]

        def check_balances(stage, filters=None):
            rows = request("GET", "/api/settlements/balance", params=filters or {})
            actual = {}
            for row in rows:
                k = tuple(reverse[dim][row[f"{dim}_id"]] for dim in DIMS)
                if k in actual:
                    failures.append({"stage": stage, "error": "duplicate CTM balance slice", "key": k})
                actual[k] = {direction: money(row[f"{direction}_balance"]) for direction in ("payable", "receivable")}
            selected = {k: v for k, v in expected.items() if any(v.values()) and all(
                k[DIMS.index(dim.removesuffix("_id"))] == reverse[dim.removesuffix("_id")][ident]
                for dim, ident in (filters or {}).items()
            )}
            if actual != selected:
                failures.append({"stage": stage, "filters": filters or {},
                                 "expected": [{"key": k, **{d: str(v) for d, v in values.items()}} for k, values in selected.items()],
                                 "actual": [{"key": k, **{d: str(v) for d, v in values.items()}} for k, values in actual.items()]})

        for index, document in enumerate(documents):
            dimensions = {f"{dim}_id": mapped(dim, document[dim], document) for dim in DIMS}
            collection = "receipts" if document["kind"] == "receipt" else "issues"
            # Debt projection only: one service line with the gross amount. No claim of
            # equivalence for VAT, inventory, discounts or cost calculation.
            created = request("POST", f"/api/goods/{collection}", json={
                **dimensions, "number": f"UT-{index}", "date": document["date"], "auto_schedule": False,
                "description": f"1C debt projection {document['uuid']}",
                "lines": [{"line_number": 1, "name": "Debt projection (gross amount)",
                           "quantity": 1, "price_without_vat": float(document["amount"]), "vat_rate": 0}],
            })
            check_balances(f"draft:{document['uuid']}")
            request("POST", f"/api/goods/{collection}/{created['id']}/post", params={"auto_schedule": "false"})
            ut_rows = defaultdict(Decimal)
            for movement in document["movements"]:
                k = tuple(movement[dim]["uuid"] for dim in DIMS)
                amount = money(movement["amount"])
                ut_rows[k] += amount
                expected[k][document["direction"]] += amount
            ctm_rows = request("GET", f"/api/goods/{document['kind']}/{created['id']}/movements")["settlements"]
            actual_rows = defaultdict(Decimal)
            for row in ctm_rows:
                k = tuple(reverse[dim][row[f"{dim}_id"]] for dim in DIMS)
                actual_rows[k] += money(row["accrual_amount"]) - money(row["payment_amount"])
                if row["direction"] != document["direction"]:
                    failures.append({"stage": document["uuid"], "error": "wrong settlement direction"})
            passed = dict(ut_rows) == dict(actual_rows)
            compared.append({"kind": document["kind"], "uuid": document["uuid"], "number": document["number"],
                             "amount": document["amount"], "passed": passed,
                             "ut": [{"key": k, "amount": str(v)} for k, v in ut_rows.items()],
                             "ctm": [{"key": k, "amount": str(v)} for k, v in actual_rows.items()]})
            if not passed:
                failures.append({"stage": document["uuid"], "error": "document debt movements differ"})
            check_balances(f"posted:{document['uuid']}")

        filter_sets = set()
        for document in documents:
            for mask in itertools.product((False, True), repeat=3):
                filter_sets.add(tuple((f"{dim}_id", id_maps[dim][document[dim]["uuid"]])
                                      for dim, enabled in zip(DIMS, mask) if enabled))
        for filters in sorted(filter_sets):
            check_balances("filtered-final", dict(filters))
    return {"passed": not failures, "documents": compared, "filter_checks": len(filter_sets),
            "failures": failures, "slice_count": len(expected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="explicitly select and save a new source sample")
    parser.add_argument("--sample-size", type=int, default=4, help="documents per direction on discovery")
    parser.add_argument("--selection", type=Path, default=LOCAL / "selection.json")
    parser.add_argument("--report", type=Path, default=LOCAL / "latest-report.json")
    args = parser.parse_args()
    if args.sample_size < 1:
        parser.error("--sample-size must be positive")
    source = {"host": os.environ.get("CTM_UT_HOST", "localhost"),
              "infobase": os.environ.get("CTM_UT_INFOBASE", "UTrecover")}
    report = {"passed": False, "source": source, "checked_at": datetime.now(timezone.utc).isoformat(),
              "scope": "posted-document-debt-projection", "source_read_only": True}
    try:
        print(f"Connecting to {source['host']}/{source['infobase']} (read only)...", flush=True)
        ib = connect()
        config = {"name": ib.Metadata.Name, "version": ib.Metadata.Version}
        report["configuration"] = config
        if config != {"name": "УправлениеТорговлей", "version": "11.5.20.80"}:
            raise RuntimeError(f"Unexpected reference configuration: {config}")
        if args.discover:
            manifest = {"source": source, "configuration": config, "documents": discover(ib, args.sample_size)}
            save(args.selection, manifest)
        else:
            manifest = json.loads(args.selection.read_text(encoding="utf-8"))
            if manifest["source"] != source or manifest["configuration"] != config:
                raise RuntimeError("Selection belongs to a different reference database/configuration")
        items = manifest["documents"]
        if not items or {item["kind"] for item in items} != set(KINDS):
            raise RuntimeError("Selection must include both receipts and issues")
        if len({(item["kind"], item["uuid"]) for item in items}) != len(items):
            raise RuntimeError("Duplicate documents in selection")
        documents = [read_document(ib, item) for item in items]
        report["coverage"] = {dim: len({d[dim]["uuid"] for d in documents}) for dim in DIMS}
        if min(report["coverage"].values()) < 2:
            raise RuntimeError(f"Insufficient dimension coverage: {report['coverage']}")
        save(args.report.parent / "latest-source.json", {"source": source, "configuration": config, "documents": documents})
        print(f"Read {len(documents)} source documents. Replaying in temporary CTM database...", flush=True)
        with tempfile.TemporaryDirectory(prefix="ctm-ut-reconcile-") as directory:
            report.update(replay(documents, Path(directory) / "replay.db"))
    except Exception as error:
        secret = os.environ.get("CTM_UT_PASSWORD")
        message = str(error)
        report["error"] = message.replace(secret, "***") if secret else message
    save(args.report, report)
    print(json.dumps({k: report[k] for k in ("passed", "coverage", "filter_checks", "slice_count", "error") if k in report}, ensure_ascii=False))
    print(f"Report: {args.report}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
