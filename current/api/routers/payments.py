from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from api.auth_dependencies import get_current_user, get_db, require_roles
from api.list_query import parse_quick_filters
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.models.payments import (
    PaymentScheduleCreate,
    PaymentScheduleUpdate,
    PaymentTransactionCreate,
    SuggestGoodsRequest,
    SuggestIncomingRequest,
    SuggestPayrollRequest,
)
from api.payment_services import (
    delete_payment_schedule,
    delete_payment_transaction,
    get_payment_schedule,
    get_payment_transaction,
    get_payment_transaction_movements,
    list_payment_schedules,
    list_payment_transactions,
    post_payment_schedule,
    post_payment_transaction,
    query_cashflow_by_day,
    query_payment_register,
    save_payment_schedule,
    save_payment_transaction,
    suggest_incoming_from_goods_issues,
    suggest_incoming_from_work_execution,
    suggest_outgoing_from_goods_receipts,
    suggest_outgoing_from_payroll,
    unpost_payment_schedule,
    unpost_payment_transaction,
)


router = APIRouter(prefix="/api/payments", tags=["payments"])


# ---------------------------------------------------------------------------
# Payment schedules
# ---------------------------------------------------------------------------


@router.get("/schedules", response_model=ApiResponse)
def list_schedules(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    object_id: int | None = None,
    contract_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_payment_schedules(
        connection,
        page=page,
        page_size=page_size,
        search=search,
        object_id=object_id,
        contract_id=contract_id,
        is_posted=is_posted,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/schedules", response_model=ApiResponse, status_code=201)
def create_schedule(
    payload: PaymentScheduleCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_payment_schedule(connection, payload=payload.model_dump(), user=current_user),
        message="Payment schedule created",
    )


@router.get("/schedules/{schedule_id}", response_model=ApiResponse)
def get_schedule(
    schedule_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_payment_schedule(connection, schedule_id))


@router.put("/schedules/{schedule_id}", response_model=ApiResponse)
def update_schedule(
    schedule_id: int,
    payload: PaymentScheduleUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_payment_schedule(connection, payload=payload.model_dump(), schedule_id=schedule_id, user=current_user),
        message="Payment schedule updated",
    )


@router.delete("/schedules/{schedule_id}", response_model=ApiMessage)
def remove_schedule(
    schedule_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiMessage:
    delete_payment_schedule(connection, schedule_id, current_user)
    return ApiMessage(message="Payment schedule marked for deletion")


@router.post("/schedules/{schedule_id}/post", response_model=ApiMessage)
def post_schedule(
    schedule_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    post_payment_schedule(connection, schedule_id=schedule_id, user=current_user)
    return ApiMessage(message="Payment schedule posted successfully")


@router.post("/schedules/{schedule_id}/unpost", response_model=ApiMessage)
def unpost_schedule(
    schedule_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    unpost_payment_schedule(connection, schedule_id=schedule_id, user=current_user)
    return ApiMessage(message="Payment schedule unposted successfully")


# ---------------------------------------------------------------------------
# Auto-suggest previews
# ---------------------------------------------------------------------------


@router.post("/schedules/preview/incoming", response_model=ApiResponse)
def preview_incoming(
    payload: SuggestIncomingRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    items = suggest_incoming_from_work_execution(
        connection,
        date_from=str(payload.date_from),
        date_to=str(payload.date_to),
        object_id=payload.object_id,
        contract_id=payload.contract_id,
    )
    return ApiResponse(data=items, message=f"{len(items)} incoming suggestion(s)")


@router.post("/schedules/preview/payroll", response_model=ApiResponse)
def preview_payroll(
    payload: SuggestPayrollRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    items = suggest_outgoing_from_payroll(
        connection,
        date_from=str(payload.date_from),
        date_to=str(payload.date_to),
        object_id=payload.object_id,
        estimate_id=payload.estimate_id,
    )
    return ApiResponse(data=items, message=f"{len(items)} payroll suggestion(s)")


@router.post("/schedules/preview/goods-receipts", response_model=ApiResponse)
def preview_goods_receipts(
    payload: SuggestGoodsRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    items = suggest_outgoing_from_goods_receipts(
        connection,
        date_from=str(payload.date_from),
        date_to=str(payload.date_to),
        organization_id=payload.organization_id,
        object_id=payload.object_id,
    )
    return ApiResponse(data=items, message=f"{len(items)} supplier payment suggestion(s)")


@router.post("/schedules/preview/goods-issues", response_model=ApiResponse)
def preview_goods_issues(
    payload: SuggestGoodsRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    items = suggest_incoming_from_goods_issues(
        connection,
        date_from=str(payload.date_from),
        date_to=str(payload.date_to),
        organization_id=payload.organization_id,
        object_id=payload.object_id,
    )
    return ApiResponse(data=items, message=f"{len(items)} customer receipt suggestion(s)")


# ---------------------------------------------------------------------------
# Payment transactions
# ---------------------------------------------------------------------------


@router.get("/transactions", response_model=ApiResponse)
def list_transactions(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    direction: str | None = None,
    counterparty_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_payment_transactions(
        connection,
        page=page,
        page_size=page_size,
        search=search,
        direction=direction,
        counterparty_id=counterparty_id,
        is_posted=is_posted,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/transactions", response_model=ApiResponse, status_code=201)
def create_transaction(
    payload: PaymentTransactionCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_payment_transaction(connection, payload=payload.model_dump(), user=current_user),
        message="Payment transaction created",
    )


@router.get("/transactions/{tx_id}", response_model=ApiResponse)
def get_transaction(
    tx_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_payment_transaction(connection, tx_id))


@router.put("/transactions/{tx_id}", response_model=ApiResponse)
def update_transaction(
    tx_id: int,
    payload: PaymentTransactionCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_payment_transaction(connection, payload=payload.model_dump(), tx_id=tx_id, user=current_user),
        message="Payment transaction updated",
    )


@router.delete("/transactions/{tx_id}", response_model=ApiMessage)
def remove_transaction(
    tx_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiMessage:
    delete_payment_transaction(connection, tx_id, current_user)
    return ApiMessage(message="Payment transaction marked for deletion")


@router.post("/transactions/{tx_id}/post", response_model=ApiMessage)
def post_transaction(
    tx_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    post_payment_transaction(connection, tx_id=tx_id, user=current_user)
    return ApiMessage(message="Payment transaction posted successfully")


@router.post("/transactions/{tx_id}/unpost", response_model=ApiMessage)
def unpost_transaction(
    tx_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    unpost_payment_transaction(connection, tx_id=tx_id, user=current_user)
    return ApiMessage(message="Payment transaction unposted successfully")


# ---------------------------------------------------------------------------
# Register query + cashflow
# ---------------------------------------------------------------------------


@router.get("/register", response_model=ApiResponse)
def query_register(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    period_from: str | None = None,
    period_to: str | None = None,
    object_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    direction: str | None = None,
    category: str | None = None,
    group_by: list[str] = Query(default=[]),
) -> ApiResponse:
    items, pagination, totals = query_payment_register(
        connection,
        page=page,
        page_size=page_size,
        period_from=period_from,
        period_to=period_to,
        object_id=object_id,
        counterparty_id=counterparty_id,
        contract_id=contract_id,
        direction=direction,
        category=category,
        group_by=group_by or None,
    )
    return ApiResponse(data={"items": items, "totals": totals}, pagination=pagination)


@router.get("/cashflow", response_model=ApiResponse)
def query_cashflow(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    date_from: str = Query(...),
    date_to: str = Query(...),
    object_id: int | None = None,
    counterparty_id: int | None = None,
) -> ApiResponse:
    items = query_cashflow_by_day(
        connection,
        date_from=date_from,
        date_to=date_to,
        object_id=object_id,
        counterparty_id=counterparty_id,
    )
    return ApiResponse(data=items)


@router.get("/transactions/{tx_id}/movements", response_model=ApiResponse)
def transaction_movements(
    tx_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    """Mutual-settlement register rows produced by one payment transaction."""
    return ApiResponse(data=get_payment_transaction_movements(connection, tx_id=tx_id))
