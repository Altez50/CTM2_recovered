from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.auth_dependencies import get_current_user, get_db
from api.models.auth import UserInfo
from api.models.common import ApiResponse
from api.goods_services import settlements_balance, settlements_ledger, settlements_overdue, settlements_turnover


router = APIRouter(prefix="/api/settlements", tags=["settlements"])


@router.get("/balance", response_model=ApiResponse)
def get_balance(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    object_id: int | None = None,
    date: str | None = None,
) -> ApiResponse:
    return ApiResponse(
        data=settlements_balance(
            connection,
            organization_id=organization_id,
            counterparty_id=counterparty_id,
            contract_id=contract_id,
            object_id=object_id,
            on_date=date,
        )
    )


@router.get("/ledger", response_model=ApiResponse)
def get_ledger(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    organization_id: int = Query(...),
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> ApiResponse:
    return ApiResponse(
        data=settlements_ledger(
            connection,
            organization_id=organization_id,
            counterparty_id=counterparty_id,
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/overdue", response_model=ApiResponse)
def get_overdue(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    date: str | None = None,
) -> ApiResponse:
    return ApiResponse(data=settlements_overdue(connection, on_date=date))


@router.get("/turnover", response_model=ApiResponse)
def get_turnover(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    date_from: str = Query(...),
    date_to: str = Query(...),
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
) -> ApiResponse:
    return ApiResponse(
        data=settlements_turnover(
            connection,
            date_from=date_from,
            date_to=date_to,
            organization_id=organization_id,
            counterparty_id=counterparty_id,
            contract_id=contract_id,
        )
    )
