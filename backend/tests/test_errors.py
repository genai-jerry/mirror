from __future__ import annotations

from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import create_app
from app.settings import Settings


def _client_raising(exc: ApiError, settings: Settings) -> TestClient:
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return TestClient(app)


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
