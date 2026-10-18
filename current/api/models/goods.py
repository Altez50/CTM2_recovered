from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GoodsLineKind = Literal["receipt", "issue"]
SettlementDirection = Literal["receivable", "payable"]
InventoryRecorderType = Literal["goods_receipt", "goods_issue", "goods_transfer"]


class GoodsLineBase(BaseModel):
    package_id: int | None = Field(default=None, gt=0)
    characteristic_id: int | None = Field(default=None, gt=0)
    series_id: int | None = Field(default=None, gt=0)
    line_number: int = Field(ge=1)
    material_id: int | None = None
    name: str = Field(min_length=1, max_length=500)
    unit_id: int | None = None
    unit: str | None = Field(default=None, max_length=50)
    quantity: float = Field(default=0, ge=0, allow_inf_nan=False)
    price_without_vat: float = Field(default=0, ge=0, allow_inf_nan=False)
    vat_rate: float = Field(default=20.0, ge=0, le=100)
    object_id: int | None = None
    drawing_code: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1000)
    uuid: str | None = None


class GoodsLineCreate(GoodsLineBase):
    pass


class GoodsLine(GoodsLineBase):
    conversion_factor: float = 1
    base_quantity: float | None = None
    base_unit_id: int | None = None
    package_name: str | None = None
    characteristic_name: str | None = None
    series_name: str | None = None
    id: int
    vat_amount: float = 0
    sum_without_vat: float = 0
    sum_with_vat: float = 0
    material_code: str | None = None
    object_name: str | None = None
    unit_name: str | None = None


class GoodsDocumentBase(BaseModel):
    number: str = Field(default="", max_length=100)
    date: date
    organization_id: int
    warehouse: str = Field(default="", max_length=200)
    warehouse_id: int | None = None
    counterparty_id: int | None = None
    contract_id: int | None = None
    object_id: int | None = None
    estimate_id: int | None = None
    responsible_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    auto_schedule: bool = True
    lines: list[GoodsLineCreate] = Field(default_factory=list)


class GoodsReceiptCreate(GoodsDocumentBase):
    pass


class GoodsIssueCreate(GoodsDocumentBase):
    based_on_type: str | None = None
    based_on_id: int | None = Field(default=None, gt=0)
    based_on_number: str | None = None


class GoodsTransferLineCreate(BaseModel):
    package_id: int | None = Field(default=None, gt=0)
    characteristic_id: int | None = Field(default=None, gt=0)
    series_id: int | None = Field(default=None, gt=0)
    line_number: int = Field(ge=1)
    material_id: int
    name: str | None = Field(default=None, max_length=500)
    unit_id: int
    quantity: float = Field(gt=0, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=1000)
    uuid: str | None = None


class GoodsTransferCreate(BaseModel):
    number: str = Field(default="", max_length=100)
    date: date
    organization_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    source_object_id: int | None = None
    destination_object_id: int | None = None
    responsible_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    lines: list[GoodsTransferLineCreate]


class GoodsDocument(GoodsDocumentBase):
    id: int
    uuid: str | None = None
    sum_without_vat: float = 0
    vat_amount: float = 0
    sum_with_vat: float = 0
    due_date: date | None = None
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    organization_name: str | None = None
    warehouse_name: str | None = None
    counterparty_name: str | None = None
    contract_number: str | None = None
    object_name: str | None = None
    responsible_name: str | None = None
    lines: list[GoodsLine] = Field(default_factory=list)


class InventoryBalanceItem(BaseModel):
    characteristic_id: int | None = None
    series_id: int | None = None
    characteristic_name: str | None = None
    series_name: str | None = None
    material_id: int | None = None
    material_name: str | None = None
    material_code: str | None = None
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    unit_id: int | None = None
    unit_name: str | None = None
    quantity_income: float = 0
    quantity_expense: float = 0
    quantity_balance: float = 0
    sum_income: float = 0
    sum_expense: float = 0
    average_price: float = 0


class InventoryMovementItem(BaseModel):
    characteristic_id: int | None = None
    series_id: int | None = None
    characteristic_name: str | None = None
    series_name: str | None = None
    period: date
    recorder_type: str
    recorder_id: int
    line_number: int
    material_id: int | None = None
    material_name: str | None = None
    material_code: str | None = None
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    unit_id: int | None = None
    unit_name: str | None = None
    quantity_income: float = 0
    quantity_expense: float = 0
    sum_income: float = 0
    sum_expense: float = 0


class SettlementBalanceItem(BaseModel):
    customer_advance: float = 0
    supplier_advance: float = 0
    organization_id: int
    organization_name: str | None = None
    counterparty_id: int | None = None
    counterparty_name: str | None = None
    contract_id: int | None = None
    contract_number: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    receivable_accrual: float = 0
    receivable_payment: float = 0
    receivable_balance: float = 0
    payable_accrual: float = 0
    payable_payment: float = 0
    payable_balance: float = 0


class SettlementLedgerItem(BaseModel):
    customer_advance_running: float = 0
    supplier_advance_running: float = 0
    period: date
    recorder_type: str
    recorder_id: int
    line_number: int
    direction: SettlementDirection
    accrual_amount: float = 0
    payment_amount: float = 0
    planned_amount: float = 0
    contract_id: int | None = None
    contract_number: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    receivable_balance_running: float = 0
    payable_balance_running: float = 0


class OverdueItem(BaseModel):
    organization_id: int
    organization_name: str | None = None
    counterparty_id: int | None = None
    counterparty_name: str | None = None
    contract_id: int | None = None
    contract_number: str | None = None
    direction: SettlementDirection
    overdue_amount: float = 0
    period: date | None = None
    days_overdue: int = 0


class GoodsExcelImportPreview(BaseModel):
    filename: str
    detected_columns: dict[str, int] = {}
    rows: list[GoodsLineCreate] = []
    warnings: list[str] = []


class GoodsReturnLineCreate(BaseModel):
    source_line_id: int = Field(gt=0)
    quantity: float = Field(gt=0, allow_inf_nan=False)


class GoodsReturnCreate(BaseModel):
    kind: Literal["customer", "supplier"]
    source_id: int = Field(gt=0)
    number: str = Field(default="", max_length=100)
    date: date
    description: str | None = Field(default=None, max_length=2000)
    organization_id: int | None = None
    counterparty_id: int | None = None
    contract_id: int | None = None
    warehouse_id: int | None = None
    object_id: int | None = None
    lines: list[GoodsReturnLineCreate] = Field(min_length=1)


class GoodsReturnRefundCreate(BaseModel):
    return_id: int = Field(gt=0)
    number: str = Field(default="", max_length=100)
    date: date
    amount: float = Field(gt=0, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=2000)


class GoodsPriceAdjustmentLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_line_id: int = Field(gt=0)
    new_price: float = Field(ge=0, allow_inf_nan=False)


class GoodsPriceAdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["sale", "purchase"]
    source_id: int = Field(gt=0)
    date: date
    number: str = Field(default="", max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    organization_id: int | None = None
    counterparty_id: int | None = None
    contract_id: int | None = None
    warehouse_id: int | None = None
    object_id: int | None = None
    estimate_id: int | None = None
    lines: list[GoodsPriceAdjustmentLineCreate] = Field(min_length=1)
