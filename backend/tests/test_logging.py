from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.logging_setup import configure_logging, log_event, set_request_id
from app.main import REQUEST_ID_HEADER, create_app
from app.settings import Settings


def _lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.strip().splitlines() if line.strip()]


def test_an_event_is_one_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    set_request_id("req-1")

    log_event("recognition.call", provider="sarvam-parse", job_id="j-9")

    (line,) = _lines(capsys.readouterr().out)
    assert line["event"] == "recognition.call"
    assert line["request_id"] == "req-1"
    assert line["provider"] == "sarvam-parse"
    assert line["job_id"] == "j-9"


def test_the_timestamp_is_utc(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()

    log_event("translation.cache_hit")

    (line,) = _lines(capsys.readouterr().out)
    assert line["timestamp"].endswith("+00:00")


def test_no_request_id_outside_a_request(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    set_request_id(None)

    log_event("service.started")

    (line,) = _lines(capsys.readouterr().out)
    assert line["request_id"] is None


def test_a_field_may_not_overwrite_the_request_id() -> None:
    configure_logging()

    with pytest.raises(ValueError, match="reserved keys"):
        log_event("recognition.call", request_id="not-the-real-one")


def test_a_field_may_not_overwrite_the_timestamp() -> None:
    configure_logging()

    with pytest.raises(ValueError, match="reserved keys"):
        log_event("recognition.call", timestamp="yesterday")


def test_configuring_twice_does_not_double_the_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    configure_logging()

    log_event("service.started")

    assert len(_lines(capsys.readouterr().out)) == 1


def test_an_event_logged_while_serving_carries_that_requests_id(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """ST-5, ST-6 and ST-8 read these lines per request, so the id must be the caller's."""
    app = create_app(settings)

    @app.get("/work")
    async def work() -> dict[str, bool]:
        log_event("recognition.call", provider="sarvam-parse", job_id="j-1")
        return {"ok": True}

    with TestClient(app) as test_client:
        capsys.readouterr()
        test_client.get("/work", headers={REQUEST_ID_HEADER: "req-work"})

    (line,) = _lines(capsys.readouterr().out)
    assert line["event"] == "recognition.call"
    assert line["request_id"] == "req-work"


def test_a_request_logs_its_own_id(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()

    client.get("/healthz", headers={"X-Request-Id": "req-health"})
    log_event("after.request")

    assert all(line["request_id"] != "req-health" for line in _lines(capsys.readouterr().out)), (
        "the request id must not leak into work done after the response"
    )
