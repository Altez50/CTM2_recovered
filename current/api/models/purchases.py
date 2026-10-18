"""Procurement input contracts; dependent documents accept source lines only."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.models.goods import GoodsLineBase

PurchaseKind = Literal['orders', 'acquisitions', 'receipt-orders', 'cancellations', 'discrepancies', 'quantity-adjustments']


class OrderLine(GoodsLineBase):
    model_config = ConfigDict(extra='forbid')
    line_type: Literal['goods', 'service'] = 'goods'
    quantity: float = Field(gt=0, allow_inf_nan=False)
    material_id: int | None = Field(default=None, gt=0)
    unit_id: int | None = Field(default=None, gt=0)
    object_id: int | None = Field(default=None, gt=0)


class PurchaseOrderCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str = Field(default='', max_length=100)
    date: date
    organization_id: int = Field(gt=0)
    counterparty_id: int = Field(gt=0)
    contract_id: int = Field(gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    object_id: int | None = Field(default=None, gt=0)
    estimate_id: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=2000)
    lines: list[OrderLine] = Field(min_length=1)


class PurchaseBasisLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_line_id: int = Field(gt=0)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    receipt_line_id: int | None = Field(default=None, gt=0)


class LinkedPurchaseCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str = Field(default='', max_length=100)
    date: date
    source_id: int = Field(gt=0)
    description: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseBasisLine] = Field(min_length=1)
