from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.config import settings
from api.auth_dependencies import (
    WORK_SPECIFICATION_REVIEW_FORM,
    WORK_SPECIFICATION_REVIEW_KEY,
    get_current_user,
    get_db,
    read_user_bool_setting,
)
from api.models.auth import LoginRequest, LoginResponse, UserInfo
from api.models.common import ApiMessage
from api.security import create_access_token, decode_access_token, verify_password


router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> LoginResponse:
    row = connection.execute(
        """
        SELECT
            u.id,
            u.uuid,
            u.username,
            u.password_hash,
            u.role,
            u.is_active,
            p.id AS person_id,
            p.uuid AS person_uuid,
            p.full_name
        FROM users u
        LEFT JOIN persons p ON p.user_id = u.id
        WHERE u.username = ?
        """,
        (payload.username,),
    ).fetchone()
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    token, jti, expires_at = create_access_token(
        user_id=row["id"],
        username=row["username"],
        role=row["role"],
        person_id=row["person_id"],
    )
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    connection.execute(
        """
        INSERT INTO sessions (jti, user_id, last_activity, expires_at, revoked)
        VALUES (?, ?, ?, ?, 0)
        """,
        (jti, row["id"], now, expires_at.replace(microsecond=0).isoformat()),
    )
    connection.commit()

    return LoginResponse(
        access_token=token,
        expires_in=settings.access_token_expire_hours * 3600,
        user=UserInfo(
            id=row["id"],
            uuid=row["uuid"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            person_id=row["person_id"],
            person_uuid=row["person_uuid"],
            full_name=row["full_name"],
            use_specification_review=read_user_bool_setting(
                connection,
                int(row["id"]),
                WORK_SPECIFICATION_REVIEW_FORM,
                WORK_SPECIFICATION_REVIEW_KEY,
            ),
        ),
    )


@router.get("/me", response_model=UserInfo)
def me(current_user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
    return current_user


@router.post("/logout", response_model=ApiMessage)
def logout(
    token: Annotated[str, Depends(oauth2_scheme)],
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ApiMessage:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    jti = payload.get("jti")
    if jti:
        connection.execute("UPDATE sessions SET revoked = 1 WHERE jti = ?", (jti,))
        connection.commit()
    return ApiMessage(message="Logged out successfully")
