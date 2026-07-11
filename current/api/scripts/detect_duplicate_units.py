from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import get_connection
from api.unit_cleanup import find_duplicate_unit_groups


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect duplicate units by normalized name.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    connection = get_connection()
    try:
        groups = find_duplicate_unit_groups(connection)
    finally:
        connection.close()

    if args.json:
        print(json.dumps(groups, ensure_ascii=False, indent=2))
        return 0

    if not groups:
        print("Duplicate unit groups not found.")
        return 0

    print(f"Found {len(groups)} duplicate unit group(s):")
    for group in groups:
        recommended = group["recommended_target"]
        print()
        print(
            f"- {group['normalized_name']}: {group['unit_count']} units, "
            f"{group['reference_count']} catalog references, "
            f"{group['legacy_work_reference_count']} legacy works"
        )
        print(
            f"  Recommended target: ID {recommended['id']} ({recommended['name']})"
        )
        for unit in group["units"]:
            print(
                f"  - ID {unit['id']}: {unit['name']} "
                f"[materials={unit['materials_count']}, specs={unit['work_specifications_count']}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
