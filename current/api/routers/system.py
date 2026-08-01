from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from api.auth_dependencies import get_current_user, get_db
from api.database import SYNC_SCHEMA_VERSION
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.services import dashboard_summary


router = APIRouter(tags=["system"])


@lru_cache(maxsize=1)
def _build_version() -> str:
    """Best-effort build identifier for the running backend.

    Resolution order:
      1. APP_BUILD_VERSION env var (set explicitly, e.g. in docker-compose).
      2. api/BUILD_VERSION file (written by the deploy script next to the package).
      3. `git describe` of the project root (local dev only).
      4. "unknown".
    """
    env_val = os.getenv("APP_BUILD_VERSION", "").strip()
    if env_val:
        return env_val
    pkg_root = Path(__file__).resolve().parent.parent  # .../current/api
    for candidate in (pkg_root / "BUILD_VERSION", pkg_root.parent / "BUILD_VERSION"):
        try:
            if candidate.exists():
                val = candidate.read_text(encoding="utf-8").strip()
                if val:
                    return val
        except OSError:
            continue
    try:
        out = subprocess.run(
            ["git", "-C", str(pkg_root.parent), "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


@router.get("/api/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return ApiResponse(data={
        "status": "ok",
        "build": _build_version(),
        "schema": SYNC_SCHEMA_VERSION,
    })


@router.get("/api/dashboard/summary", response_model=ApiResponse)
def dashboard(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=dashboard_summary(connection, current_user))


# ── Пользовательские настройки форм (состав колонок, сортировка) ───────────
#
# См. DOCUMENT_LIST_SPEC.md раздел 4.3. Хранилище — таблица user_settings
# (user_id, form_name, setting_key, setting_value). Значения — строковый JSON.

_MAX_SETTING_VALUE_LEN = 64 * 1024  # 64 КБ на одно значение


@router.get("/api/system/user-settings/{form_name}", response_model=ApiResponse)
def get_user_settings(
    form_name: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    rows = connection.execute(
        """SELECT setting_key, setting_value FROM user_settings
           WHERE user_id = ? AND form_name = ?""",
        (current_user.id, form_name),
    ).fetchall()
    data = {row["setting_key"]: row["setting_value"] for row in rows}
    return ApiResponse(data=data)


@router.put("/api/system/user-settings/{form_name}", response_model=ApiResponse)
def put_user_settings(
    form_name: str,
    payload: Annotated[dict, Body(...)],
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    upserted: dict[str, str] = {}
    for key, value in payload.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if len(text) > _MAX_SETTING_VALUE_LEN:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' exceeds 64 KB limit")
        connection.execute(
            """INSERT INTO user_settings (user_id, form_name, setting_key, setting_value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, form_name, setting_key)
               DO UPDATE SET setting_value = excluded.setting_value""",
            (current_user.id, form_name, key, text),
        )
        upserted[key] = text
    connection.commit()
    return ApiResponse(data=upserted, message="Settings saved")


@router.delete("/api/system/user-settings/{form_name}/{setting_key}", response_model=ApiResponse)
def delete_user_setting(
    form_name: str,
    setting_key: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    connection.execute(
        """DELETE FROM user_settings
           WHERE user_id = ? AND form_name = ? AND setting_key = ?""",
        (current_user.id, form_name, setting_key),
    )
    connection.commit()
    return ApiResponse(message=f"Setting '{setting_key}' reset to default")
