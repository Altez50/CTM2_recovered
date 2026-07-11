from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    uuid: str | None = None
    username: str
    role: str
    is_active: bool
    person_id: int | None = None
    person_uuid: str | None = None
    full_name: str | None = None
    use_specification_review: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo
