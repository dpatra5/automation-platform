from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from lt.config import (
    Config,
    ConfigError,
    SafetyError,
    apply_overrides,
    check_safety,
    host_allowed,
    load_config,
    parse_config,
)
from lt.utils.time import format_duration, parse_duration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.name)
def test_examples_are_valid_and_safe(path: Path) -> None:
    cfg = load_config(path)
    report = check_safety(cfg)
    assert report.peak_rate <= report.effective_cap


def test_example_set_is_complete() -> None:
    names = {p.name for p in EXAMPLES.glob("*.yaml")}
    assert {
        "constant-1000rps.yaml",
        "step-to-10k.yaml",
        "burst-test.yaml",
        "fairness-two-keys.yaml",
    } <= names


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("500ms", 0.5), ("60s", 60), ("5m", 300), ("1h", 3600), ("2.5", 2.5), (3, 3.0), ("1S", 1)],
)
def test_parse_duration(value: str | int, seconds: float) -> None:
    assert parse_duration(value) == seconds


@pytest.mark.parametrize("value", ["", "abc", "10x", "-1s", True, -2])
def test_parse_duration_rejects(value: object) -> None:
    with pytest.raises(ValueError):
        parse_duration(value)  # type: ignore[arg-type]


def test_format_duration() -> None:
    assert format_duration(0.25) == "250ms"
    assert format_duration(60) == "60s"


def test_host_allowlist_matching() -> None:
    assert host_allowed("api.example.com", ["API.example.com"])
    assert host_allowed("a.b.example.com", ["*.example.com"])
    assert not host_allowed("example.com", ["*.example.com"])
    assert not host_allowed("evil-example.com", ["*.example.com"])
    assert not host_allowed("example.com.evil.io", ["example.com"])


def test_safety_rejects_host_not_allowlisted(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory("https://prod.example.com")
    with pytest.raises(SafetyError, match="not in safety.allowlist"):
        check_safety(cfg)


def test_safety_requires_non_empty_allowlist(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(safety={"allowlist": []})
    with pytest.raises(SafetyError, match="allowlist is empty"):
        check_safety(cfg)


def test_safety_can_be_relaxed_with_warning(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory("https://anything.test", safety={"require_allowlist": False})
    report = check_safety(cfg)
    assert report.warnings


def test_safety_enforces_cap(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(model={"profile": [{"duration": "1s", "rate": 6000}]})
    with pytest.raises(SafetyError, match="exceeds max_rps_cap"):
        check_safety(cfg)
    ok = config_factory()
    assert check_safety(ok).effective_cap == 5000
    with pytest.raises(SafetyError):
        check_safety(ok, cli_max_rps_cap=10)


def test_ramp_peak_counts_against_cap(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(model={"profile": [{"duration": "5s", "rate": 10, "end_rate": 9000}]})
    with pytest.raises(SafetyError):
        check_safety(cfg)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"routes": []}, "routes"),
        ({"base_url": "ftp://x"}, "base_url"),
        ({"base_url": "not a url"}, "base_url"),
        ({"model": {"profile": [{"duration": "0s", "rate": 1}]}}, "duration"),
        ({"model": {"profile": [{"duration": "1s", "rate": -1}]}}, "rate"),
        ({"model": {"profile": [{"duration": "1s", "rate": 0}]}}, "rate > 0"),
        ({"model": {"profile": []}}, "profile"),
        (
            {"model": {"workers": 1, "processes": 2, "profile": [{"duration": 1, "rate": 1}]}},
            "workers",
        ),
        ({"routes": [{"name": "x", "path": "http://evil.io/"}]}, "path"),
        ({"routes": [{"name": "x", "path": "//evil.io/"}]}, "path"),
        ({"routes": [{"name": "x", "path": "/a"}, {"name": "x", "path": "/b"}]}, "unique"),
        ({"routes": [{"name": "x", "path": "/a", "method": "TRACE"}]}, "method"),
        ({"unknown_key": 1}, "unknown_key"),
    ],
)
def test_invalid_configs_rejected(override: dict[str, object], message: str) -> None:
    data: dict[str, object] = {
        "base_url": "http://127.0.0.1:8080",
        "safety": {"allowlist": ["127.0.0.1"]},
        "model": {"profile": [{"duration": "1s", "rate": 10}]},
        "routes": [{"name": "r", "path": "/"}],
    }
    data.update(override)
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


def test_method_is_normalised(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(routes=[{"name": "p", "path": "/p", "method": "post", "body": {"a": 1}}])
    assert cfg.routes[0].method == "POST"
    assert cfg.routes[0].tenant_key == "p"


def test_env_expansion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LT_TEST_KEY", "s3cr3t")
    path = tmp_path / "c.yaml"
    path.write_text(
        "base_url: http://127.0.0.1:8080\n"
        "safety: {allowlist: [127.0.0.1]}\n"
        "default_headers: {X-API-Key: '${LT_TEST_KEY}', X-Other: '${LT_UNSET_VAR:-fallback}'}\n"
        "model: {profile: [{duration: 1s, rate: 1}]}\n"
        "routes: [{name: r, path: /}]\n"
    )
    cfg = load_config(path)
    assert cfg.default_headers == {"X-API-Key": "s3cr3t", "X-Other": "fallback"}
    path.write_text(path.read_text().replace("LT_UNSET_VAR:-fallback", "LT_UNSET_VAR"))
    with pytest.raises(ConfigError, match="LT_UNSET_VAR"):
        load_config(path)


def test_load_config_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(bad)
    bad.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(bad)


def test_overrides(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(
        model={"profile": [{"duration": "2s", "rate": 10}, {"duration": "3s", "rate": 20}]}
    )
    out = apply_overrides(
        cfg,
        rps=100,
        workers=8,
        processes=2,
        max_rps_cap=99999,
        http2=False,
        connections=4,
        streams=7,
        concurrency=9,
        events_sample_rate=0.5,
    )
    assert [(s.duration, s.rate) for s in out.model.profile] == [(5.0, 100.0)]
    assert out.model.workers == 8 and out.model.processes == 2
    assert out.safety.max_rps_cap == 5000  # CLI can only lower the cap
    assert not out.http.http2 and out.http.max_connections == 4 and out.http.max_streams == 7
    assert out.http.concurrency == 9 and out.output.events_sample_rate == 0.5
    lowered = apply_overrides(cfg, duration="1s", max_rps_cap=100, processes=4)
    assert lowered.model.profile[0].rate == 10 and lowered.model.profile[0].duration == 1
    assert lowered.safety.max_rps_cap == 100
    assert lowered.model.workers == 4
    with pytest.raises(ConfigError):
        apply_overrides(cfg, rps=-5)


def test_effective_concurrency_and_client_shards(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(http={"http2": False, "max_connections": 10, "concurrency": 100})
    assert cfg.http.effective_concurrency == 10
    assert cfg.http.effective_client_shards == 3
    h2 = config_factory(http={"max_connections": 2, "max_streams": 50, "concurrency": 1000})
    assert h2.http.effective_concurrency == 100
    pinned = config_factory(http={"max_connections": 4, "client_shards": 16})
    assert pinned.http.effective_client_shards == 4
    assert cfg.model.expected_events == 50
