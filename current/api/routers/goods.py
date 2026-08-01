from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Query, Request, Response, UploadFile

from api.auth_dependencies import get_current_user, get_db, require_roles
from api.list_query import parse_quick_filters
from api.import_profiles import delete_profile, list_profiles, save_profile
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.models.goods import (
    GoodsIssueCreate,
    GoodsReceiptCreate,
)
from api.goods_services import (
    copy_goods_issue,
    copy_goods_receipt,
    delete_goods_issue,
    delete_goods_receipt,
    export_goods_document_lines,
    get_document_movements,
    get_goods_issue,
    get_goods_receipt,
    inventory_balances,
    inventory_movements,
    list_goods_issues,
    list_goods_receipts,
    post_goods_issue,
    post_goods_receipt,
    preview_goods_lines_import,
    save_goods_issue,
    save_goods_receipt,
    unpost_goods_issue,
    unpost_goods_receipt,
)


router = APIRouter(prefix="/api/goods", tags=["goods"])


# ---------------------------------------------------------------------------
# Goods receipts
# ---------------------------------------------------------------------------


@router.get("/receipts", response_model=ApiResponse)
def list_receipts(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    object_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_goods_receipts(
        connection,
        page=page,
        page_size=page_size,
        search=search,
        organization_id=organization_id,
        counterparty_id=counterparty_id,
        contract_id=contract_id,
        object_id=object_id,
        is_posted=is_posted,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/receipts", response_model=ApiResponse, status_code=201)
def create_receipt(
    payload: GoodsReceiptCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_goods_receipt(connection, payload=payload.model_dump(), user=current_user),
        message="Goods receipt created",
    )


@router.get("/receipts/{receipt_id}", response_model=ApiResponse)
def get_receipt(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_goods_receipt(connection, receipt_id))


@router.put("/receipts/{receipt_id}", response_model=ApiResponse)
def update_receipt(
    receipt_id: int,
    payload: GoodsReceiptCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_goods_receipt(connection, payload=payload.model_dump(), document_id=receipt_id, user=current_user),
        message="Goods receipt updated",
    )


@router.delete("/receipts/{receipt_id}", response_model=ApiMessage)
def remove_receipt(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiMessage:
    delete_goods_receipt(connection, receipt_id, current_user)
    return ApiMessage(message="Goods receipt marked for deletion")


@router.post("/receipts/{receipt_id}/post", response_model=ApiMessage)
def post_receipt(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
    auto_schedule: bool = Query(default=True),
) -> ApiMessage:
    post_goods_receipt(connection, document_id=receipt_id, user=current_user, auto_schedule=auto_schedule)
    return ApiMessage(message="Goods receipt posted successfully")


@router.post("/receipts/{receipt_id}/unpost", response_model=ApiMessage)
def unpost_receipt(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    unpost_goods_receipt(connection, document_id=receipt_id, user=current_user)
    return ApiMessage(message="Goods receipt unposted successfully")


@router.post("/receipts/{receipt_id}/copy", response_model=ApiResponse, status_code=201)
def copy_receipt(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=copy_goods_receipt(connection, document_id=receipt_id, user=current_user),
        message="Goods receipt copied",
    )


# ---------------------------------------------------------------------------
# Goods issues
# ---------------------------------------------------------------------------


@router.get("/issues", response_model=ApiResponse)
def list_issues(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    organization_id: int | None = None,
    counterparty_id: int | None = None,
    contract_id: int | None = None,
    object_id: int | None = None,
    is_posted: bool | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_goods_issues(
        connection,
        page=page,
        page_size=page_size,
        search=search,
        organization_id=organization_id,
        counterparty_id=counterparty_id,
        contract_id=contract_id,
        object_id=object_id,
        is_posted=is_posted,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/issues", response_model=ApiResponse, status_code=201)
def create_issue(
    payload: GoodsIssueCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_goods_issue(connection, payload=payload.model_dump(), user=current_user),
        message="Goods issue created",
    )


@router.get("/issues/{issue_id}", response_model=ApiResponse)
def get_issue(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_goods_issue(connection, issue_id))


@router.put("/issues/{issue_id}", response_model=ApiResponse)
def update_issue(
    issue_id: int,
    payload: GoodsIssueCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=save_goods_issue(connection, payload=payload.model_dump(), document_id=issue_id, user=current_user),
        message="Goods issue updated",
    )


@router.delete("/issues/{issue_id}", response_model=ApiMessage)
def remove_issue(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiMessage:
    delete_goods_issue(connection, issue_id, current_user)
    return ApiMessage(message="Goods issue marked for deletion")


@router.post("/issues/{issue_id}/post", response_model=ApiMessage)
def post_issue(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
    auto_schedule: bool = Query(default=True),
) -> ApiMessage:
    post_goods_issue(connection, document_id=issue_id, user=current_user, auto_schedule=auto_schedule)
    return ApiMessage(message="Goods issue posted successfully")


@router.post("/issues/{issue_id}/unpost", response_model=ApiMessage)
def unpost_issue(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("admin"))],
) -> ApiMessage:
    unpost_goods_issue(connection, document_id=issue_id, user=current_user)
    return ApiMessage(message="Goods issue unposted successfully")


@router.post("/issues/{issue_id}/copy", response_model=ApiResponse, status_code=201)
def copy_issue(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
) -> ApiResponse:
    return ApiResponse(
        data=copy_goods_issue(connection, document_id=issue_id, user=current_user),
        message="Goods issue copied",
    )


# ---------------------------------------------------------------------------
# Inventory register
# ---------------------------------------------------------------------------


@router.get("/inventory/balances", response_model=ApiResponse)
def get_inventory_balances(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    date: str | None = None,
    object_id: int | None = None,
    material_id: int | None = None,
) -> ApiResponse:
    return ApiResponse(
        data=inventory_balances(
            connection,
            on_date=date,
            object_id=object_id,
            material_id=material_id,
        )
    )


@router.get("/inventory/movements", response_model=ApiResponse)
def get_inventory_movements(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    date_from: str = Query(...),
    date_to: str = Query(...),
    object_id: int | None = None,
    material_id: int | None = None,
) -> ApiResponse:
    return ApiResponse(
        data=inventory_movements(
            connection,
            date_from=date_from,
            date_to=date_to,
            object_id=object_id,
            material_id=material_id,
        )
    )


# ---------------------------------------------------------------------------
# Document register movements viewer
# ---------------------------------------------------------------------------


@router.get("/{kind}/{document_id}/movements", response_model=ApiResponse)
def get_document_movements_endpoint(
    kind: str,
    document_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    """Register movements (inventory + settlements) produced by one document."""
    return ApiResponse(data=get_document_movements(connection, kind=kind, document_id=document_id))


# ---------------------------------------------------------------------------
# Excel export / import of document lines
# ---------------------------------------------------------------------------


@router.get("/receipts/{receipt_id}/lines/export", response_model=None)
def export_receipt_lines(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> Response:
    content = export_goods_document_lines(connection, kind="receipt", document_id=receipt_id)
    return Response(
        content=content,
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="goods_receipt_{receipt_id}_lines.xls"'},
    )


@router.get("/issues/{issue_id}/lines/export", response_model=None)
def export_issue_lines(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> Response:
    content = export_goods_document_lines(connection, kind="issue", document_id=issue_id)
    return Response(
        content=content,
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="goods_issue_{issue_id}_lines.xls"'},
    )


@router.post("/receipts/{receipt_id}/lines/import", response_model=ApiResponse)
async def import_receipt_lines(
    receipt_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    preview = preview_goods_lines_import(
        connection, kind="receipt", filename=file.filename or "import.xlsx", content=content
    )
    return ApiResponse(data=preview, message=f"{len(preview['rows'])} row(s) parsed")


@router.post("/issues/{issue_id}/lines/import", response_model=ApiResponse)
async def import_issue_lines(
    issue_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    preview = preview_goods_lines_import(
        connection, kind="issue", filename=file.filename or "import.xlsx", content=content
    )
    return ApiResponse(data=preview, message=f"{len(preview['rows'])} row(s) parsed")


@router.post("/lines/import-preview", response_model=ApiResponse)
async def import_lines_preview(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
    kind: str = Query(..., regex="^(receipt|issue)$"),
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    preview = preview_goods_lines_import(
        connection, kind=kind, filename=file.filename or "import.xlsx", content=content
    )
    return ApiResponse(data=preview, message=f"{len(preview['rows'])} row(s) parsed")


# ---------------------------------------------------------------------------
# Import profiles (shared across sync nodes via the constants table)
# ---------------------------------------------------------------------------


@router.get("/import-profiles", response_model=ApiResponse)
def list_import_profiles(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    target: str | None = Query(default=None, regex="^(goods_receipt|goods_issue|work_specification)$"),
) -> ApiResponse:
    return ApiResponse(data=list_profiles(connection, target=target))


@router.post("/import-profiles", response_model=ApiResponse)
def save_import_profile(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    record = save_profile(connection, payload)
    return ApiResponse(data=record, message="Import profile saved")


@router.delete("/import-profiles/{name}", response_model=ApiMessage)
def delete_import_profile(
    name: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(require_roles("manager", "admin"))],
    target: str = Query(..., regex="^(goods_receipt|goods_issue|work_specification)$"),
) -> ApiMessage:
    deleted = delete_profile(connection, target=target, name=name)
    if not deleted:
        return ApiMessage(success=False, message="Profile not found")
    return ApiMessage(message="Import profile deleted")
