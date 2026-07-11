"""Pydantic schemas for the cost accounting subsystem."""

from __future__ import annotations

from datetime import date as date_type, datetime
from typing import Any

from pydantic import BaseModel, Field

from api.models.common import ORMModel, Pagination


# ── Cost Element ──────────────────────────────────────────────────────────

class CostElementBase(BaseModel):
    code: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=200)
    kind: str = Field(default="materials", max_length=30)
    is_direct: bool = True
    allocation_base_id: int | None = None


class CostElement(CostElementBase, ORMModel):
    id: int
    is_predefined: bool = False


# ── Allocation Base ───────────────────────────────────────────────────────

class AllocationBase(BaseModel):
    id: int
    name: str
    kind: str


# ── Machine ───────────────────────────────────────────────────────────────

class MachineBase(BaseModel):
    name: str = Field(default="", max_length=200)
    code: str = Field(default="", max_length=50)
    cost_per_hour: float = Field(default=0.0, ge=0)
    operator_rate_per_hour: float = Field(default=0.0, ge=0)
    unit: str = Field(default="маш.-ч", max_length=20)


class MachineCreate(MachineBase):
    pass


class MachineUpdate(MachineBase):
    pass


class Machine(MachineBase, ORMModel):
    id: int
    marked_for_deletion: bool = False


# ── Material Consumption ─────────────────────────────────────────────────

class MaterialConsumptionLineBase(BaseModel):
    line_number: int = Field(default=1, ge=1)
    work_id: int | None = None
    material_id: int | None = None
    planned_quantity: float = Field(default=0.0, ge=0)
    actual_quantity: float = Field(default=0.0, ge=0)
    price: float = Field(default=0.0, ge=0)
    sum: float = Field(default=0.0, ge=0)
    cost_element_id: int | None = None


class MaterialConsumptionLineCreate(MaterialConsumptionLineBase):
    pass


class MaterialConsumptionLine(MaterialConsumptionLineBase, ORMModel):
    id: int
    document_id: int
    work_name: str | None = None
    material_name: str | None = None


class MaterialConsumptionBase(BaseModel):
    number: str = Field(default="", max_length=50)
    date: date_type = Field(default_factory=date_type.today)
    object_id: int | None = None
    estimate_id: int | None = None
    foreman_id: int | None = None
    warehouse: str = Field(default="", max_length=200)


class MaterialConsumptionCreate(MaterialConsumptionBase):
    lines: list[MaterialConsumptionLineCreate] = Field(default_factory=list)


class MaterialConsumptionUpdate(MaterialConsumptionBase):
    lines: list[MaterialConsumptionLineCreate] = Field(default_factory=list)


class MaterialConsumption(MaterialConsumptionBase, ORMModel):
    id: int
    uuid: str | None = None
    is_posted: bool = False
    posted_at: datetime | None = None
    marked_for_deletion: bool = False
    lines: list[MaterialConsumptionLine] = Field(default_factory=list)
    object_name: str | None = None
    estimate_number: str | None = None
    foreman_name: str | None = None


# ── Machinery Usage Report ────────────────────────────────────────────────

class MachineryUsageLineBase(BaseModel):
    line_number: int = Field(default=1, ge=1)
    machine_id: int | None = None
    work_id: int | None = None
    hours: float = Field(default=0.0, ge=0)
    machine_cost: float = Field(default=0.0, ge=0)
    operator_labor: float = Field(default=0.0, ge=0)


class MachineryUsageLineCreate(MachineryUsageLineBase):
    pass


class MachineryUsageLine(MachineryUsageLineBase, ORMModel):
    id: int
    document_id: int
    machine_name: str | None = None


class MachineryUsageReportBase(BaseModel):
    number: str = Field(default="", max_length=50)
    date: date_type = Field(default_factory=date_type.today)
    object_id: int | None = None
    estimate_id: int | None = None
    foreman_id: int | None = None


class MachineryUsageReportCreate(MachineryUsageReportBase):
    lines: list[MachineryUsageLineCreate] = Field(default_factory=list)


class MachineryUsageReportUpdate(MachineryUsageReportBase):
    lines: list[MachineryUsageLineCreate] = Field(default_factory=list)


class MachineryUsageReport(MachineryUsageReportBase, ORMModel):
    id: int
    uuid: str | None = None
    is_posted: bool = False
    posted_at: datetime | None = None
    marked_for_deletion: bool = False
    lines: list[MachineryUsageLine] = Field(default_factory=list)
    object_name: str | None = None
    estimate_number: str | None = None


# ── Subcontract Acceptance ────────────────────────────────────────────────

class SubcontractAcceptanceLineBase(BaseModel):
    line_number: int = Field(default=1, ge=1)
    work_id: int | None = None
    counterparty_id: int | None = None
    sum: float = Field(default=0.0, ge=0)
    description: str = Field(default="", max_length=500)


class SubcontractAcceptanceLineCreate(SubcontractAcceptanceLineBase):
    pass


class SubcontractAcceptanceLine(SubcontractAcceptanceLineBase, ORMModel):
    id: int
    document_id: int
    counterparty_name: str | None = None


class SubcontractAcceptanceBase(BaseModel):
    number: str = Field(default="", max_length=50)
    date: date_type = Field(default_factory=date_type.today)
    object_id: int | None = None
    estimate_id: int | None = None


class SubcontractAcceptanceCreate(SubcontractAcceptanceBase):
    lines: list[SubcontractAcceptanceLineCreate] = Field(default_factory=list)


class SubcontractAcceptanceUpdate(SubcontractAcceptanceBase):
    lines: list[SubcontractAcceptanceLineCreate] = Field(default_factory=list)


class SubcontractAcceptance(SubcontractAcceptanceBase, ORMModel):
    id: int
    uuid: str | None = None
    is_posted: bool = False
    posted_at: datetime | None = None
    marked_for_deletion: bool = False
    lines: list[SubcontractAcceptanceLine] = Field(default_factory=list)
    object_name: str | None = None
    estimate_number: str | None = None


# ── Overhead Expense ──────────────────────────────────────────────────────

class OverheadExpenseLineBase(BaseModel):
    line_number: int = Field(default=1, ge=1)
    cost_element_id: int | None = None
    counterparty_id: int | None = None
    sum: float = Field(default=0.0, ge=0)
    description: str = Field(default="", max_length=500)


class OverheadExpenseLineCreate(OverheadExpenseLineBase):
    pass


class OverheadExpenseLine(OverheadExpenseLineBase, ORMModel):
    id: int
    document_id: int
    cost_element_name: str | None = None
    counterparty_name: str | None = None


class OverheadExpenseBase(BaseModel):
    number: str = Field(default="", max_length=50)
    date: date_type = Field(default_factory=date_type.today)
    period: str = Field(default="", max_length=10)


class OverheadExpenseCreate(OverheadExpenseBase):
    lines: list[OverheadExpenseLineCreate] = Field(default_factory=list)


class OverheadExpenseUpdate(OverheadExpenseBase):
    lines: list[OverheadExpenseLineCreate] = Field(default_factory=list)


class OverheadExpense(OverheadExpenseBase, ORMModel):
    id: int
    uuid: str | None = None
    is_distributed: bool = False
    lines: list[OverheadExpenseLine] = Field(default_factory=list)


# ── Cost Calculation ─────────────────────────────────────────────────────

class CostCalculationBase(BaseModel):
    number: str = Field(default="", max_length=50)
    period: str = Field(default="", max_length=10)
    date: date_type = Field(default_factory=date_type.today)
    object_id: int = Field(default=0, ge=0)


class CostCalculationCreate(CostCalculationBase):
    pass


class CostCalculation(CostCalculationBase, ORMModel):
    id: int
    uuid: str | None = None
    status: str = "draft"
    object_name: str | None = None


# ── Overhead Distribution ─────────────────────────────────────────────────

class OverheadDistributionRequest(BaseModel):
    period: str = Field(..., max_length=10, description="YYYY-MM")
    allocation_base_id: int
    object_id: int = Field(default=0, ge=0, description="0 = all objects")


class OverheadDistributionResult(BaseModel):
    period: str
    allocation_base_name: str
    total_distributed: float
    record_count: int


# ── Reports ───────────────────────────────────────────────────────────────

class CostElementSummary(BaseModel):
    cost_element_id: int
    cost_element_name: str
    cost_element_kind: str
    planned_amount: float
    actual_amount: float
    deviation: float


class WorkCostRow(BaseModel):
    work_id: int
    work_name: str | None
    completed_quantity: float
    planned_cost: float
    actual_cost: float
    deviation: float
    contract_value: float
    profit: float
    profitability_pct: float


class CostCardResponse(BaseModel):
    object_id: int
    object_name: str | None
    period: str | None
    elements: list[CostElementSummary]
    total_planned: float
    total_actual: float
    total_deviation: float
    total_contract_value: float
    total_profit: float
    profitability_pct: float
    works: list[WorkCostRow] = Field(default_factory=list)


class TurnoverRow(BaseModel):
    cost_element_id: int
    cost_element_name: str
    cost_element_kind: str
    opening_balance: float
    inflow: float
    outflow: float
    closing_balance: float


class TurnoverReportResponse(BaseModel):
    period: str
    object_id: int
    object_name: str | None
    rows: list[TurnoverRow]


class DeviationRow(BaseModel):
    work_id: int
    work_name: str | None
    cost_element_name: str
    planned_amount: float
    actual_amount: float
    deviation: float
    deviation_pct: float


class DeviationsReportResponse(BaseModel):
    period: str
    object_id: int
    threshold_pct: float
    rows: list[DeviationRow]


class ProfitabilityRow(BaseModel):
    object_id: int
    object_name: str | None
    planned_cost: float
    actual_cost: float
    contract_value: float
    profit: float
    profitability_pct: float


class ProfitabilityReportResponse(BaseModel):
    period: str | None
    rows: list[ProfitabilityRow]


# ── Limit Check ───────────────────────────────────────────────────────────

class LimitCheckRequest(BaseModel):
    work_id: int
    material_id: int
    actual_quantity: float = Field(..., gt=0)
    completed_quantity: float = Field(default=1.0, ge=0)


class LimitCheckResponse(BaseModel):
    work_id: int
    material_id: int
    planned_quantity: float
    actual_quantity: float
    limit_exceeded: bool
    exceed_pct: float
