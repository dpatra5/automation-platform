"""Structured JSON logging with sensitive-field redaction."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REDACTED = "***REDACTED***"

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "api-key",
        "apikey",
        "cookie",
        "set-cookie",
        "x-auth-token",
        "x-amz-security-token",
        "password",
        "client_secret",
    }
)

_RESERVED_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys() | {"message", "asctime"}
)


def is_sensitive(key: str, extra_keys: Iterable[str] = ()) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or lowered in {k.lower() for k in extra_keys}


def redact(value: Any, extra_keys: Iterable[str] = ()) -> Any:
    """Return a deep copy of ``value`` with sensitive mapping keys replaced by a marker."""
    extra = tuple(extra_keys)
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if isinstance(k, str) and is_sensitive(k, extra) else redact(v, extra))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v, extra) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line; ``extra=`` fields are merged in after redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED_ATTRS}
        payload.update(redact(extras))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("lt")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level.upper())
    logger.propagate = False
    formatter = JsonFormatter()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("lt") else f"lt.{name}")
