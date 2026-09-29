from __future__ import annotations

import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lt.analyze import AnalysisError, analyze_run, load_run, max_min_shares
from lt.config import Config
from lt.demo_server import DemoSettings, Limiter
from lt.engine import ArtifactWriter, RunInfo, redacted_config
from lt.metrics import MetricsCollector, write_json
from lt.report import format_analysis, format_summary, load_summary
from lt.scheduler import ArrivalSchedule


def simulate(
    tmp_path: Path,
    cfg: Config,
    settings: DemoSettings | None,
    *,
    phase: float = 0.0,
    key_of: Callable[[str], str] = lambda route: "global",
) -> Path:
    """Replay the arrival schedule through an in-memory limiter and write run artifacts."""
    schedule = ArrivalSchedule(cfg.model.profile)
    rng = random.Random(1)
    limiters: dict[str, Limiter] = {}
    collector = MetricsCollector()
    names = [r.name for r in cfg.routes]
    weights = [r.weight for r in cfg.routes]
    for _, offset in schedule.iter_offsets():
        route = rng.choices(names, weights)[0]
        collector.record_attempt(offset, route, 0.0)
        status = 200
        headers: dict[str, str] = {}
        if settings is not None:
            key = key_of(route)
            now = offset + phase
            limiter = limiters.setdefault(key, settings.make_limiter(now))
            d = limiter.acquire(now)
            status = 200 if d.allowed else 429
            headers = {"RateLimit-Reset": str(round(d.reset_s, 3))}
            if not d.allowed:
                headers["Retry-After"] = "1"
        collector.record_result(offset, route, status, 0.002, headers=headers)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_json(run_dir / "config.json", redacted_config(cfg))
    writer = ArtifactWriter(cfg, run_dir, "sim")
    writer.finalize(collector, RunInfo(started_at="t0", finished_at="t1"))
    return run_dir


def cfg_with(
    config_factory: Callable[..., Config], profile: list[dict[str, Any]], **kw: Any
) -> Config:
    return config_factory(model={"profile": profile}, safety={"max_rps_cap": 50_000}, **kw)


def test_sustained_pass_and_fail(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = cfg_with(
        config_factory,
        [{"duration": "6s", "rate": 300}],
        analysis={"expected_limit_rps": 200},
    )
    run_dir = simulate(tmp_path, cfg, DemoSettings(rate=200, burst=20))
    a = analyze_run(run_dir)
    s = a["sustained"]
    assert s["pass"] and s["mean_accepted_rps"] == pytest.approx(200, rel=0.02)
    assert s["mean_429_rps"] == pytest.approx(100, rel=0.05)
    assert s["expected_overflow_rps"] == 100
    failing = analyze_run(run_dir, {"expected_limit_rps": 250})
    assert not failing["sustained"]["pass"] and not failing["pass"]
    assert (run_dir / "analysis.json").is_file()


def test_burst_inference(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = cfg_with(
        config_factory,
        [{"duration": "2s", "rate": 0}, {"duration": "6s", "rate": 1000}],
        analysis={"expected_burst": 300},
    )
    run_dir = simulate(tmp_path, cfg, DemoSettings(rate=200, burst=300))
    a = analyze_run(run_dir)
    b = a["burst"]
    assert b["triggered"] and b["pass"], b
    assert b["inferred_burst_b"] == pytest.approx(300, rel=0.05)
    assert b["refill_rate_estimate"] == pytest.approx(200, rel=0.03)
    assert b["first_window_acceptances"] == pytest.approx(500, abs=3)
    ws = a["window_semantics"]
    assert ws["classification"] == "token-bucket", ws


def test_burst_not_triggered(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = cfg_with(config_factory, [{"duration": "3s", "rate": 50}])
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=500)))
    assert a["burst"]["triggered"] is False
    assert a["window_semantics"]["classification"] == "not-triggered"
    assert a["step"]["applicable"] is False
    assert a["fairness"]["applicable"] is False


def test_step_capacity_curve_and_knee(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    profile = [{"duration": "3s", "rate": r} for r in (100, 200, 300, 400, 500)]
    cfg = cfg_with(config_factory, profile, analysis={"expected_limit_rps": 250})
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=250, burst=10)))
    st = a["step"]
    assert [c["asked"] for c in st["capacity_curve"]] == [100, 200, 300, 400, 500]
    assert st["knee_point"]["asked"] == 300 and st["knee_point"]["reason"] == "429 onset"
    assert st["estimated_capacity_rps"] == pytest.approx(250, rel=0.03)
    assert st["pass"]


def test_step_knee_from_marginal_gain(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    profile = [{"duration": "3s", "rate": r} for r in (100, 200)]
    cfg = cfg_with(config_factory, profile, analysis={"knee_429_threshold": 0.5})
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=120, burst=5)))
    assert a["step"]["knee_point"]["reason"] == "marginal gain drop"


def test_step_limit_below_first_step(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    profile = [{"duration": "3s", "rate": r} for r in (200, 300)]
    cfg = cfg_with(config_factory, profile)
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=100, burst=5)))
    assert a["step"]["knee_point"]["asked"] == 200
    assert a["step"]["estimated_capacity_rps"] == pytest.approx(100, rel=0.05)


def two_tenant_cfg(config_factory: Callable[..., Config], weights: tuple[float, float]) -> Config:
    routes = [
        {"name": n, "tenant": f"key-{n}", "path": "/", "weight": w, "headers": {"X-API-Key": n}}
        for n, w in zip(("a", "b"), weights, strict=True)
    ]
    return cfg_with(config_factory, [{"duration": "5s", "rate": 600}], routes=routes)


def test_max_min_shares() -> None:
    assert max_min_shares({"a": 450, "b": 150}, 300) == {"a": 150, "b": 150}
    assert max_min_shares({"a": 450, "b": 50}, 300) == {"a": 250, "b": 50}


def test_fairness_global_limit_is_fair(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = two_tenant_cfg(config_factory, (1, 1))
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=300, burst=10)))
    f = a["fairness"]
    assert f["applicable"] and f["pass"], f
    assert f["fairness_ratio"] <= 1.2
    assert set(f["tenants"]) == {"key-a", "key-b"}


def test_fairness_per_key_limit_is_max_min_fair(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = two_tenant_cfg(config_factory, (3, 1))
    settings = DemoSettings(rate=100, burst=5, scope="per-key")
    a = analyze_run(simulate(tmp_path, cfg, settings, key_of=lambda route: route))
    f = a["fairness"]
    assert f["fairness_ratio"] == pytest.approx(1.0, abs=0.1)
    assert f["pass"], f


def test_fairness_proportional_global_limit_is_unfair(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = two_tenant_cfg(config_factory, (3, 1))
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=300, burst=10)))
    f = a["fairness"]
    # The heavy tenant receives ~3x the light one although both exceed the fair share.
    assert f["fair_share_ratio"] > 2 and not f["pass"]


@pytest.mark.parametrize("phase", [0.37, 0.8])
def test_semantics_fixed_window(
    tmp_path: Path, config_factory: Callable[..., Config], phase: float
) -> None:
    cfg = cfg_with(config_factory, [{"duration": "8s", "rate": 400}])
    a = analyze_run(
        simulate(tmp_path, cfg, DemoSettings(rate=200, algo="fixed-window"), phase=phase)
    )
    ws = a["window_semantics"]
    assert ws["classification"] == "fixed-window", ws
    assert ws["evidence"]["period_s"] == 1


def test_semantics_sliding_log(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = cfg_with(config_factory, [{"duration": "8s", "rate": 400}])
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=200, algo="sliding-window")))
    assert a["window_semantics"]["classification"] == "sliding-window"


def test_semantics_smooth_without_burst(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = cfg_with(config_factory, [{"duration": "8s", "rate": 400}])
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=200, burst=1)))
    ws = a["window_semantics"]
    assert ws["classification"] == "sliding-window" and ws["confidence"] == 0.5


def test_headers_section(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = cfg_with(config_factory, [{"duration": "3s", "rate": 300}])
    a = analyze_run(simulate(tmp_path, cfg, DemoSettings(rate=100, burst=5)))
    h = a["headers"]
    assert h["style"] == "ietf" and h["retry_after_on_429_ratio"] == 1.0
    assert h["headers"]["ratelimit-reset"]["count"] == 900


def test_report_formatting(tmp_path: Path, config_factory: Callable[..., Config]) -> None:
    cfg = two_tenant_cfg(config_factory, (1, 1))
    run_dir = simulate(tmp_path, cfg, DemoSettings(rate=300, burst=10))
    analysis = analyze_run(run_dir, {"expected_limit_rps": 300})
    summary, loaded = load_summary(run_dir)
    assert loaded == json.loads((run_dir / "analysis.json").read_text())
    text = format_summary(summary, analysis)
    for needle in ("attempted", "p99=", "sustained", "fairness", "semantics", "overall"):
        assert needle in text
    step_cfg = cfg_with(config_factory, [{"duration": "2s", "rate": r} for r in (100, 200)])
    step_root = tmp_path / "s"
    step_root.mkdir()
    step_dir = simulate(step_root, step_cfg, DemoSettings(rate=150, burst=5))
    assert "knee at" in format_analysis(analyze_run(step_dir))


def test_missing_artifacts(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="missing"):
        load_run(tmp_path)
