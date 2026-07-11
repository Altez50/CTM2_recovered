from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query

from api.auth_dependencies import get_current_user, get_db
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.services import create_reference, get_reference, list_references, soft_delete_reference, update_reference


router = APIRouter(prefix="/api/references", tags=["references"])


@router.get("/{kind}", response_model=ApiResponse)
def list_reference_items(
    kind: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query(default="asc"),
    review_status: str | None = None,
) -> ApiResponse:
    items, pagination = list_references(
        connection,
        kind=kind,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        review_status=review_status,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.get("/{kind}/{item_id}", response_model=ApiResponse)
def get_reference_item(
    kind: str,
    item_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_reference(connection, kind=kind, item_id=item_id))


@router.post("/{kind}", response_model=ApiResponse)
def create_reference_item(
    kind: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(data=create_reference(connection, kind=kind, payload=payload), message="Created successfully")


@router.put("/{kind}/{item_id}", response_model=ApiResponse)
def update_reference_item(
    kind: str,
    item_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(
        data=update_reference(connection, kind=kind, item_id=item_id, payload=payload),
        message="Updated successfully",
    )


@router.delete("/{kind}/{item_id}", response_model=ApiMessage)
def delete_reference_item(
    kind: str,
    item_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    soft_delete_reference(connection, kind=kind, item_id=item_id)
    return ApiMessage(message="Marked for deletion")
