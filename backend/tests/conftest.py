from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import DEFAULTS_DIR, Settings

ADMIN_TOKEN = "admin-token-for-tests"
APP_TOKEN = "app-token-for-tests"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at an empty override directory and the shipped defaults."""
    return Settings(
        sarvam_api_key="test-key",
        admin_token=None,
        app_token=None,
        config_dir=tmp_path / "runtime-config",
        defaults_dir=DEFAULTS_DIR,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_settings(settings: Settings) -> Settings:
    """Settings with the admin configuration endpoints switched on."""
    return replace(settings, admin_token=ADMIN_TOKEN)


@pytest.fixture
def admin_client(admin_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(admin_settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}
