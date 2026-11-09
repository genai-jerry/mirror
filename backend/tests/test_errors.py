from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import REQUEST_ID_HEADER, create_app
from app.settings import Settings


def _client_raising(exc: Exception, settings: Settings, **client_args: bool) -> TestClient:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return TestClient(app, **client_args)


def _lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


def test_an_api_error_answers_in_the_one_shape(settings: Settings) -> None:
    client = _client_raising(
        ApiError(400, "unsupported_language", "source language fr-FR is not configured"),
        settings,
    )

    response = client.get("/boom")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "unsupported_language",
            "message": "source language fr-FR is not configured",
        }
    }


def test_an_api_error_may_carry_headers(settings: Settings) -> None:
    client = _client_raising(
        ApiError(429, "budget_exhausted", "Try again shortly.", headers={"Retry-After": "15"}),
        settings,
    )

    response = client.get("/boom")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "15"


def test_a_rejected_request_is_logged_against_its_request_id(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """ST-9 reads the request.rejected line, so it must name the request it rejected."""
    client = _client_raising(
        ApiError(
            400,
            "unsupported_language",
            "source language fr-FR is not configured",
            log_fields={"source_language": "fr-FR"},
        ),
        settings,
    )
    capsys.readouterr()

    client.get("/boom", headers={REQUEST_ID_HEADER: "req-9"})

    (line,) = _lines(capsys.readouterr().out)
    assert line["event"] == "request.rejected"
    assert line["request_id"] == "req-9"
    assert line["code"] == "unsupported_language"
    assert line["status"] == 400
    assert line["source_language"] == "fr-FR"


def test_an_unexpected_failure_answers_in_the_one_shape(settings: Settings) -> None:
    """A caller never sees a traceback — only the one shape, with a generic code."""
    client = _client_raising(
        RuntimeError("the provider refused token sk-not-for-the-caller"),
        settings,
        raise_server_exceptions=False,
    )

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "The backend could not answer this request.",
        }
    }
    assert "sk-not-for-the-caller" not in response.text
    assert "Traceback" not in response.text
