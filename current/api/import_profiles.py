"""Server-side storage of Excel import profiles.

Profiles are persisted as JSON in the ``constants`` table under the key
``goods.import_profiles``, so they are shared across all sync nodes (the
desktop client remains the primary editor). Mirrors the desktop
:class:`src.services.excel_import_profile.ExcelImportProfileStore` shape so a
profile saved on one node can be reused on another.

The API intentionally stores arbitrary profile dicts (no strict schema) — the
desktop owns the canonical :class:`ExcelImportProfile` definition.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


_CONSTANTS_KEY = "goods.import_profiles"


def _load_all(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    row = connection.execute("SELECT value FROM constants WHERE key = ?", (_CONSTANTS_KEY,)).fetchone()
    if row is None or not row["value"]:
        return []
    try:
        data = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, dict) and isinstance(data.get("profiles"), list):
        return data["profiles"]
    if isinstance(data, list):
        return data
    return []


def _save_all(connection: sqlite3.Connection, profiles: list[dict[str, Any]]) -> None:
    payload = json.dumps(profiles, ensure_ascii=False)
    connection.execute(
        """
        INSERT INTO constants (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_CONSTANTS_KEY, payload),
    )


def list_profiles(connection: sqlite3.Connection, *, target: str | None = None) -> list[dict[str, Any]]:
    profiles = _load_all(connection)
    if target:
        profiles = [p for p in profiles if p.get("target") == target]
    return profiles


def save_profile(connection: sqlite3.Connection, profile: dict[str, Any]) -> dict[str, Any]:
    name = str(profile.get("name") or "").strip()
    if not name:
        raise ValueError("Имя профиля обязательно")
    target = str(profile.get("target") or "goods_receipt")
    profiles = _load_all(connection)
    profiles = [p for p in profiles if not (p.get("name") == name and p.get("target") == target)]
    record = {**profile, "name": name, "target": target}
    profiles.append(record)
    _save_all(connection, profiles)
    connection.commit()
    return record


def delete_profile(connection: sqlite3.Connection, *, target: str, name: str) -> bool:
    profiles = _load_all(connection)
    remaining = [p for p in profiles if not (p.get("name") == name and p.get("target") == target)]
    if len(remaining) == len(profiles):
        return False
    _save_all(connection, remaining)
    connection.commit()
    return True
