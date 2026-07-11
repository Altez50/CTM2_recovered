from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


GoodsLineKind = Literal["receipt", "issue"]
SettlementDirection = Literal["receivable", "payable"]
InventoryRecorderType = Literal["goods_receipt", "goods_issue"]


class GoodsLineBase(BaseModel):
    line_number: int = Field(ge=1)
    material_id: int | None = None
    name: str = Field(min_length=1, max_length=500)
    unit_id: int | None = None
    unit: str | None = Field(default=None, max_length=50)
    quantity: float = Field(default=0, ge=0)
    price_without_vat: float = Field(default=0, ge=0)
    vat_rate: float = Field(default=20.0, ge=0, le=100)
    object_id: int | None = None
    drawing_code: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=1000)
    uuid: str | None = None


class GoodsLineCreate(GoodsLineBase):
    pass


class GoodsLine(GoodsLineBase):
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
    pass


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
    counterparty_name: str | None = None
    contract_number: str | None = None
    object_name: str | None = None
    responsible_name: str | None = None
    lines: list[GoodsLine] = Field(default_factory=list)


class InventoryBalanceItem(BaseModel):
    material_id: int | None = None
    material_name: str | None = None
    material_code: str | None = None
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
    period: date
    recorder_type: str
    recorder_id: int
    line_number: int
    material_id: int | None = None
    material_name: str | None = None
    material_code: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    unit_id: int | None = None
    unit_name: str | None = None
    quantity_income: float = 0
    quantity_expense: float = 0
    sum_income: float = 0
    sum_expense: float = 0


class SettlementBalanceItem(BaseModel):
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
