from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ComponentType = Literal["Material", "Labor", "Equipment", "Other"]
WorkReviewStatus = Literal["ok", "incorrect", "corrected"]


class WorkSpecificationPayload(BaseModel):
    id: int | None = None
    uuid: str | None = None
    component_type: ComponentType
    component_name: str = Field(min_length=1, max_length=500)
    unit_id: int | None = None
    unit_uuid: str | None = None
    unit_name: str | None = Field(default=None, max_length=128)
    consumption_rate: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    material_id: int | None = None
    material_uuid: str | None = None


class WorkDetailPayload(BaseModel):
    uuid: str | None = None
    name: str = Field(min_length=1, max_length=500)
    code: str | None = Field(default=None, max_length=64)
    unit: str | None = Field(default=None, max_length=32)
    price: float = 0
    labor_rate: float = 0
    specification_review_status: WorkReviewStatus = "ok"
    specification_review_note: str | None = Field(default=None, max_length=1000)
    parent_id: int | None = None
    parent_uuid: str | None = None
    marked_for_deletion: bool = False
    is_group: bool = False
    specifications: list[WorkSpecificationPayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_group_fields(self) -> "WorkDetailPayload":
        if self.is_group and ((self.price or 0) != 0 or (self.labor_rate or 0) != 0):
            raise ValueError("Group works cannot have price or labor rate")
        return self


class UnitRecord(BaseModel):
    id: int
    uuid: str | None = None
    name: str
    short_name: str | None = None


class MaterialRecord(BaseModel):
    id: int
    uuid: str | None = None
    code: str | None = None
    name: str
    unit_id: int | None = None
    unit_uuid: str | None = None
    unit_name: str | None = None
    price: float = 0


class WorkSpecificationRecord(BaseModel):
    id: int
    uuid: str | None = None
    work_id: int
    work_uuid: str | None = None
    component_type: ComponentType
    component_name: str
    unit_id: int | None = None
    unit_uuid: str | None = None
    unit_name: str | None = None
    consumption_rate: float
    unit_price: float
    total_cost: float
    material_id: int | None = None
    material_uuid: str | None = None
    modified_at: str | None = None


class WorkDetailRecord(BaseModel):
    id: int
    uuid: str | None = None
    name: str
    code: str | None = None
    unit: str | None = None
    price: float = 0
    labor_rate: float = 0
    specification_review_status: WorkReviewStatus = "ok"
    specification_review_note: str | None = None
    parent_id: int | None = None
    parent_uuid: str | None = None
    marked_for_deletion: bool = False
    is_group: bool = False
    specifications: list[WorkSpecificationRecord] = Field(default_factory=list)


class ImportedSpecificationRow(BaseModel):
    source_row: int
    component_type: str | None = None
    component_name: str | None = None
    material_code: str | None = None
    material_id: int | None = None
    material_status: str | None = None
    matched_material_name: str | None = None
    matched_material_code: str | None = None
    unit_name: str | None = None
    unit_id: int | None = None
    unit_status: str | None = None
    consumption_rate: float | None = None
    unit_price: float | None = None
    total_cost: float = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MissingImportedMaterial(BaseModel):
    material_name: str = Field(min_length=1, max_length=500)
    material_code: str | None = Field(default=None, max_length=128)
    unit_name: str | None = Field(default=None, max_length=128)
    unit_id: int | None = None
    unit_status: str | None = None
    unit_price: float = Field(default=0, ge=0)
    source_row_numbers: list[int] = Field(default_factory=list)


class ImportMaterialCreateRequest(BaseModel):
    materials: list[MissingImportedMaterial] = Field(default_factory=list)


class ImportMaterialCreateResult(BaseModel):
    material_id: int
    material_name: str
    material_code: str | None = None
    unit_id: int | None = None
    unit_name: str | None = None
    price: float = Field(default=0, ge=0)
    status: Literal["created", "reused"]
    source_row_numbers: list[int] = Field(default_factory=list)


class ImportMaterialCreateResponse(BaseModel):
    created_count: int = 0
    reused_count: int = 0
    materials: list[ImportMaterialCreateResult] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    rows: list[ImportedSpecificationRow] = Field(default_factory=list)
    valid_count: int = 0
    error_count: int = 0
    missing_materials: list[MissingImportedMaterial] = Field(default_factory=list)


class WorkCorrectionImportWorkResult(BaseModel):
    work_id: int
    work_uuid: str | None = None
    work_code: str | None = None
    work_name: str
    row_count: int = 0
    specification_count: int = 0
    specification_review_status: WorkReviewStatus = "corrected"


class WorkCorrectionImportResponse(BaseModel):
    updated_work_count: int = 0
    updated_specification_count: int = 0
    works: list[WorkCorrectionImportWorkResult] = Field(default_factory=list)
