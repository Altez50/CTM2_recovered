from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PaymentDirection = Literal["incoming", "outgoing"]
PaymentCategory = Literal[
    "customer_stage",
    "payroll",
    "supplier",
    "tax",
    "supplier_invoice",
    "customer_invoice",
    "other",
]
PaymentSourceKind = Literal["manual", "work_execution", "payroll", "goods_receipt", "goods_issue"]


class PaymentScheduleLineBase(BaseModel):
    line_number: int = Field(ge=1)
    direction: PaymentDirection = "outgoing"
    category: PaymentCategory = "other"
    planned_date: date
    counterparty_id: int | None = None
    contract_id: int | None = None
    estimate_id: int | None = None
    object_id: int | None = None
    planned_amount: float = Field(default=0, ge=0)
    description: str | None = Field(default=None, max_length=1000)
    source_kind: PaymentSourceKind = "manual"
    source_ref: str | None = None
    is_group: bool = False
    group_name: str | None = Field(default=None, max_length=255)
    parent_group_id: int | None = None
    parent_group_uuid: str | None = None
    is_collapsed: bool = False
    uuid: str | None = None


class PaymentScheduleLineCreate(PaymentScheduleLineBase):
    pass


class PaymentScheduleLine(PaymentScheduleLineBase):
    id: int
    schedule_id: int
    counterparty_name: str | None = None
    contract_number: str | None = None
    estimate_number: str | None = None
    object_name: str | None = None
    fact_amount: float = 0
    balance: float = 0


class PaymentScheduleBase(BaseModel):
    number: str = Field(default="", max_length=100)
    date_from: date
    date_to: date
    object_id: int | None = None
    contract_id: int | None = None
    responsible_id: int | None = None


class PaymentScheduleCreate(PaymentScheduleBase):
    lines: list[PaymentScheduleLineCreate] = Field(default_factory=list)


class PaymentScheduleUpdate(PaymentScheduleBase):
    lines: list[PaymentScheduleLineCreate] = Field(default_factory=list)


class PaymentSchedule(PaymentScheduleBase):
    id: int
    uuid: str | None = None
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    object_name: str | None = None
    contract_number: str | None = None
    responsible_name: str | None = None
    total_incoming: float = 0
    total_outgoing: float = 0
    lines: list[PaymentScheduleLine] = Field(default_factory=list)


class PaymentTransactionBase(BaseModel):
    number: str = Field(default="", max_length=100)
    date: date
    direction: PaymentDirection = "outgoing"
    category: PaymentCategory = "other"
    counterparty_id: int | None = None
    contract_id: int | None = None
    estimate_id: int | None = None
    object_id: int | None = None
    linked_schedule_id: int | None = None
    linked_line_id: int | None = None
    amount: float = Field(default=0, ge=0)
    description: str | None = Field(default=None, max_length=1000)


class PaymentTransactionCreate(PaymentTransactionBase):
    pass


class PaymentTransaction(PaymentTransactionBase):
    id: int
    uuid: str | None = None
    is_posted: bool
    posted_at: datetime | None = None
    marked_for_deletion: bool
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_at: datetime | None = None
    counterparty_name: str | None = None
    contract_number: str | None = None
    linked_line_uuid: str | None = None


class PaymentRegisterItem(BaseModel):
    planned_date: date | None = None
    direction: PaymentDirection = "outgoing"
    category: PaymentCategory = "other"
    counterparty_id: int | None = None
    counterparty_name: str | None = None
    contract_id: int | None = None
    contract_number: str | None = None
    object_id: int | None = None
    object_name: str | None = None
    estimate_id: int | None = None
    estimate_number: str | None = None
    planned_amount: float = 0
    fact_amount: float = 0
    balance: float = 0
    is_overdue: bool = False
    is_paid: bool = False


class CashflowDayItem(BaseModel):
    date: date
    incoming_planned: float = 0
    outgoing_planned: float = 0
    incoming_fact: float = 0
    outgoing_fact: float = 0
    cumulative_balance: float = 0
    is_deficit: bool = False


class SuggestIncomingRequest(BaseModel):
    date_from: date
    date_to: date
    object_id: int | None = None
    contract_id: int | None = None


class SuggestPayrollRequest(BaseModel):
    date_from: date
    date_to: date
    object_id: int | None = None
    estimate_id: int | None = None


class SuggestGoodsRequest(BaseModel):
    date_from: date
    date_to: date
    organization_id: int | None = None
    object_id: int | None = None
