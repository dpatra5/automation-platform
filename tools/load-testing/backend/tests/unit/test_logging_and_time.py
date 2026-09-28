from __future__ import annotations

import asyncio
import io
import json
import logging
import sys

from lt.logging import REDACTED, JsonFormatter, get_logger, redact, setup_logging
from lt.utils.time import event_loop_factory, high_resolution_timers, new_run_id, utc_now_iso


def test_redact_nested_and_case_insensitive() -> None:
    data = {
        "Authorization": "Bearer x",
        "headers": {"x-api-key": "k", "Accept": "json"},
        "routes": [{"headers": {"Cookie": "c"}}, "plain"],
        "custom": "v",
    }
    out = redact(data, extra_keys=["Custom"])
    assert out["Authorization"] == REDACTED
    assert out["headers"] == {"x-api-key": REDACTED, "Accept": "json"}
    assert out["routes"][0]["headers"]["Cookie"] == REDACTED
    assert out["routes"][1] == "plain"
    assert out["custom"] == REDACTED
    assert data["Authorization"] == "Bearer x"  # input untouched


def test_json_formatter_redacts_extras() -> None:
    record = logging.LogRecord("lt.test", logging.INFO, __file__, 1, "hello %s", ("w",), None)
    record.headers = {"Authorization": "secret"}
    record.count = 3
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "hello w"
    assert payload["headers"]["Authorization"] == REDACTED
    assert payload["count"] == 3
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record.exc_info = sys.exc_info()
    assert "boom" in json.loads(JsonFormatter().format(record))["exc"]


def test_setup_logging_is_idempotent(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    setup_logging("INFO")
    logger = setup_logging("DEBUG", tmp_path / "x.log")
    assert len(logger.handlers) == 2
    get_logger("unit").info("msg", extra={"X-API-Key": "k"})
    line = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert line["logger"] == "lt.unit" and line["X-API-Key"] == REDACTED
    assert "msg" in (tmp_path / "x.log").read_text()
    setup_logging("WARNING")
    assert get_logger("lt.engine").name == "lt.engine"


def test_time_helpers() -> None:
    assert len(new_run_id()) > 16 and new_run_id() != new_run_id()
    assert "T" in utc_now_iso()
    with high_resolution_timers():
        loop = event_loop_factory(use_uvloop=False)()
        try:
            assert loop.run_until_complete(asyncio.sleep(0.001, result=7)) == 7
            assert loop.time() > 0
        finally:
            loop.close()
