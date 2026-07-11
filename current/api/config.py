from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _derive_database_prefix(database_path: Path) -> str:
    raw_value = os.getenv("DATABASE_NUMBER_PREFIX")
    if raw_value:
        sanitized = "".join(char for char in raw_value.upper() if char.isalnum())
    else:
        sanitized = "".join(char for char in database_path.stem.upper() if char.isalnum())
    if len(sanitized) >= 2:
        return sanitized[:2]
    if len(sanitized) == 1:
        return f"{sanitized}X"
    return "CT"


@dataclass(slots=True)
class Settings:
    project_root: Path
    database_path: Path
    web_dist_path: Path
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_hours: int
    inactivity_timeout_minutes: int
    allow_seed_data: bool
    reset_database_on_schema_mismatch: bool
    cors_origins: list[str]
    database_number_prefix: str
    timesheet_number_total_length: int
    sync_token: str
    db_type: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = Path(__file__).resolve().parent.parent
        default_db = project_root / "construction.db"
        default_dist = project_root / "web-client" / "dist"
        database_path = Path(os.getenv("DATABASE_PATH", str(default_db))).resolve()
        return cls(
            project_root=project_root,
            database_path=database_path,
            web_dist_path=Path(os.getenv("WEB_DIST_PATH", str(default_dist))).resolve(),
            jwt_secret_key=os.getenv(
                "JWT_SECRET_KEY",
                "ctm-dev-secret-change-me-before-production",
            ),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            access_token_expire_hours=_parse_int("JWT_EXPIRE_HOURS", 8),
            inactivity_timeout_minutes=_parse_int("INACTIVITY_TIMEOUT_MINUTES", 30),
            allow_seed_data=_parse_bool("ALLOW_SEED_DATA", True),
            reset_database_on_schema_mismatch=_parse_bool("RESET_DATABASE_ON_SCHEMA_MISMATCH", False),
            cors_origins=_parse_csv(
                "CORS_ORIGINS",
                [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:8000",
                    "http://127.0.0.1:8000",
                ],
            ),
            database_number_prefix=_derive_database_prefix(database_path),
            timesheet_number_total_length=max(6, _parse_int("TIMESHEET_NUMBER_TOTAL_LENGTH", 12)),
            sync_token=os.getenv("SYNC_TOKEN", "").strip(),
            db_type=os.getenv("DB_TYPE", "sqlite").strip().lower(),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost").strip(),
            postgres_port=_parse_int("POSTGRES_PORT", 5432),
            postgres_db=os.getenv("POSTGRES_DB", "ctm").strip(),
            postgres_user=os.getenv("POSTGRES_USER", "ctm").strip(),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "").strip(),
        )


settings = Settings.from_env()
