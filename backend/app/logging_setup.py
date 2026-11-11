"""Structured logging: one JSON line per event on standard output.

Every line carries a UTC timestamp and the request id of the request that
produced it. The design's "Logged events" table is read by the system test
cases, so the shape here is part of the contract: `log_event("recognition.call",
provider="sarvam-parse")` writes one line whose `event` is that name and whose
remaining keys are the fields the table lists.

The Sarvam API key, the admin token and the app token are never passed to this
module; nothing here reads the environment.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

LOGGER_NAME = "mirror"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Keys the formatter writes itself; a caller's field may not collide with them.
_RESERVED = frozenset({"timestamp", "level", "event", "request_id", "message"})


def set_request_id(request_id: str | None) -> None:
    _request_id.set(request_id)


def get_request_id() -> str | None:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    """Render a record as one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", record.name),
            "request_id": getattr(record, "request_id", None),
        }
        message = record.getMessage()
        if message:
            line["message"] = message
        fields = getattr(record, "fields", None)
        if fields:
            line.update(fields)
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Point the app's logger at standard output, replacing any earlier handler.

    Called once per app creation, so repeated calls (every test that builds an
    app) leave exactly one handler rather than stacking them.
    """
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def log_event(event: str, *, level: int = logging.INFO, message: str = "", **fields: Any) -> None:
    """Write one structured line for a named event in the design's table."""
    collisions = _RESERVED.intersection(fields)
    if collisions:
        raise ValueError(f"log fields may not use reserved keys: {sorted(collisions)}")
    logging.getLogger(LOGGER_NAME).log(
        level,
        message,
        extra={"event": event, "request_id": get_request_id(), "fields": fields},
    )
