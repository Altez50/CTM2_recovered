from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from api.config import settings


class EstimateLineBase(BaseModel):
    line_number: int = Field(ge=1)
    work_id: int | None = None
    quantity: float = Field(default=0, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    price: float = Field(default=0, ge=0)
    labor_rate: float = Field(default=0, ge=0)
    sum: float = Field(default=0, ge=0)
    planned_labor: float = Field(default=0, ge=0)
    is_group: bool = False
    group_name: str | None = Field(default=None, max_length=255)
    parent_group_id: int | None = None
    parent_group_uuid: str | None = None
    is_collapsed: bool = False


class EstimateLineCreate(EstimateLineBase):
    pass


class EstimateLine(EstimateLineBase):
    id: int
    uuid: str | None = None
    estimate_id: int
    estimate_uuid: str | None = None
    work_uuid: str | None = None
    work_name: str | None = None


class EstimateBase(BaseModel):
    number: str = Field(default="", max_length=100)
    date: date
    customer_id: int | None = None
    object_id: int | None = None
    contractor_id: int | None = None
    responsible_id: int | None = None
    contract_id: int | None = None


class EstimateCreate(EstimateBase):
    lines: list[EstimateLineCreate] = Field(default_factory=list)


class EstimateUpdate(EstimateBase):
    lines: list[EstimateLineCreate] = Field(default_factory=list)


class Estimate(EstimateBase):
    id: int
    uuid: str | None = None
    total_sum: float
    total_labor: float
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    customer_uuid: str | None = None
    object_uuid: str | None = None
    contractor_uuid: str | None = None
    responsible_uuid: str | None = None
    customer_name: str | None = None
    object_name: str | None = None
    contractor_name: str | None = None
    responsible_name: str | None = None
    contract_id: int | None = None
    contract_uuid: str | None = None
    contract_number: str | None = None
    lines: list[EstimateLine] = Field(default_factory=list)


class DailyReportLineBase(BaseModel):
    line_number: int = Field(ge=1)
    work_id: int | None = None
    planned_labor: float = Field(default=0, ge=0)
    actual_labor: float = Field(default=0, ge=0)
    deviation_percent: float = 0
    quantity: float = Field(default=0, ge=0)
    unit: str | None = Field(default=None, max_length=32)
    price: float = Field(default=0, ge=0)
    actual_sum: float = Field(default=0, ge=0)
    executor_ids: list[int] = Field(default_factory=list)
    is_group: bool = False
    group_name: str | None = Field(default=None, max_length=255)
    parent_group_id: int | None = None
    parent_group_uuid: str | None = None
    is_collapsed: bool = False


class DailyReportLineCreate(DailyReportLineBase):
    pass


class DailyReportLine(DailyReportLineBase):
    id: int
    uuid: str | None = None
    report_id: int
    report_uuid: str | None = None
    work_uuid: str | None = None
    work_name: str | None = None
    executor_uuids: list[str] = Field(default_factory=list)
    executor_names: list[str] = Field(default_factory=list)


class DailyReportBase(BaseModel):
    number: str = Field(default="", max_length=100)
    date: date
    estimate_id: int | None = None
    foreman_id: int | None = None
    supplementary_agreement_id: int | None = None


class DailyReportCreate(DailyReportBase):
    lines: list[DailyReportLineCreate] = Field(default_factory=list)


class DailyReportUpdate(DailyReportBase):
    lines: list[DailyReportLineCreate] = Field(default_factory=list)


class DailyReport(DailyReportBase):
    id: int
    uuid: str | None = None
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    estimate_uuid: str | None = None
    foreman_uuid: str | None = None
    estimate_number: str | None = None
    foreman_name: str | None = None
    supplementary_agreement_id: int | None = None
    supplementary_agreement_uuid: str | None = None
    supplementary_agreement_number: str | None = None
    lines: list[DailyReportLine] = Field(default_factory=list)


class TimesheetLineBase(BaseModel):
    line_number: int = Field(ge=1)
    employee_id: int = Field(ge=1)
    hourly_rate: float = Field(default=0, ge=0)
    days: dict[int, float] = Field(default_factory=dict)


class TimesheetLineCreate(TimesheetLineBase):
    pass


class TimesheetLine(TimesheetLineBase):
    id: int
    uuid: str | None = None
    timesheet_id: int
    timesheet_uuid: str | None = None
    employee_uuid: str | None = None
    employee_name: str | None = None
    total_hours: float = 0
    total_amount: float = 0


class TimesheetBase(BaseModel):
    number: str = Field(default="", max_length=settings.timesheet_number_total_length)
    date: date
    object_id: int | None = Field(default=None, ge=1)
    estimate_id: int | None = Field(default=None, ge=1)
    foreman_id: int | None = Field(default=None, ge=1)
    month_year: str = Field(pattern=r"^\d{4}-\d{2}$")


class TimesheetCreate(TimesheetBase):
    lines: list[TimesheetLineCreate] = Field(default_factory=list)


class TimesheetUpdate(TimesheetBase):
    lines: list[TimesheetLineCreate] = Field(default_factory=list)


class Timesheet(TimesheetBase):
    id: int
    uuid: str | None = None
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    object_uuid: str | None = None
    estimate_uuid: str | None = None
    foreman_uuid: str | None = None
    object_name: str | None = None
    estimate_number: str | None = None
    foreman_name: str | None = None
    total_hours: float = 0
    total_amount: float = 0
    lines: list[TimesheetLine] = Field(default_factory=list)


class TimesheetAutofillRequest(BaseModel):
    object_id: int = Field(ge=1)
    estimate_id: int | None = Field(default=None, ge=1)
    month_year: str = Field(pattern=r"^\d{4}-\d{2}$")


class TimesheetMissingEmployee(BaseModel):
    employee_name: str = Field(min_length=1, max_length=255)
    hourly_rate: float = Field(default=0, ge=0)
    source_line_numbers: list[int] = Field(default_factory=list)


class TimesheetImportedEmployee(BaseModel):
    source_line_number: int = Field(ge=1)
    employee_name: str = Field(min_length=1, max_length=255)
    personnel_number: str | None = Field(default=None, max_length=64)
    position: str | None = Field(default=None, max_length=255)
    hourly_rate: float | None = Field(default=None, ge=0)
    days: dict[int, float] = Field(default_factory=dict)
    total_hours: float = Field(default=0, ge=0)
    total_amount: float = Field(default=0, ge=0)
    matched_employee_id: int | None = Field(default=None, ge=1)
    matched_employee_name: str | None = Field(default=None, max_length=255)
    matched_by: str | None = Field(default=None, pattern="^(full_name|personnel_number)$")


class TimesheetImportPreview(BaseModel):
    document_info: dict[str, str | bool | None] = Field(default_factory=dict)
    lines: list[TimesheetLine] = Field(default_factory=list)
    imported_rows: list[TimesheetImportedEmployee] = Field(default_factory=list)
    missing_employees: list[TimesheetMissingEmployee] = Field(default_factory=list)
    requires_employee_creation: bool = False


class RegisterMovement(BaseModel):
    id: int | None = None
    uuid: str | None = None
    recorder_type: str
    recorder_id: int
    recorder_uuid: str | None = None
    line_number: int
    period: date
    object_id: int | None = None
    object_uuid: str | None = None
    object_name: str | None = None
    estimate_id: int | None = None
    estimate_uuid: str | None = None
    estimate_number: str | None = None
    work_id: int | None = None
    work_uuid: str | None = None
    work_name: str | None = None
    quantity_income: float = 0
    quantity_expense: float = 0
    sum_income: float = 0
    sum_expense: float = 0
    balance_quantity: float = 0
    balance_sum: float = 0
