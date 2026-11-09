from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import REQUEST_ID_HEADER


def test_healthz_is_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_needs_no_token(client: TestClient) -> None:
    """The factory's health check sends no credential, so neither does this."""
    response = client.get("/healthz", headers={})

    assert response.status_code == 200


def test_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.headers[REQUEST_ID_HEADER]


def test_caller_request_id_is_kept(client: TestClient) -> None:
    response = client.get("/healthz", headers={REQUEST_ID_HEADER: "abc123"})

    assert response.headers[REQUEST_ID_HEADER] == "abc123"
