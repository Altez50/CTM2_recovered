from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response

from api.auth_dependencies import get_current_user, get_db
from api.list_query import parse_quick_filters
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.text_import_export import export_document, import_document_lines
from api.models.documents import (
    DailyReportCreate,
    DailyReportUpdate,
    EstimateCreate,
    EstimateUpdate,
    TimesheetAutofillRequest,
    TimesheetCreate,
    TimesheetUpdate,
)
from api.services import (
    build_daily_report_print,
    build_daily_report_act_print,
    build_act_print,
    build_estimate_print,
    build_timesheet_print,
    copy_daily_report,
    copy_estimate,
    copy_timesheet,
    delete_daily_report,
    delete_estimate,
    delete_timesheet,
    export_timesheet_data,
    autofill_timesheet_lines,
    get_daily_report,
    get_estimate,
    get_timesheet,
    list_daily_reports,
    list_estimates,
    list_timesheets,
    post_daily_report,
    post_estimate,
    post_timesheet,
    preview_timesheet_import,
    restore_daily_report,
    restore_estimate,
    save_daily_report,
    save_estimate,
    save_timesheet,
    unpost_daily_report,
    unpost_estimate,
    unpost_timesheet,
)


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/estimates", response_model=ApiResponse)
def list_estimate_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    object_id: int | None = None,
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_estimates(
        connection,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        object_id=object_id,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/estimates", response_model=ApiResponse, status_code=201)
def create_estimate_document(
    payload: EstimateCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=save_estimate(connection, payload=payload.model_dump()), message="Estimate created")


@router.get("/estimates/{estimate_id}", response_model=ApiResponse)
def get_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_estimate(connection, estimate_id))


@router.put("/estimates/{estimate_id}", response_model=ApiResponse)
def update_estimate_document(
    estimate_id: int,
    payload: EstimateUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_estimate(connection, payload=payload.model_dump(), estimate_id=estimate_id),
        message="Estimate updated",
    )


@router.delete("/estimates/{estimate_id}", response_model=ApiMessage)
def delete_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_estimate(connection, estimate_id)
    return ApiMessage(message="Estimate marked for deletion")


@router.post("/estimates/{estimate_id}/restore", response_model=ApiMessage)
def restore_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    restore_estimate(connection, estimate_id)
    return ApiMessage(message="Estimate restored")


@router.post("/estimates/{estimate_id}/post", response_model=ApiMessage)
def post_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    post_estimate(connection, estimate_id=estimate_id, user=current_user)
    return ApiMessage(message="Estimate posted successfully")


@router.post("/estimates/{estimate_id}/unpost", response_model=ApiMessage)
def unpost_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    unpost_estimate(connection, estimate_id=estimate_id, user=current_user)
    return ApiMessage(message="Estimate unposted successfully")


@router.get("/estimates/{estimate_id}/print")
def print_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="pdf", pattern="^(pdf|excel)$"),
) -> Response:
    estimate = get_estimate(connection, estimate_id)
    content, media_type, filename = build_estimate_print(connection, estimate, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/estimates/{estimate_id}/print-act")
def print_act_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="pdf", pattern="^(pdf|excel)$"),
) -> Response:
    estimate = get_estimate(connection, estimate_id)
    content, media_type, filename = build_act_print(connection, estimate, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily-reports", response_model=ApiResponse)
def list_daily_report_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_daily_reports(
        connection,
        user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/daily-reports", response_model=ApiResponse, status_code=201)
def create_daily_report_document(
    payload: DailyReportCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_daily_report(connection, payload=payload.model_dump(), user=current_user),
        message="Daily report created",
    )


@router.get("/daily-reports/{report_id}", response_model=ApiResponse)
def get_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_daily_report(connection, report_id, current_user))


@router.put("/daily-reports/{report_id}", response_model=ApiResponse)
def update_daily_report_document(
    report_id: int,
    payload: DailyReportUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_daily_report(connection, payload=payload.model_dump(), user=current_user, report_id=report_id),
        message="Daily report updated",
    )


@router.delete("/daily-reports/{report_id}", response_model=ApiMessage)
def delete_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_daily_report(connection, report_id, current_user)
    return ApiMessage(message="Daily report marked for deletion")


@router.post("/daily-reports/{report_id}/restore", response_model=ApiMessage)
def restore_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    restore_daily_report(connection, report_id, current_user)
    return ApiMessage(message="Daily report restored")


@router.post("/daily-reports/{report_id}/post", response_model=ApiMessage)
def post_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    post_daily_report(connection, report_id=report_id, user=current_user)
    return ApiMessage(message="Daily report posted successfully")


@router.post("/daily-reports/{report_id}/unpost", response_model=ApiMessage)
def unpost_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    unpost_daily_report(connection, report_id=report_id, user=current_user)
    return ApiMessage(message="Daily report unposted successfully")


@router.get("/daily-reports/{report_id}/print")
def print_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="pdf", pattern="^(pdf|excel)$"),
) -> Response:
    report = get_daily_report(connection, report_id, current_user)
    content, media_type, filename = build_daily_report_print(report, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily-reports/{report_id}/print-act")
def print_daily_report_act_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="pdf", pattern="^(pdf|excel)$"),
) -> Response:
    report = get_daily_report(connection, report_id, current_user)
    content, media_type, filename = build_daily_report_act_print(connection, report, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/timesheets", response_model=ApiResponse)
def list_timesheet_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    object_id: int | None = None,
    estimate_id: int | None = None,
    month_year: str | None = None,
    is_posted: bool | None = None,
    request: Request = None,
) -> ApiResponse:
    filters = parse_quick_filters(request.query_params if request else None)
    items, pagination = list_timesheets(
        connection,
        user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        object_id=object_id,
        estimate_id=estimate_id,
        month_year=month_year,
        is_posted=is_posted,
        filters=filters,
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/timesheets", response_model=ApiResponse, status_code=201)
def create_timesheet_document(
    payload: TimesheetCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    timesheet = save_timesheet(connection, payload=payload.model_dump(), user=current_user)
    message = "Timesheet created"
    if not timesheet.get("estimate_id"):
        message += ". Estimate is not selected; posting is still allowed."
    return ApiResponse(data=timesheet, message=message)


@router.get("/timesheets/{timesheet_id}", response_model=ApiResponse)
def get_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_timesheet(connection, timesheet_id, current_user))


@router.put("/timesheets/{timesheet_id}", response_model=ApiResponse)
def update_timesheet_document(
    timesheet_id: int,
    payload: TimesheetUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    timesheet = save_timesheet(connection, payload=payload.model_dump(), user=current_user, timesheet_id=timesheet_id)
    message = "Timesheet updated"
    if not timesheet.get("estimate_id"):
        message += ". Estimate is not selected; posting is still allowed."
    return ApiResponse(data=timesheet, message=message)


@router.delete("/timesheets/{timesheet_id}", response_model=ApiMessage)
def delete_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_timesheet(connection, timesheet_id, current_user)
    return ApiMessage(message="Timesheet marked for deletion")


@router.post("/timesheets/{timesheet_id}/post", response_model=ApiMessage)
def post_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    post_timesheet(connection, timesheet_id=timesheet_id, user=current_user)
    return ApiMessage(message="Timesheet posted successfully")


@router.post("/timesheets/{timesheet_id}/unpost", response_model=ApiMessage)
def unpost_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    unpost_timesheet(connection, timesheet_id=timesheet_id, user=current_user)
    return ApiMessage(message="Timesheet unposted successfully")


@router.get("/timesheets/{timesheet_id}/print")
def print_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="pdf", pattern="^(pdf|excel)$"),
) -> Response:
    timesheet = get_timesheet(connection, timesheet_id, current_user)
    content, media_type, filename = build_timesheet_print(timesheet, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/timesheets/{timesheet_id}/export")
def export_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query(default="json", pattern="^(json|excel)$"),
) -> Response:
    timesheet = get_timesheet(connection, timesheet_id, current_user)
    content, media_type, filename = export_timesheet_data(timesheet, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/timesheets/{timesheet_id}/copy", response_model=ApiResponse, status_code=201)
def copy_timesheet_document(
    timesheet_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=copy_timesheet(connection, timesheet_id=timesheet_id, user=current_user),
        message="Timesheet copied",
    )


@router.post("/estimates/{estimate_id}/copy", response_model=ApiResponse, status_code=201)
def copy_estimate_document(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=copy_estimate(connection, estimate_id=estimate_id),
        message="Estimate copied",
    )


# ── Estimate text import / export (TSV / JSON / XLSX) ──────────────────────


@router.post("/estimates/{estimate_id}/import-text", response_model=ApiResponse)
async def import_estimate_text(
    estimate_id: int,
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query("tsv", description="tsv | json | xlsx"),
    replace: bool = Query(True, description="Replace existing lines"),
) -> ApiResponse:
    """Import tabular lines for an estimate from TSV / JSON / XLSX.

    Missing works and units are created automatically. Group rows
    (is_group=1) are imported as-is.
    """
    raw = await request.body()
    if format == "xlsx":
        data: bytes | str = raw
    elif isinstance(raw, (bytes, bytearray)):
        data = bytes(raw).decode("utf-8", errors="replace")
    else:
        data = raw or ""

    result = import_document_lines(
        connection, "estimate", estimate_id, fmt=format, data=data, replace=replace
    )
    return ApiResponse(
        data=result, message=f"Imported {result.get('imported', 0)} lines"
    )


@router.get("/estimates/{estimate_id}/export-text")
def export_estimate_text(
    estimate_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    format: str = Query("tsv", description="tsv | json | xlsx"),
) -> Response:
    """Export an estimate's tabular lines to TSV / JSON / XLSX."""
    result = export_document(connection, "estimate", estimate_id, fmt=format)
    body = result["body"]
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body
    return Response(
        content=body_bytes,
        media_type=result["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"'
        },
    )


@router.post("/daily-reports/{report_id}/copy", response_model=ApiResponse, status_code=201)
def copy_daily_report_document(
    report_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=copy_daily_report(connection, report_id=report_id, user=current_user),
        message="Daily report copied",
    )


@router.post("/timesheets/autofill", response_model=ApiResponse)
def autofill_timesheet_document(
    payload: TimesheetAutofillRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=autofill_timesheet_lines(
            connection,
            object_id=payload.object_id,
            estimate_id=payload.estimate_id,
            month_year=payload.month_year,
        ),
        message="Timesheet lines generated from daily reports",
    )


@router.post("/timesheets/import-preview", response_model=ApiResponse)
async def preview_timesheet_import_document(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    file: UploadFile = File(...),
) -> ApiResponse:
    content = await file.read()
    return ApiResponse(
        data=preview_timesheet_import(
            connection,
            filename=file.filename or "timesheet-import.xlsx",
            content=content,
        )
    )
