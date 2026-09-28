from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from lt import cli
from lt.cli import main
from lt.demo_server import DemoSettings, ThreadedDemoServer

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def write_cfg(path: Path, base_url: str, **extra: object) -> Path:
    data = {
        "base_url": base_url,
        "safety": {"allowlist": ["127.0.0.1"], "max_rps_cap": 1000},
        "model": {"workers": 2, "profile": [{"duration": "2s", "rate": 60}]},
        "http": {"max_connections": 8},
        "routes": [{"name": "items", "path": "/api/items"}],
        "analysis": {"expected_limit_rps": 40},
        **extra,
    }
    path.write_text(yaml.safe_dump(data))
    return path


def test_version_and_help() -> None:
    runner = CliRunner()
    assert "lt, version" in runner.invoke(main, ["--version"]).output
    result = runner.invoke(main, ["--help"])
    for cmd in ("run", "validate", "analyze", "report", "demo-server"):
        assert cmd in result.output


def test_validate_ok_and_failures(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    ok = runner.invoke(main, ["validate", "-c", str(EXAMPLES / "constant-1000rps.yaml")])
    assert ok.exit_code == 0, ok.stderr
    assert "OK" in ok.output and "peak rate" in ok.output
    capped = runner.invoke(
        main, ["validate", "-c", str(EXAMPLES / "constant-1000rps.yaml"), "--max-rps-cap", "10"]
    )
    assert capped.exit_code == 2 and "exceeds max_rps_cap" in capped.stderr
    unsafe = write_cfg(tmp_path / "u.yaml", "https://prod.example.com")
    res = runner.invoke(main, ["validate", "-c", str(unsafe)])
    assert res.exit_code == 2 and "not in safety.allowlist" in res.stderr
    bad = tmp_path / "bad.yaml"
    bad.write_text("base_url: 1\n")
    res = runner.invoke(main, ["validate", "-c", str(bad)])
    assert res.exit_code == 2 and "invalid configuration" in res.stderr
    relaxed = write_cfg(
        tmp_path / "r.yaml", "http://127.0.0.1:1", safety={"require_allowlist": False}
    )
    res = runner.invoke(main, ["validate", "-c", str(relaxed)])
    assert res.exit_code == 0 and "warning" in res.stderr


def test_run_analyze_report_end_to_end(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    with ThreadedDemoServer(DemoSettings(rate=40, burst=5)) as srv:
        cfg = write_cfg(tmp_path / "c.yaml", srv.base_url)
        out = tmp_path / "runs"
        res = runner.invoke(
            main,
            ["--log-level", "WARNING", "run", "-c", str(cfg), "--output-dir", str(out),
             "--run-id", "cli", "--no-http2", "--connections", "4", "--concurrency", "8",
             "--events-sample-rate", "0.5"],
        )  # fmt: skip
        assert res.exit_code == 0, res.stderr + res.output
        assert "artifacts:" in res.output
        dup = runner.invoke(
            main, ["run", "-c", str(cfg), "--output-dir", str(out), "--run-id", "cli"]
        )
        assert dup.exit_code == 2 and "already exists" in dup.stderr
    run_dir = out / "cli"
    res = runner.invoke(main, ["analyze", str(run_dir)])
    assert res.exit_code == 0 and "sustained" in res.output
    res = runner.invoke(main, ["analyze", str(run_dir), "--json", "--expected-limit", "40"])
    assert json.loads(res.output)["sustained"]["target_rps"] == 40
    strict = runner.invoke(main, ["analyze", str(run_dir), "--strict", "--expected-limit", "5"])
    assert strict.exit_code == 1
    res = runner.invoke(main, ["report", str(run_dir)])
    assert res.exit_code == 0 and "p50=" in res.output and "analysis" in res.output
    res = runner.invoke(main, ["report", str(run_dir), "--json"])
    assert json.loads(res.output)["totals"]["attempted"] == 120


def test_run_rejects_unsafe_config(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    cfg = write_cfg(tmp_path / "c.yaml", "https://prod.example.com")
    res = runner.invoke(main, ["run", "-c", str(cfg), "--output-dir", str(tmp_path / "o")])
    assert res.exit_code == 2 and "safety check failed" in res.stderr
    res = runner.invoke(main, ["run", "-c", str(cfg), "--duration", "abc"])
    assert res.exit_code == 2
    res = runner.invoke(main, ["run", "-c", str(tmp_path / "missing.yaml")])
    assert res.exit_code == 2


def test_analyze_and_report_errors(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    res = runner.invoke(main, ["analyze", str(tmp_path)])
    assert res.exit_code == 2 and "missing" in res.stderr
    res = runner.invoke(main, ["report", str(tmp_path)])
    assert res.exit_code == 2 and "not found" in res.stderr


def test_demo_server_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(settings: DemoSettings, host: str, port: int) -> None:
        captured.update(settings=settings, host=host, port=port)

    monkeypatch.setattr("lt.demo_server.run_demo_server", fake_run)
    res = CliRunner(mix_stderr=False).invoke(
        main,
        ["demo-server", "--rate", "500", "--burst", "50", "--window", "2s", "--algo",
         "fixed-window", "--scope", "per-key", "--port", "9999"],
    )  # fmt: skip
    assert res.exit_code == 0, res.stderr
    settings = captured["settings"]
    assert isinstance(settings, DemoSettings)
    assert settings.window_s == 2 and settings.algo == "fixed-window" and settings.burst == 50
    assert captured["port"] == 9999
    assert cli.EXIT_INVALID == 2
