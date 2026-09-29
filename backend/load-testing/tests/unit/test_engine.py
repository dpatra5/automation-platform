from __future__ import annotations

import asyncio
import json
import signal
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from lt.config import Config, SafetyError
from lt.engine import Runner, install_stop_handlers, redacted_config, run_load
from lt.http_client import build_client_pool
from lt.logging import REDACTED
from lt.metrics import MetricsCollector, read_csv


def ok_transport(status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"RateLimit-Remaining": "3"}, json={"ok": True})

    return httpx.MockTransport(handler)


def test_run_load_writes_all_artifacts(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = config_factory(
        default_headers={"Authorization": "Bearer top-secret"},
        routes=[{"name": "items", "path": "/api/items", "headers": {"X-API-Key": "k1"}}],
        model={"profile": [{"duration": "1s", "rate": 40}]},
        output={"events_sample_rate": 1.0},
    )
    result = run_load(cfg, output_dir=tmp_path, run_id="r1", transport=ok_transport())
    run_dir = tmp_path / "r1"
    assert result.run_dir == run_dir and not result.interrupted
    for name in ("metrics.csv", "metrics.json", "summary.json", "config.json", "routes.csv",
                 "fine.csv", "events.jsonl", "run.log"):  # fmt: skip
        assert (run_dir / name).is_file(), name
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["totals"]["attempted"] == 40 and summary["totals"]["accepted"] == 40
    assert summary["latency_ms"]["p50"] is not None
    rows = read_csv(run_dir / "metrics.csv")
    assert list(rows[0]) == [
        "second", "attempted_rps", "accepted_rps", "429_rps", "error_rps",
        "p50_ms", "p90_ms", "p95_ms", "p99_ms", "dropped", "failed_rps", "vus",
    ]  # fmt: skip
    assert float(rows[0]["attempted_rps"]) == 40
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["headers"]["ratelimit-remaining"]["count"] == 40
    assert metrics["scheduler"]["rate_error_pct"] == 0
    config_text = (run_dir / "config.json").read_text()
    assert "top-secret" not in config_text and "k1" not in config_text
    assert "top-secret" not in (run_dir / "run.log").read_text()
    assert len((run_dir / "events.jsonl").read_text().splitlines()) == 40
    with pytest.raises(FileExistsError):
        run_load(cfg, output_dir=tmp_path, run_id="r1", transport=ok_transport())


def test_run_load_refuses_unsafe_target(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = config_factory("https://prod.example.com")
    with pytest.raises(SafetyError):
        run_load(cfg, output_dir=tmp_path, transport=ok_transport())
    assert not any(tmp_path.iterdir())


def test_latency_is_measured_from_scheduled_time(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    """A 200 ms service with one worker must show queueing delay (coordinated omission)."""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(200)

    cfg = config_factory(
        model={"workers": 1, "profile": [{"duration": "1s", "rate": 10}]},
        http={"concurrency": 1, "max_connections": 1, "read_timeout": "30s"},
    )
    result = run_load(cfg, output_dir=tmp_path, transport=httpx.MockTransport(slow))
    lat = result.summary["latency_ms"]
    # Service time is 200 ms; the 10th request was scheduled at 0.9 s but finishes ~2.0 s.
    assert lat["max"] > 900
    assert lat["p50"] >= 200
    metrics = json.loads((result.run_dir / "metrics.json").read_text())
    assert metrics["latency_by_family_ms"]["2xx"]["count"] == 10


def test_errors_unexpected_status_and_weighted_routes(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/boom":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(500 if request.url.path == "/err" else 200)

    cfg = config_factory(
        model={"profile": [{"duration": "1s", "rate": 200}]},
        routes=[
            {"name": "ok", "path": "/ok", "weight": 2},
            {"name": "err", "path": "/err", "weight": 1, "expect_status": [200]},
            {"name": "boom", "path": "/boom", "weight": 1},
        ],
    )
    result = run_load(cfg, output_dir=tmp_path, transport=httpx.MockTransport(handler))
    metrics = json.loads((result.run_dir / "metrics.json").read_text())
    routes = metrics["routes"]
    assert sum(r["attempted"] for r in routes.values()) == 200
    assert routes["ok"]["attempted"] > routes["err"]["attempted"]
    assert routes["err"]["unexpected_status"] == routes["err"]["attempted"]
    assert metrics["error_types"]["ReadTimeout"] == routes["boom"]["attempted"]
    assert (
        result.summary["totals"]["errors"]
        == routes["err"]["attempted"] + routes["boom"]["attempted"]
    )


async def test_queue_overflow_is_counted_as_dropped(config_factory: Callable[..., Config]) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return httpx.Response(200)

    cfg = config_factory(
        model={"workers": 1, "profile": [{"duration": "0.5s", "rate": 100}]},
        http={"concurrency": 1, "max_connections": 1, "queue_size": 2, "read_timeout": "5s"},
    )
    collector = MetricsCollector()
    async with build_client_pool(cfg, httpx.MockTransport(slow)) as pool:
        runner = Runner(cfg, collector)
        runner.drain_timeout = 0.1
        stats = await runner.run(
            pool, start=time.perf_counter(), shard_ids=[0], n_shards=1, stop=asyncio.Event()
        )
    totals = collector.totals()
    assert totals["attempted"] == 50 == stats.fired
    assert totals["dropped"] > 40
    assert stats.cancelled >= 1  # in-flight request cancelled after the drain timeout


async def test_stop_event_interrupts_run(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(model={"profile": [{"duration": "30s", "rate": 20}]})
    collector = MetricsCollector()
    stop = asyncio.Event()
    async with build_client_pool(cfg, ok_transport()) as pool:
        runner = Runner(cfg, collector)
        loop = asyncio.get_running_loop()
        loop.call_later(0.3, stop.set)
        t0 = time.perf_counter()
        stats = await runner.run(pool, start=t0, shard_ids=[0, 1], n_shards=2, stop=stop)
    assert stats.interrupted and time.perf_counter() - t0 < 2
    assert 3 <= stats.fired <= 12


def test_stop_handlers_install_and_restore() -> None:
    before = signal.getsignal(signal.SIGINT)
    calls: list[int] = []
    restore = install_stop_handlers(lambda: calls.append(1))
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)
    handler(signal.SIGINT, None)  # type: ignore[operator]
    assert calls == [1]
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGINT, None)  # type: ignore[operator]
    restore()
    assert signal.getsignal(signal.SIGINT) == before


def test_redacted_config_strips_credentials(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(
        "http://user:pw@127.0.0.1:8080", default_headers={"Cookie": "c", "Accept": "x"}
    )
    data = redacted_config(cfg)
    assert data["base_url"] == "http://127.0.0.1:8080"
    assert data["default_headers"] == {"Cookie": REDACTED, "Accept": "x"}
