from __future__ import annotations

import hmac
import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.config import settings
from api.database import get_connection
from api.models.auth import UserInfo
from api.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
WORK_SPECIFICATION_REVIEW_FORM = "works"
WORK_SPECIFICATION_REVIEW_KEY = "use_specification_review"


def get_db() -> Generator[sqlite3.Connection, None, None]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def _revoke_session(connection: sqlite3.Connection, jti: str) -> None:
    connection.execute("UPDATE sessions SET revoked = 1 WHERE jti = ?", (jti,))
    connection.commit()


def read_user_bool_setting(
    connection: sqlite3.Connection,
    user_id: int,
    form_name: str,
    setting_key: str,
    default: bool = False,
) -> bool:
    row = connection.execute(
        """
        SELECT setting_value
        FROM user_settings
        WHERE user_id = ? AND form_name = ? AND setting_key = ?
        """,
        (user_id, form_name, setting_key),
    ).fetchone()
    if row is None:
        return default

    raw_value = row["setting_value"]
    if raw_value is None:
        return default

    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    return default


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UserInfo:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is missing session id")

    session_row = connection.execute(
        "SELECT user_id, last_activity, expires_at, revoked FROM sessions WHERE jti = ?",
        (jti,),
    ).fetchone()
    if session_row is None or session_row["revoked"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer valid")

    expires_at = datetime.fromisoformat(session_row["expires_at"])
    if expires_at < datetime.now(UTC):
        _revoke_session(connection, jti)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")

    last_activity = datetime.fromisoformat(session_row["last_activity"])
    idle_limit = timedelta(minutes=settings.inactivity_timeout_minutes)
    if last_activity + idle_limit < datetime.now(UTC):
        _revoke_session(connection, jti)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity")

    user_row = connection.execute(
        """
        SELECT
            u.id,
            u.uuid,
            u.username,
            u.role,
            u.is_active,
            p.id AS person_id,
            p.uuid AS person_uuid,
            p.full_name
        FROM users u
        LEFT JOIN persons p ON p.user_id = u.id
        WHERE u.id = ?
        """,
        (int(payload["sub"]),),
    ).fetchone()

    if user_row is None or not user_row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")

    connection.execute(
        "UPDATE sessions SET last_activity = ? WHERE jti = ?",
        (datetime.now(UTC).replace(microsecond=0).isoformat(), jti),
    )
    connection.commit()

    return UserInfo(
        id=user_row["id"],
        uuid=user_row["uuid"],
        username=user_row["username"],
        role=user_row["role"],
        is_active=bool(user_row["is_active"]),
        person_id=user_row["person_id"],
        person_uuid=user_row["person_uuid"],
        full_name=user_row["full_name"],
        use_specification_review=read_user_bool_setting(
            connection,
            int(user_row["id"]),
            WORK_SPECIFICATION_REVIEW_FORM,
            WORK_SPECIFICATION_REVIEW_KEY,
        ),
    )


def require_roles(*roles: str):
    def _dependency(current_user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return _dependency


def require_sync_token(
    x_sync_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Gate for peer-to-peer sync routes.

    When ``SYNC_TOKEN`` is configured (non-empty) on the server, every
    ``/api/sync/*`` request must present it either via the ``X-Sync-Token``
    header or as ``Authorization: Bearer <token>``. Comparison is constant-time.

    When ``SYNC_TOKEN`` is empty (the default, e.g. during development or when
    the web client uses the same routes under a logged-in user session), this
    dependency is a no-op and the routes behave exactly as before.
    """
    expected = settings.sync_token
    if not expected:
        return

    presented: str | None = x_sync_token
    if not presented and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            presented = value.strip()

    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing sync token",
        )
