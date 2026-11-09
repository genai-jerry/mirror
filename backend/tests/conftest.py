from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import DEFAULTS_DIR, Settings


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
