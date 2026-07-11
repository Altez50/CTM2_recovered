from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReferenceKind = Literal["counterparties", "objects", "works", "persons", "organizations", "contracts", "materials"]


class CounterpartyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=32)
    contact_person: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    parent_id: int | None = None
    marked_for_deletion: bool = False
    is_group: bool = False


class ObjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    owner_id: int | None = None
    parent_id: int | None = None
    marked_for_deletion: bool = False
    is_group: bool = False


class WorkPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    unit: str | None = Field(default=None, max_length=32)
    price: float = 0
    labor_rate: float = 0
    specification_review_status: Literal["ok", "incorrect", "corrected"] = "ok"
    specification_review_note: str | None = Field(default=None, max_length=1000)
    parent_id: int | None = None
    marked_for_deletion: bool = False
    is_group: bool = False


class PersonPayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    personnel_number: str | None = Field(default=None, max_length=64)
    position: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    hourly_rate: float = Field(default=0, ge=0)
    user_id: int | None = None
    parent_id: int | None = None
    marked_for_deletion: bool = False
    is_group: bool = False


class OrganizationPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=32)
    default_responsible_id: int | None = None
    parent_id: int | None = None
    marked_for_deletion: bool = False
    is_group: bool = False


class ContractPayload(BaseModel):
    number: str = Field(min_length=1, max_length=100)
    date: str | None = Field(default=None, max_length=20)
    organization_id: int | None = None
    counterparty_id: int | None = None
    parent_id: int | None = None
    amount: float = Field(default=0, ge=0)
    kind: str = Field(default="supply", max_length=20)
    currency: str = Field(default="RUB", max_length=10)
    vat_rate: float = Field(default=20.0, ge=0, le=100)
    payment_deferral_days: int = Field(default=0, ge=0)
    agreement_date: str | None = Field(default=None, max_length=20)
    valid_until: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=1000)
    marked_for_deletion: bool = False
    is_group: bool = False


class MaterialPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    unit_id: int | None = None
    price: float = Field(default=0, ge=0)
    marked_for_deletion: bool = False


REFERENCE_MODEL_MAP = {
    "counterparties": CounterpartyPayload,
    "objects": ObjectPayload,
    "works": WorkPayload,
    "persons": PersonPayload,
    "organizations": OrganizationPayload,
    "contracts": ContractPayload,
    "materials": MaterialPayload,
}


def validate_reference_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind not in REFERENCE_MODEL_MAP:
        raise ValueError(f"Unsupported reference kind: {kind}")
    model = REFERENCE_MODEL_MAP[kind](**payload)
    return model.model_dump()
