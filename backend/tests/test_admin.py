from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import ADMIN_TOKEN
from fastapi.testclient import TestClient

from app.config import load_config
from app.logging_setup import configure_logging
from app.main import create_app
from app.settings import Settings

LANGUAGES_WITH_TAMIL: dict[str, Any] = {
    "sources": [
        {
            "code": "ta-IN",
            "name": "Tamil",
            "recognition_provider": "sarvam-parse",
            "translation_provider": "sarvam-translate",
        }
    ],
    "targets": [{"code": "en-IN", "name": "English"}],
    "providers": {
        "sarvam-parse": {"kind": "sarvam_parse"},
        "sarvam-translate": {"kind": "sarvam_translate", "model": "mayura:v1"},
    },
}

LOW_BUDGET = {
    "recognition_per_minute": 2,
    "translation_per_minute": 60,
    "max_wait_seconds": 15,
}

EVERY_ENDPOINT = [
    pytest.param("PUT", "/v1/admin/config/languages", id="store languages"),
    pytest.param("PUT", "/v1/admin/config/budget", id="store budget"),
    pytest.param("DELETE", "/v1/admin/config/overrides", id="remove overrides"),
]


def _lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


# --- who may call it --------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), EVERY_ENDPOINT)
def test_without_an_admin_token_the_endpoints_do_not_exist(
    client: TestClient, method: str, path: str
) -> None:
    """ADMIN_TOKEN unset: an operator has not switched this surface on."""
    response = client.request(method, path, json={})

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "There is no such endpoint."}
    }


@pytest.mark.parametrize(("method", "path"), EVERY_ENDPOINT)
@pytest.mark.parametrize(
    "header",
    [
        pytest.param({}, id="no header"),
        pytest.param({"Authorization": "Bearer not-the-token"}, id="the wrong token"),
        pytest.param({"Authorization": ADMIN_TOKEN}, id="no scheme"),
        pytest.param({"Authorization": f"Basic {ADMIN_TOKEN}"}, id="the wrong scheme"),
    ],
)
def test_the_admin_token_is_required(
    admin_client: TestClient, method: str, path: str, header: dict[str, str]
) -> None:
    response = admin_client.request(method, path, headers=header, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), EVERY_ENDPOINT)
def test_a_token_with_a_character_outside_plain_ascii_is_refused(
    admin_settings: Settings, method: str, path: str
) -> None:
    """Review round 1: comparing it as text crashed, so the caller got a 500."""
    app = create_app(admin_settings)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(
            method,
            path,
            headers={"Authorization": "Bearer töken".encode("latin-1")},
            json={},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_a_refused_call_does_not_echo_the_admin_token(admin_client: TestClient) -> None:
    response = admin_client.delete(
        "/v1/admin/config/overrides", headers={"Authorization": "Bearer guess"}
    )

    assert ADMIN_TOKEN not in response.text


def test_the_admin_token_is_in_no_log_line(
    admin_client: TestClient, admin_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging()
    capsys.readouterr()

    admin_client.put("/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL)
    admin_client.delete("/v1/admin/config/overrides", headers={"Authorization": "Bearer guess"})

    assert ADMIN_TOKEN not in capsys.readouterr().out


# --- storing a languages file ----------------------------------------------


def test_a_stored_languages_file_changes_the_answer_with_no_restart(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """How the test data loader applies a DS-2 set to a running backend."""
    stored = admin_client.put(
        "/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL
    )

    assert stored.status_code == 200
    assert stored.json() == {"status": "stored", "name": "languages"}
    assert admin_client.get("/v1/languages").json() == {
        "sources": [{"code": "ta-IN", "name": "Tamil"}],
        "targets": [{"code": "en-IN", "name": "English"}],
    }


def test_storing_the_same_file_twice_leaves_the_same_configuration(
    admin_client: TestClient, admin_headers: dict[str, str], admin_settings: Settings
) -> None:
    """The loader may be run twice; the second run must not stack or duplicate."""
    first = admin_client.put(
        "/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL
    )
    after_first = (admin_settings.config_dir / "languages.json").read_text(encoding="utf-8")

    second = admin_client.put(
        "/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL
    )

    assert second.json() == first.json()
    assert (admin_settings.config_dir / "languages.json").read_text(encoding="utf-8") == after_first
    assert sorted(path.name for path in admin_settings.config_dir.iterdir()) == ["languages.json"]


def test_a_languages_file_the_service_cannot_use_is_not_stored(
    admin_client: TestClient, admin_headers: dict[str, str], admin_settings: Settings
) -> None:
    broken = {"sources": [{"code": "ta-IN", "name": "Tamil"}]}

    response = admin_client.put("/v1/admin/config/languages", headers=admin_headers, json=broken)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_configuration"
    assert "recognition_provider" in response.json()["error"]["message"]
    assert not (admin_settings.config_dir / "languages.json").exists()
    assert admin_client.get("/v1/languages").json()["sources"] == [
        {"code": "ml-IN", "name": "Malayalam"}
    ]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param("[1, 2]", "whole configuration file", id="a JSON list"),
        pytest.param('"languages"', "whole configuration file", id="a JSON string"),
        pytest.param("{not json", "not valid JSON", id="not JSON at all"),
        pytest.param("", "not valid JSON", id="an empty body"),
    ],
)
def test_a_body_that_is_not_a_configuration_file_is_refused_in_the_one_shape(
    admin_client: TestClient, admin_headers: dict[str, str], body: str, expected: str
) -> None:
    """Not FastAPI's validation shape — every error this service answers looks alike."""
    response = admin_client.put(
        "/v1/admin/config/languages",
        headers={**admin_headers, "Content-Type": "application/json"},
        content=body,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_configuration"
    assert expected in response.json()["error"]["message"]


def test_storing_a_file_is_logged_for_the_operator(
    admin_client: TestClient, admin_headers: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    # The app was built before this test began, so its handler holds the
    # standard output of that moment; point the logger at this test's.
    configure_logging()
    capsys.readouterr()

    admin_client.put("/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL)

    written = [
        line
        for line in _lines(capsys.readouterr().out)
        if line["event"] == "config.override_written"
    ]
    assert written and written[0]["name"] == "languages"


# --- storing a budget file -------------------------------------------------


def test_a_stored_budget_file_is_what_the_backend_reads(
    admin_client: TestClient, admin_headers: dict[str, str], admin_settings: Settings
) -> None:
    """How the loader applies DS-3's low recognition budget to a running backend."""
    response = admin_client.put("/v1/admin/config/budget", headers=admin_headers, json=LOW_BUDGET)

    assert response.json() == {"status": "stored", "name": "budget"}
    assert load_config("budget", admin_settings) == LOW_BUDGET


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {"recognition_per_minute": 2, "translation_per_minute": 60},
            "max_wait_seconds",
            id="a field left out of a whole file",
        ),
        pytest.param(
            {**LOW_BUDGET, "recognition_requests_per_minute": 2},
            "not part of the budget configuration",
            id="a field the budget does not have",
        ),
        pytest.param(
            {**LOW_BUDGET, "recognition_per_minute": "two"},
            "whole number of calls",
            id="a count that is not a number",
        ),
        pytest.param(
            {**LOW_BUDGET, "recognition_per_minute": 0},
            "at least 1",
            id="a count of nothing",
        ),
        pytest.param(
            {**LOW_BUDGET, "translation_per_minute": 2.5},
            "whole number of calls",
            id="a fraction of a call",
        ),
        pytest.param(
            {**LOW_BUDGET, "max_wait_seconds": -1},
            "0 or more",
            id="a wait of less than no time",
        ),
    ],
)
def test_a_budget_file_the_service_cannot_use_is_not_stored(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    admin_settings: Settings,
    payload: dict[str, Any],
    expected: str,
) -> None:
    response = admin_client.put("/v1/admin/config/budget", headers=admin_headers, json=payload)

    assert response.status_code == 400
    assert expected in response.json()["error"]["message"]
    assert not (admin_settings.config_dir / "budget.json").exists()
    assert load_config("budget", admin_settings)["recognition_per_minute"] == 60


# --- removing the overrides ------------------------------------------------


def test_removing_the_overrides_restores_the_shipped_configuration(
    admin_client: TestClient, admin_headers: dict[str, str], admin_settings: Settings
) -> None:
    admin_client.put("/v1/admin/config/languages", headers=admin_headers, json=LANGUAGES_WITH_TAMIL)
    admin_client.put("/v1/admin/config/budget", headers=admin_headers, json=LOW_BUDGET)

    response = admin_client.delete("/v1/admin/config/overrides", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "restored",
        "removed": ["budget.json", "languages.json"],
    }
    assert admin_client.get("/v1/languages").json()["sources"] == [
        {"code": "ml-IN", "name": "Malayalam"}
    ]
    assert load_config("budget", admin_settings)["recognition_per_minute"] == 60


def test_removing_the_overrides_twice_is_not_an_error(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.put("/v1/admin/config/budget", headers=admin_headers, json=LOW_BUDGET)
    admin_client.delete("/v1/admin/config/overrides", headers=admin_headers)

    second = admin_client.delete("/v1/admin/config/overrides", headers=admin_headers)

    assert second.status_code == 200
    assert second.json() == {"status": "restored", "removed": []}


def test_removing_the_overrides_leaves_a_file_the_service_does_not_own(
    admin_client: TestClient, admin_headers: dict[str, str], admin_settings: Settings
) -> None:
    """The override directory may be a mount an operator keeps other things in."""
    admin_settings.config_dir.mkdir(parents=True, exist_ok=True)
    theirs = admin_settings.config_dir / "notes.json"
    theirs.write_text("{}", encoding="utf-8")

    admin_client.delete("/v1/admin/config/overrides", headers=admin_headers)

    assert theirs.exists()
