from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import DEFAULTS_DIR, Settings

ADMIN_TOKEN = "admin-token-for-tests"
APP_TOKEN = "app-token-for-tests"

#: `backend/scripts/` holds the system test data loader, which is a command a
#: person runs rather than part of the service's package. Putting it on the
#: import path here lets its tests import it like any other module.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


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
