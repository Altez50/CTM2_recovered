from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.database import get_connection, initialize_database
from api.main import app


def _postgres_admin_connection():
    """Autocommit connection to the maintenance database for CREATE/DROP DATABASE."""
    import psycopg

    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
    )


def _create_postgres_database(db_name: str) -> None:
    with _postgres_admin_connection() as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{db_name}"')


def _drop_postgres_database(db_name: str) -> None:
    with _postgres_admin_connection() as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')


@pytest.fixture()
def database_path(tmp_path: Path) -> Iterator[Path]:
    """Fresh database per test.

    SQLite (default): a temp file per test. PostgreSQL (CTM_TEST_DB=postgresql):
    a temp database per test on the server configured via CTM_TEST_PG_* env vars,
    e.g. docker run -p 5433:5432 -e POSTGRES_USER=ctm -e POSTGRES_PASSWORD=ctm
    postgres:17. The role needs CREATEDB (the default POSTGRES_USER role has it).
    """
    settings.environment = "test"
    settings.allow_seed_data = True
    settings.sync_token = ""
    settings.reset_database_on_schema_mismatch = False

    if os.getenv("CTM_TEST_DB", "sqlite") == "postgresql":
        settings.db_type = "postgresql"
        settings.postgres_host = os.getenv("CTM_TEST_PG_HOST", "127.0.0.1")
        settings.postgres_port = int(os.getenv("CTM_TEST_PG_PORT", "5433"))
        settings.postgres_user = os.getenv("CTM_TEST_PG_USER", "ctm")
        settings.postgres_password = os.getenv("CTM_TEST_PG_PASSWORD", "ctm")
        db_name = f"ctm_test_{uuid.uuid4().hex[:10]}"
        _create_postgres_database(db_name)
        settings.postgres_db = db_name
        try:
            initialize_database()
            yield Path(db_name)
        finally:
            _drop_postgres_database(db_name)
        return

    settings.db_type = "sqlite"
    path = tmp_path / "ctm-test.db"
    settings.database_path = path
    initialize_database()
    yield path


@pytest.fixture()
def connection(database_path: Path) -> Iterator:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def client(database_path: Path) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def login_headers(client: TestClient, username: str = "admin", password: str = "admin") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    return login_headers(client)
