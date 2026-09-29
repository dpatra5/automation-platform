"""End-to-end limiter verification against the local demo server.

Rates are scaled down from the production examples so the suite is stable on 2-vCPU CI
runners with the server sharing the test process (set LT_IT_SERVER=process to isolate it).
The full-scale 1000 RPS check lives in ``test_accuracy_1000rps`` (``--run-slow``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lt.analyze import analyze_run
from lt.config import Config, parse_config
from lt.demo_server import DemoServerProcess, DemoSettings, ThreadedDemoServer
from lt.engine import run_load

pytestmark = pytest.mark.integration

StartServer = Callable[[DemoSettings], ThreadedDemoServer]


def config(base_url: str, profile: list[dict[str, Any]], **extra: Any) -> Config:
    data: dict[str, Any] = {
        "base_url": base_url,
        "safety": {"allowlist": ["127.0.0.1"], "max_rps_cap": 5000},
        "model": {"workers": 4, "profile": profile},
        "http": {"max_connections": 32, "warmup_requests": 16, "warmup_path": "/healthz"},
        "routes": [{"name": "items", "path": "/api/items"}],
    }
    for key, value in extra.items():
        data[key] = {**data.get(key, {}), **value} if isinstance(value, dict) else value
    return parse_config(data)


def run_and_analyze(cfg: Config, tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run_load(cfg, output_dir=tmp_path)
    assert result.summary["totals"]["errors"] == 0, result.summary
    # Guard against a saturated host smearing arrivals (would invalidate limiter checks).
    assert result.summary["latency_ms"]["p99"] < 500, result.summary["latency_ms"]
    return result.summary, analyze_run(result.run_dir)


def test_sustained_capacity(demo_server: StartServer, tmp_path: Path) -> None:
    srv = demo_server(DemoSettings(rate=100, burst=10))
    cfg = config(
        srv.base_url,
        [{"duration": "5s", "rate": 150}],
        analysis={"expected_limit_rps": 100, "tolerance": 0.05},
    )
    summary, a = run_and_analyze(cfg, tmp_path)
    s = a["sustained"]
    assert s["pass"], s
    # 429 rate matches the overflow (offered - limit).
    assert s["mean_429_rps"] == pytest.approx(s["expected_overflow_rps"], rel=0.10)
    assert abs(summary["scheduler"]["rate_error_pct"]) <= 2.0


def test_burst_inference(demo_server: StartServer, tmp_path: Path) -> None:
    srv = demo_server(DemoSettings(rate=50, burst=100))
    cfg = config(
        srv.base_url,
        [{"duration": "1s", "rate": 0}, {"duration": "4s", "rate": 200}],
        analysis={"expected_burst": 100, "burst_tolerance": 0.10},
    )
    _, a = run_and_analyze(cfg, tmp_path)
    b = a["burst"]
    assert b["triggered"] and b["pass"], b
    assert b["refill_rate_estimate"] == pytest.approx(50, rel=0.10)
    assert a["window_semantics"]["classification"] == "token-bucket"


def test_step_capacity_knee(demo_server: StartServer, tmp_path: Path) -> None:
    srv = demo_server(DemoSettings(rate=125, burst=10))
    profile = [{"duration": "2s", "rate": r} for r in (50, 100, 150, 200)]
    cfg = config(srv.base_url, profile, analysis={"expected_limit_rps": 125})
    _, a = run_and_analyze(cfg, tmp_path)
    st = a["step"]
    assert st["knee_point"] is not None and st["knee_point"]["asked"] == 150, st
    assert st["estimated_capacity_rps"] == pytest.approx(125, rel=0.10)


def test_fairness_two_keys_share_global_limit(demo_server: StartServer, tmp_path: Path) -> None:
    srv = demo_server(DemoSettings(rate=150, burst=10, scope="global"))
    cfg = config(
        srv.base_url,
        [{"duration": "4s", "rate": 250}],
        routes=[
            {"name": "a", "tenant": "key-a", "path": "/api/items", "headers": {"X-API-Key": "A"}},
            {"name": "b", "tenant": "key-b", "path": "/api/items", "headers": {"X-API-Key": "B"}},
        ],
        analysis={"fairness_threshold": 1.2},
    )
    _, a = run_and_analyze(cfg, tmp_path)
    f = a["fairness"]
    assert f["pass"] and f["fairness_ratio"] <= 1.2, f


@pytest.mark.parametrize("algo", ["fixed-window", "sliding-window"])
def test_window_semantics_classification(
    demo_server: StartServer, tmp_path: Path, algo: str
) -> None:
    # A fixed window whose boundary falls within 100 ms of traffic onset is physically
    # indistinguishable from a sliding log; retry once with a fresh (random) phase.
    for attempt in range(2):
        srv = demo_server(DemoSettings(rate=80, algo=algo))  # type: ignore[arg-type]
        cfg = config(srv.base_url, [{"duration": "6s", "rate": 160}])
        _, a = run_and_analyze(cfg, tmp_path / str(attempt))
        ws = a["window_semantics"]
        if ws["classification"] == algo:
            return
        if algo != "fixed-window" or ws["classification"] != "sliding-window":
            break
    pytest.fail(f"expected {algo}, got {ws}")


def test_multiprocess_sharding(demo_server: StartServer, tmp_path: Path) -> None:
    srv = demo_server(DemoSettings(rate=10_000, burst=10_000))
    cfg = config(
        srv.base_url,
        [{"duration": "2s", "rate": 100}],
        model={"workers": 4, "processes": 2},
        output={"events_sample_rate": 1.0},
    )
    result = run_load(cfg, output_dir=tmp_path)
    s = result.summary
    assert s["totals"]["attempted"] == 200 and s["totals"]["accepted"] == 200, s
    assert not result.interrupted
    events = list(result.run_dir.glob("events-p*.jsonl"))
    assert len(events) == 2
    assert sum(len(p.read_text().splitlines()) for p in events) == 200


@pytest.mark.slow
def test_accuracy_1000rps(tmp_path: Path) -> None:
    """Scheduler holds 1000 RPS within +/-2% per window; limiter verified within +/-5%."""
    with DemoServerProcess(DemoSettings(rate=800, burst=100)) as srv:
        cfg = config(
            srv.base_url,
            [{"duration": "10s", "rate": 1000}],
            model={"workers": 4, "processes": 2},
            http={"max_connections": 64},
            analysis={"expected_limit_rps": 800},
        )
        summary, a = run_and_analyze(cfg, tmp_path)
    assert summary["scheduler"]["mean_abs_window_error_pct"] <= 2.0
    assert a["sustained"]["pass"], a["sustained"]
    assert summary["latency_ms"]["p99"] < 250
