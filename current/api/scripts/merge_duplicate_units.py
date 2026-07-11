from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import get_connection, transactional_connection
from api.unit_cleanup import find_duplicate_unit_group, merge_unit_ids
from api.work_services import _normalize_unit_name


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge duplicate units into a single target unit.")
    parser.add_argument(
        "--normalized-name",
        help="Normalized unit name group to merge, for example 'м²'.",
    )
    parser.add_argument("--target-unit-id", type=int, help="Unit ID to keep.")
    parser.add_argument(
        "--source-unit-id",
        type=int,
        action="append",
        default=[],
        help="Unit ID to merge into the target. Repeat for multiple IDs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag the script runs in dry-run mode.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if not args.normalized_name and (args.target_unit_id is None or not args.source_unit_id):
        raise SystemExit(
            "Provide either --normalized-name, or both --target-unit-id and at least one --source-unit-id."
        )

    canonical_name = _normalize_unit_name(args.normalized_name or "")
    if args.normalized_name:
        connection = get_connection()
        try:
            group = find_duplicate_unit_group(connection, args.normalized_name)
        finally:
            connection.close()
        if group is None:
            raise SystemExit(f"Duplicate group not found for normalized name: {args.normalized_name}")
        target_unit_id = args.target_unit_id or int(group["recommended_target"]["id"])
        source_unit_ids = args.source_unit_id or [int(unit_id) for unit_id in group["source_unit_ids"]]
        canonical_name = str(group["normalized_name"])
    else:
        target_unit_id = int(args.target_unit_id)
        source_unit_ids = [int(unit_id) for unit_id in args.source_unit_id]

    context = transactional_connection() if args.apply else None
    if context is None:
        connection = get_connection()
        try:
            result = merge_unit_ids(
                connection,
                target_unit_id,
                source_unit_ids,
                dry_run=True,
                canonical_name=canonical_name or None,
            )
        finally:
            connection.close()
    else:
        with context as connection:
            result = merge_unit_ids(
                connection,
                target_unit_id,
                source_unit_ids,
                dry_run=False,
                canonical_name=canonical_name or None,
            )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: normalized group {result['normalized_name']}")
    print(
        f"Target unit: ID {result['target_unit']['id']} ({result['target_unit']['name']})"
    )
    print(f"Source units: {', '.join(str(unit_id) for unit_id in result['source_unit_ids']) or 'none'}")
    print(
        f"Updates: materials={result['materials_updated']}, "
        f"work_specifications={result['work_specifications_updated']}"
    )
    rename = result["target_rename"]
    if rename["will_rename"]:
        suffix = "applied" if args.apply else "planned"
        print(f"Target rename {suffix}: {rename['from']} -> {rename['to']}")
    elif rename["blocked_by_existing_name"]:
        print(f"Target rename blocked: another unit already uses '{rename['to']}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
