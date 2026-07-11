"""Cost accounting API router — documents, operations, reports."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.auth_dependencies import get_current_user, get_db, require_roles
from api.cost_accounting_services import (
    calculate_cost,
    cancel_overhead_distribution,
    delete_cost_calculation,
    delete_machine,
    delete_machinery_usage_report,
    delete_material_consumption,
    delete_overhead_expense,
    delete_subcontract_acceptance,
    distribute_overhead,
    get_cost_card,
    get_cost_calculation,
    get_deviations,
    get_machine,
    get_machinery_usage_report,
    get_material_consumption,
    get_overhead_expense,
    get_profitability,
    get_subcontract_acceptance,
    get_turnover_balance,
    list_allocation_bases,
    list_cost_calculations,
    list_cost_elements,
    list_machinery_usage_reports,
    list_machines,
    list_material_consumptions,
    list_overhead_expenses,
    list_subcontract_acceptances,
    post_cost_calculation,
    post_machinery_usage_report,
    post_material_consumption,
    post_subcontract_acceptance,
    save_cost_calculation,
    save_machine,
    save_machinery_usage_report,
    save_material_consumption,
    save_overhead_expense,
    save_subcontract_acceptance,
    unpost_cost_calculation,
    unpost_machinery_usage_report,
    unpost_material_consumption,
    unpost_subcontract_acceptance,
    get_audit_logs,
)
from api.models.auth import UserInfo
from api.models.common import ApiMessage, ApiResponse
from api.models.cost_accounting import (
    CostCalculationCreate,
    LimitCheckRequest,
    MachineCreate,
    MachineUpdate,
    MachineryUsageReportCreate,
    MachineryUsageReportUpdate,
    MaterialConsumptionCreate,
    MaterialConsumptionUpdate,
    OverheadDistributionRequest,
    OverheadExpenseCreate,
    OverheadExpenseUpdate,
    SubcontractAcceptanceCreate,
    SubcontractAcceptanceUpdate,
)

router = APIRouter(prefix="/api/cost", tags=["cost-accounting"])

# Role check for admin-only operations (posting, distribution, calculation)
AdminOrManager = Depends(require_roles("admin", "manager"))


# ── Reference Data ────────────────────────────────────────────────────────


@router.get("/cost-elements", response_model=ApiResponse)
def get_cost_elements(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=list_cost_elements(connection))


@router.get("/allocation-bases", response_model=ApiResponse)
def get_allocation_bases(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=list_allocation_bases(connection))


# ── Machines ──────────────────────────────────────────────────────────────


@router.get("/machines", response_model=ApiResponse)
def list_machine_items(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
) -> ApiResponse:
    items, pagination = list_machines(connection, page=page, page_size=page_size, search=search)
    return ApiResponse(data=items, pagination=pagination)


@router.post("/machines", response_model=ApiResponse, status_code=201)
def create_machine(
    payload: MachineCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=save_machine(connection, payload.model_dump()), message="Machine created")


@router.get("/machines/{machine_id}", response_model=ApiResponse)
def get_machine_item(
    machine_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_machine(connection, machine_id))


@router.put("/machines/{machine_id}", response_model=ApiResponse)
def update_machine(
    machine_id: int,
    payload: MachineUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=save_machine(connection, payload.model_dump(), machine_id=machine_id), message="Machine updated")


@router.delete("/machines/{machine_id}", response_model=ApiMessage)
def delete_machine_item(
    machine_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_machine(connection, machine_id)
    return ApiMessage(message="Machine marked for deletion")


# ── Material Consumptions ─────────────────────────────────────────────────


@router.get("/material-consumptions", response_model=ApiResponse)
def list_mc_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    object_id: int | None = None,
) -> ApiResponse:
    items, pagination = list_material_consumptions(
        connection, page=page, page_size=page_size, search=search, object_id=object_id
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/material-consumptions", response_model=ApiResponse, status_code=201)
def create_mc_document(
    payload: MaterialConsumptionCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=save_material_consumption(connection, payload.model_dump()), message="Material consumption created")


@router.get("/material-consumptions/{doc_id}", response_model=ApiResponse)
def get_mc_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_material_consumption(connection, doc_id))


@router.put("/material-consumptions/{doc_id}", response_model=ApiResponse)
def update_mc_document(
    doc_id: int,
    payload: MaterialConsumptionUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_material_consumption(connection, payload.model_dump(), doc_id=doc_id),
        message="Material consumption updated",
    )


@router.delete("/material-consumptions/{doc_id}", response_model=ApiMessage)
def delete_mc_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_material_consumption(connection, doc_id)
    return ApiMessage(message="Material consumption marked for deletion")


@router.post("/material-consumptions/{doc_id}/post", response_model=ApiMessage)
def post_mc_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    post_material_consumption(connection, doc_id)
    return ApiMessage(message="Material consumption posted")


@router.post("/material-consumptions/{doc_id}/unpost", response_model=ApiMessage)
def unpost_mc_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    unpost_material_consumption(connection, doc_id)
    return ApiMessage(message="Material consumption unposted")


# ── Machinery Usage Reports ───────────────────────────────────────────────


@router.get("/machinery-usage-reports", response_model=ApiResponse)
def list_mur_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    object_id: int | None = None,
) -> ApiResponse:
    items, pagination = list_machinery_usage_reports(
        connection, page=page, page_size=page_size, search=search, object_id=object_id
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/machinery-usage-reports", response_model=ApiResponse, status_code=201)
def create_mur_document(
    payload: MachineryUsageReportCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_machinery_usage_report(connection, payload.model_dump()),
        message="Machinery usage report created",
    )


@router.get("/machinery-usage-reports/{doc_id}", response_model=ApiResponse)
def get_mur_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_machinery_usage_report(connection, doc_id))


@router.put("/machinery-usage-reports/{doc_id}", response_model=ApiResponse)
def update_mur_document(
    doc_id: int,
    payload: MachineryUsageReportUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_machinery_usage_report(connection, payload.model_dump(), doc_id=doc_id),
        message="Machinery usage report updated",
    )


@router.delete("/machinery-usage-reports/{doc_id}", response_model=ApiMessage)
def delete_mur_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_machinery_usage_report(connection, doc_id)
    return ApiMessage(message="Machinery usage report marked for deletion")


@router.post("/machinery-usage-reports/{doc_id}/post", response_model=ApiMessage)
def post_mur_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    post_machinery_usage_report(connection, doc_id)
    return ApiMessage(message="Machinery usage report posted")


@router.post("/machinery-usage-reports/{doc_id}/unpost", response_model=ApiMessage)
def unpost_mur_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    unpost_machinery_usage_report(connection, doc_id)
    return ApiMessage(message="Machinery usage report unposted")


# ── Subcontract Acceptances ───────────────────────────────────────────────


@router.get("/subcontract-acceptances", response_model=ApiResponse)
def list_sa_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    object_id: int | None = None,
) -> ApiResponse:
    items, pagination = list_subcontract_acceptances(
        connection, page=page, page_size=page_size, search=search, object_id=object_id
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/subcontract-acceptances", response_model=ApiResponse, status_code=201)
def create_sa_document(
    payload: SubcontractAcceptanceCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_subcontract_acceptance(connection, payload.model_dump()),
        message="Subcontract acceptance created",
    )


@router.get("/subcontract-acceptances/{doc_id}", response_model=ApiResponse)
def get_sa_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_subcontract_acceptance(connection, doc_id))


@router.put("/subcontract-acceptances/{doc_id}", response_model=ApiResponse)
def update_sa_document(
    doc_id: int,
    payload: SubcontractAcceptanceUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_subcontract_acceptance(connection, payload.model_dump(), doc_id=doc_id),
        message="Subcontract acceptance updated",
    )


@router.delete("/subcontract-acceptances/{doc_id}", response_model=ApiMessage)
def delete_sa_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_subcontract_acceptance(connection, doc_id)
    return ApiMessage(message="Subcontract acceptance marked for deletion")


@router.post("/subcontract-acceptances/{doc_id}/post", response_model=ApiMessage)
def post_sa_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    post_subcontract_acceptance(connection, doc_id)
    return ApiMessage(message="Subcontract acceptance posted")


@router.post("/subcontract-acceptances/{doc_id}/unpost", response_model=ApiMessage)
def unpost_sa_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    unpost_subcontract_acceptance(connection, doc_id)
    return ApiMessage(message="Subcontract acceptance unposted")


# ── Overhead Expenses ─────────────────────────────────────────────────────


@router.get("/overhead-expenses", response_model=ApiResponse)
def list_oe_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    search: str | None = None,
    period: str | None = None,
) -> ApiResponse:
    items, pagination = list_overhead_expenses(
        connection, page=page, page_size=page_size, search=search, period=period
    )
    return ApiResponse(data=items, pagination=pagination)


@router.post("/overhead-expenses", response_model=ApiResponse, status_code=201)
def create_oe_document(
    payload: OverheadExpenseCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_overhead_expense(connection, payload.model_dump()),
        message="Overhead expense created",
    )


@router.get("/overhead-expenses/{doc_id}", response_model=ApiResponse)
def get_oe_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_overhead_expense(connection, doc_id))


@router.put("/overhead-expenses/{doc_id}", response_model=ApiResponse)
def update_oe_document(
    doc_id: int,
    payload: OverheadExpenseUpdate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_overhead_expense(connection, payload.model_dump(), doc_id=doc_id),
        message="Overhead expense updated",
    )


@router.delete("/overhead-expenses/{doc_id}", response_model=ApiMessage)
def delete_oe_document(
    doc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_overhead_expense(connection, doc_id)
    return ApiMessage(message="Overhead expense marked for deletion")


# ── Overhead Distribution ─────────────────────────────────────────────────


@router.post("/overhead/distribute", response_model=ApiResponse)
def distribute_overhead_endpoint(
    payload: OverheadDistributionRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiResponse:
    result = distribute_overhead(
        connection,
        period=payload.period,
        allocation_base_id=payload.allocation_base_id,
        object_id=payload.object_id,
    )
    return ApiResponse(data=result, message="Overhead distributed")


@router.post("/overhead/cancel-distribution", response_model=ApiMessage)
def cancel_distribution_endpoint(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
    period: str = Query(..., description="YYYY-MM"),
) -> ApiMessage:
    result = cancel_overhead_distribution(connection, period)
    return ApiMessage(message=f"Distribution for {period} cancelled")


# ── Cost Calculations ────────────────────────────────────────────────────


@router.get("/cost-calculations", response_model=ApiResponse)
def list_cc_documents(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ApiResponse:
    items, pagination = list_cost_calculations(connection, page=page, page_size=page_size)
    return ApiResponse(data=items, pagination=pagination)


@router.post("/cost-calculations", response_model=ApiResponse, status_code=201)
def create_cc_document(
    payload: CostCalculationCreate,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(
        data=save_cost_calculation(connection, payload.model_dump()),
        message="Cost calculation created",
    )


@router.get("/cost-calculations/{calc_id}", response_model=ApiResponse)
def get_cc_document(
    calc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiResponse:
    return ApiResponse(data=get_cost_calculation(connection, calc_id))


@router.delete("/cost-calculations/{calc_id}", response_model=ApiMessage)
def delete_cc_document(
    calc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
) -> ApiMessage:
    delete_cost_calculation(connection, calc_id)
    return ApiMessage(message="Cost calculation marked for deletion")


@router.post("/cost-calculations/{calc_id}/calculate", response_model=ApiResponse)
def calculate_cost_endpoint(
    calc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiResponse:
    result = calculate_cost(connection, calc_id)
    return ApiResponse(data=result, message="Cost calculation executed")


@router.post("/cost-calculations/{calc_id}/post", response_model=ApiMessage)
def post_cc_document(
    calc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    post_cost_calculation(connection, calc_id)
    return ApiMessage(message="Cost calculation posted")


@router.post("/cost-calculations/{calc_id}/unpost", response_model=ApiMessage)
def unpost_cc_document(
    calc_id: int,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, AdminOrManager],
) -> ApiMessage:
    unpost_cost_calculation(connection, calc_id)
    return ApiMessage(message="Cost calculation unposted")


# ── Reports ───────────────────────────────────────────────────────────────


@router.get("/reports/cost-card", response_model=ApiResponse)
def cost_card_report(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    object_id: int = Query(..., ge=1),
    period: str | None = None,
) -> ApiResponse:
    return ApiResponse(data=get_cost_card(connection, object_id, period=period))


@router.get("/reports/cost-turnover", response_model=ApiResponse)
def cost_turnover_report(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    period: str = Query(..., description="YYYY-MM"),
    object_id: int = Query(default=0, ge=0),
) -> ApiResponse:
    return ApiResponse(data=get_turnover_balance(connection, period, object_id=object_id))


@router.get("/reports/cost-deviations", response_model=ApiResponse)
def cost_deviations_report(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    period: str = Query(..., description="YYYY-MM"),
    threshold: float = Query(default=0, ge=0, description="Minimum deviation percentage"),
    object_id: int = Query(default=0, ge=0),
) -> ApiResponse:
    return ApiResponse(data=get_deviations(connection, period, threshold_pct=threshold, object_id=object_id))


@router.get("/reports/cost-profitability", response_model=ApiResponse)
def cost_profitability_report(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    period: str | None = None,
) -> ApiResponse:
    return ApiResponse(data=get_profitability(connection, period=period))


# ── Audit ─────────────────────────────────────────────────────────────────


@router.get("/audit-logs", response_model=ApiResponse)
def get_audit_logs_endpoint(
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    current_user: Annotated[UserInfo, Depends(get_current_user)],
    resource_type: str | None = None,
    resource_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse:
    items, total = get_audit_logs(
        connection,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
    )
    return ApiResponse(data=items, pagination={"total": total, "limit": limit, "offset": offset})
