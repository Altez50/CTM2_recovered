from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth_dependencies import get_current_user, get_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.services import dashboard_summary


router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=ApiResponse)
def health() -> ApiResponse:
    return ApiResponse(data={"status": "ok"})


@router.get("/api/dashboard/summary", response_model=ApiResponse)
def dashboard(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=dashboard_summary(connection, current_user))
