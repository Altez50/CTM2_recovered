from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OpeningInventoryLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    material_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)
    object_id: int | None = Field(default=None, gt=0)
    characteristic_id: int | None = Field(default=None, gt=0)
    series_id: int | None = Field(default=None, gt=0)
    package_id: int | None = Field(default=None, gt=0)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    cost: float = Field(ge=0, allow_inf_nan=False)


class OpeningSettlementLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    counterparty_id: int = Field(gt=0)
    contract_id: int = Field(gt=0)
    object_id: int | None = Field(default=None, gt=0)
    direction: Literal['payable', 'receivable']
    amount: float = Field(gt=0, allow_inf_nan=False)


class OpeningBalanceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    number: str = Field(default='', max_length=100)
    date: date
    organization_id: int = Field(gt=0)
    description: str | None = Field(default=None, max_length=2000)
    inventory: list[OpeningInventoryLine] = Field(default_factory=list)
    settlements: list[OpeningSettlementLine] = Field(default_factory=list)

    @model_validator(mode='after')
    def not_empty(self):
        if not self.inventory and not self.settlements:
            raise ValueError('Укажите хотя бы один начальный остаток')
        return self
