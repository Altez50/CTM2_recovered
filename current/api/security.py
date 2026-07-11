from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from api.config import settings


password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("$pbkdf2-sha256$"):
        return password_context.verify(plain_password, password_hash)
    return plain_password == password_hash


def create_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
    person_id: int | None,
) -> tuple[str, str, datetime]:
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=settings.access_token_expire_hours)
    jti = str(uuid4())
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "person_id": person_id,
        "jti": jti,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc
