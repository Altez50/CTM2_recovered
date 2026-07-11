from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ApiMessage(BaseModel):
    success: bool = True
    message: str


class ApiResponse(BaseModel):
    success: bool = True
    data: Any
    message: str | None = None
    pagination: Pagination | None = None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
