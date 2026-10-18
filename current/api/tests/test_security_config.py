from __future__ import annotations

from pathlib import Path

import pytest

from api.config import Settings
from api.security import verify_password


def test_production_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CTM_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "development-only")
    monkeypatch.setenv("SYNC_TOKEN", "")
    monkeypatch.setenv("ALLOW_SEED_DATA", "true")
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        Settings.from_env().validate_security()


def test_plaintext_passwords_are_rejected() -> None:
    assert verify_password("legacy-password", "legacy-password") is False


def test_runner_scripts_do_not_contain_password_fallbacks() -> None:
    runner = Path(__file__).resolve().parents[3] / "runner"
    scripts = [runner / name for name in ("deploy_prod.py", "push_db.py", "prod_service.py", "_analyze_dbs.py")]
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "PASS =" not in text
        assert "or PASS" not in text
