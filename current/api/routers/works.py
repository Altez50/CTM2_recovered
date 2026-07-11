from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Query, Response, UploadFile

from api.auth_dependencies import get_current_user, get_db
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.models.works import ImportMaterialCreateRequest
from api.work_services import (
    create_materials_from_import_preview,
    create_work,
    delete_material,
    delete_work,
    export_flagged_work_specifications,
    export_work_specifications,
    get_work_detail,
    get_work_specifications,
    import_work_specification_corrections,
    list_materials,
    list_units,
    mark_works_with_import_issues,
    preview_copy_specifications,
    preview_work_specification_import,
    update_material,
    update_work,
)


router = APIRouter(tags=["works"])


@router.get("/api/units", response_model=ApiResponse)
def list_unit_items(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    search: str | None = None,
) -> ApiResponse:
    return ApiResponse(data=list_units(connection, search=search))


@router.get("/api/materials", response_model=ApiResponse)
def list_material_items(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    search: str | None = None,
) -> ApiResponse:
    items, pagination = list_materials(connection, page=page, page_size=page_size, search=search)
    return ApiResponse(data=items, pagination=pagination)


@router.put("/api/materials/{material_id}", response_model=ApiResponse)
def update_material_item(
    material_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(
        data=update_material(
            connection,
            material_id,
            name=payload.get("name"),
            code=payload.get("code"),
            unit_id=payload.get("unit_id"),
            price=payload.get("price"),
        ),
        message="Material updated",
    )


@router.delete("/api/materials/{material_id}", response_model=ApiMessage)
def delete_material_item(
    material_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_material(connection, material_id)
    return ApiMessage(message="Material deleted")


@router.get("/api/works/{work_id}", response_model=ApiResponse)
def get_work_item(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_work_detail(connection, work_id))


@router.post("/api/works", response_model=ApiResponse)
def create_work_item(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(data=create_work(connection, payload), message="Created successfully")


@router.put("/api/works/{work_id}", response_model=ApiResponse)
def update_work_item(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(data=update_work(connection, work_id, payload), message="Updated successfully")


@router.delete("/api/works/{work_id}", response_model=ApiMessage)
def delete_work_item(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_work(connection, work_id)
    return ApiMessage(message="Marked for deletion")


@router.get("/api/works/{work_id}/specifications", response_model=ApiResponse)
def get_work_specification_items(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_work_specifications(connection, work_id))


@router.post("/api/works/{work_id}/specifications/copy-from/{source_work_id}", response_model=ApiResponse)
def preview_copy_from_work(
    work_id: int,
    source_work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data={
            "target_work_id": work_id,
            "source_work_id": source_work_id,
            "rows": preview_copy_specifications(connection, source_work_id),
        }
    )


@router.post("/api/works/{work_id}/specifications/import", response_model=ApiResponse)
async def preview_import_for_work(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    return ApiResponse(data=preview_work_specification_import(connection, file.filename or "import.xlsx", content))


@router.post("/api/works/{work_id}/specifications/import/materials", response_model=ApiResponse)
def create_import_materials_for_work(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    payload: dict[str, Any] = Body(...),
) -> ApiResponse:
    return ApiResponse(
        data=create_materials_from_import_preview(connection, ImportMaterialCreateRequest(**payload)),
        message="Materials resolved for import preview",
    )


@router.get("/api/works/{work_id}/specifications/export", response_model=None)
def export_work_specifications_endpoint(
    work_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> Response:
    content = export_work_specifications(connection, work_id)
    return Response(
        content=content,
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": f'attachment; filename="work_specification_{work_id}.xls"',
        },
    )


@router.get("/api/works/specifications/export-flagged", response_model=None)
def export_flagged_work_specifications_endpoint(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    review_status: str = Query(default="incorrect"),
) -> Response:
    content = export_flagged_work_specifications(connection, review_status=review_status)
    return Response(
        content=content,
        media_type="application/vnd.ms-excel",
        headers={
            "Content-Disposition": f'attachment; filename="work_specifications_{review_status}.xls"',
        },
    )


@router.post("/api/works/specifications/import-corrections", response_model=ApiResponse)
async def import_work_specification_corrections_endpoint(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    return ApiResponse(
        data=import_work_specification_corrections(connection, file.filename or "corrections.xlsx", content),
        message="Work specifications updated from correction file",
    )


@router.post("/api/works/specifications/mark-import-issues", response_model=ApiResponse)
def mark_import_issue_works_endpoint(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=mark_works_with_import_issues(connection),
        message="Works with import issues were marked for review",
    )
