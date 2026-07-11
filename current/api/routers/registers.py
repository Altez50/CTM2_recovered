from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.auth_dependencies import get_current_user, get_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.services import query_work_execution


router = APIRouter(prefix="/api/registers", tags=["registers"])


@router.get("/work-execution", response_model=ApiResponse)
def query_work_execution_register(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    period_from: str | None = None,
    period_to: str | None = None,
    object_id: int | None = None,
    estimate_id: int | None = None,
    work_id: int | None = None,
    customer_id: int | None = None,
    contract_id: int | None = None,
    group_by: list[str] = Query(default=[]),
) -> ApiResponse:
    items, pagination, totals = query_work_execution(
        connection,
        page=page,
        page_size=page_size,
        period_from=period_from,
        period_to=period_to,
        object_id=object_id,
        estimate_id=estimate_id,
        work_id=work_id,
        customer_id=customer_id,
        contract_id=contract_id,
        group_by=group_by or None,
    )
    return ApiResponse(data={"items": items, "totals": totals}, pagination=pagination)
