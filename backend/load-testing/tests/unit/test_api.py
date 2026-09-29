from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from lt.api import worker
from lt.api.app import create_app
from lt.api.settings import ApiSettings
from lt.cli import main as cli_main
from lt.demo_server import DemoSettings, ThreadedDemoServer

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def yaml_config(base_url: str = "http://127.0.0.1:9", rate: int = 50, duration: str = "1s") -> str:
    return f"""
version: 1
name: api-test
base_url: {base_url}
safety: {{ allowlist: [127.0.0.1], max_rps_cap: 5000 }}
model: {{ workers: 2, profile: [{{ duration: {duration}, rate: {rate} }}] }}
http: {{ max_connections: 8, concurrency: 32, read_timeout: 5s }}
routes:
  - {{ name: items, path: /api/items, headers: {{ Authorization: Bearer secret }} }}
"""


MakeClient = Callable[..., TestClient]


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[MakeClient]:
    clients: list[TestClient] = []

    def make(**overrides: object) -> TestClient:
        values: dict[str, object] = {"runs_dir": tmp_path / "runs", "examples_dir": EXAMPLES}
        values.update(overrides)
        client = TestClient(create_app(ApiSettings(**values)))  # type: ignore[arg-type]
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: MakeClient) -> TestClient:
    return make_client()


def fake_run(runs_dir: Path, run_id: str, *, summary: bool = True) -> Path:
    d = runs_dir / run_id
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"name": "fake", "base_url": "http://x"}))
    if summary:
        (d / "summary.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "name": "fake",
                    "base_url": "http://x",
                    "interrupted": False,
                    "duration_s": 2.0,
                    "totals": {"attempted": 10, "accepted": 8, "429": 2, "errors": 0},
                }
            )
        )
    (d / "metrics.csv").write_text(
        "second,attempted_rps,accepted_rps,429_rps,error_rps,p50_ms,p90_ms,p95_ms,p99_ms,dropped\n"
        "0,5,4,1,0,1.5,2,2.5,3,0\n1,5,4,1,0,,,,,0\n"
    )
    (d / "run.log").write_text(
        '{"msg": "run starting"}\nnot json\n'
        '{"msg": "progress", "second": 0, "attempted": 5, "accepted": 4, '
        '"rate_limited": 1, "errors": 0}\n'
    )
    return d


def test_health_is_public_and_reports_auth(make_client: MakeClient) -> None:
    client = make_client(token="t0ken")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["auth_required"] is True
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["cache-control"] == "no-store"


def test_token_required_when_configured(make_client: MakeClient) -> None:
    client = make_client(token="t0ken")
    assert client.get("/api/v1/runs").status_code == 401
    assert client.get("/api/v1/runs", headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.get("/api/v1/runs", headers={"Authorization": "Bearer t0ken"})
    assert ok.status_code == 200
    assert ok.json() == []


def test_examples_listed(client: TestClient) -> None:
    names = {e["name"] for e in client.get("/api/v1/examples").json()}
    assert "constant-1000rps" in names


def test_validate_ok_and_summary(client: TestClient) -> None:
    resp = client.post("/api/v1/configs/validate", json={"yaml": yaml_config()})
    body = resp.json()
    assert body["valid"] is True, body
    assert body["summary"]["peak_rps"] == 50
    assert body["summary"]["routes"][0]["name"] == "items"


def test_validate_applies_overrides(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/configs/validate",
        json={"yaml": yaml_config(), "overrides": {"rps": 20, "duration": "3s"}},
    )
    summary = resp.json()["summary"]
    assert summary["peak_rps"] == 20
    assert summary["duration_s"] == 3


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("base_url: [", "invalid YAML"),
        ("- 1", "mapping"),
        ("version: 1\nbase_url: http://127.0.0.1\n", "model"),
        (yaml_config().replace("Bearer secret", "${HOME}"), "environment variable"),
        (yaml_config(rate=6000), "exceeds max_rps_cap"),
    ],
)
def test_validate_errors(client: TestClient, text: str, fragment: str) -> None:
    body = client.post("/api/v1/configs/validate", json={"yaml": text}).json()
    assert body["valid"] is False
    assert any(fragment in e for e in body["errors"]), body["errors"]


def test_server_allowlist_enforced(make_client: MakeClient) -> None:
    client = make_client(allowed_hosts=["localhost"])
    body = client.post("/api/v1/configs/validate", json={"yaml": yaml_config()}).json()
    assert body["valid"] is False
    assert "not permitted by this server" in body["errors"][0]
    assert (
        make_client(allowed_hosts=["*"])
        .post("/api/v1/configs/validate", json={"yaml": yaml_config()})
        .json()["valid"]
    )


def test_server_rps_cap_enforced(make_client: MakeClient) -> None:
    client = make_client(max_rps_cap=10)
    body = client.post("/api/v1/configs/validate", json={"yaml": yaml_config()}).json()
    assert body["valid"] is False


def test_oversized_config_rejected(make_client: MakeClient) -> None:
    client = make_client(max_config_bytes=64)
    body = client.post("/api/v1/configs/validate", json={"yaml": yaml_config()}).json()
    assert "exceeds" in body["errors"][0]


def test_start_run_invalid_config_is_422(client: TestClient) -> None:
    resp = client.post("/api/v1/runs", json={"yaml": "- 1"})
    assert resp.status_code == 422
    assert "mapping" in resp.json()["detail"]


def test_run_listing_detail_and_timeseries(client: TestClient, tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    fake_run(runs, "20260101T000000Z-aaaaaa")
    fake_run(runs, "20260101T000001Z-bbbbbb", summary=False)
    listing = {r["run_id"]: r for r in client.get("/api/v1/runs").json()}
    assert listing["20260101T000000Z-aaaaaa"]["status"] == "completed"
    assert listing["20260101T000000Z-aaaaaa"]["totals"]["accepted"] == 8
    assert listing["20260101T000001Z-bbbbbb"]["status"] == "failed"

    detail = client.get("/api/v1/runs/20260101T000000Z-aaaaaa").json()
    assert detail["summary"]["name"] == "fake"
    assert {a["name"] for a in detail["artifacts"]} >= {"summary.json", "metrics.csv"}

    ts = client.get("/api/v1/runs/20260101T000000Z-aaaaaa/timeseries").json()
    assert ts["metrics"][0]["p99_ms"] == 3.0
    assert ts["metrics"][1]["p99_ms"] is None
    assert ts["live"] == [
        {"second": 0, "attempted": 5, "accepted": 4, "rate_limited": 1, "errors": 0}
    ]

    logs = client.get("/api/v1/runs/20260101T000000Z-aaaaaa/logs?tail=1").json()
    assert [r["msg"] for r in logs] == ["progress"]


def test_artifact_download_and_whitelist(client: TestClient, tmp_path: Path) -> None:
    run_dir = fake_run(tmp_path / "runs", "r1")
    (run_dir / "secret.txt").write_text("x")
    resp = client.get("/api/v1/runs/r1/artifacts/summary.json")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert client.get("/api/v1/runs/r1/artifacts/secret.txt").status_code == 404
    assert client.get("/api/v1/runs/r1/artifacts/analysis.json").status_code == 404


@pytest.mark.parametrize("run_id", ["..", ".staging", "a%2F..%2Fb", "-x", "nope"])
def test_unknown_or_unsafe_run_ids_404(client: TestClient, run_id: str) -> None:
    assert client.get(f"/api/v1/runs/{run_id}").status_code == 404


def test_delete_run(client: TestClient, tmp_path: Path) -> None:
    run_dir = fake_run(tmp_path / "runs", "r2")
    assert client.delete("/api/v1/runs/r2").status_code == 204
    assert not run_dir.exists()
    assert client.delete("/api/v1/runs/r2").status_code == 404


def test_stop_unknown_and_idle_runs(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/api/v1/runs/nope/stop").status_code == 404
    fake_run(tmp_path / "runs", "r3")
    assert client.post("/api/v1/runs/r3/stop").status_code == 409


def test_analyze_missing_artifacts_is_422(client: TestClient, tmp_path: Path) -> None:
    fake_run(tmp_path / "runs", "r4", summary=False)
    assert client.post("/api/v1/runs/r4/analyze", json={}).status_code == 422


def test_demo_server_state_when_stopped(client: TestClient) -> None:
    assert client.get("/api/v1/demo-server").json() == {
        "running": False,
        "base_url": None,
        "settings": None,
    }
    assert client.get("/api/v1/demo-server/stats").status_code == 409
    assert client.delete("/api/v1/demo-server").status_code == 204
    bad = client.post("/api/v1/demo-server", json={"window": "soon"})
    assert bad.status_code == 422


def test_spa_serving(make_client: MakeClient, tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    (tmp_path / "outside.txt").write_text("secret")
    client = make_client(static_dir=static)

    root = client.get("/")
    assert root.text == "<html>app</html>"
    assert "default-src 'self'" in root.headers["content-security-policy"]
    assert client.get("/runs/abc").text == "<html>app</html>"
    assert client.get("/favicon.svg").text == "<svg/>"
    asset = client.get("/assets/app.js")
    assert "immutable" in asset.headers["cache-control"]
    assert client.get("/..%2Foutside.txt").text == "<html>app</html>"
    assert client.get("/api/v1/unknown").status_code == 404


def test_spa_requires_index(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(ApiSettings(runs_dir=tmp_path / "runs", static_dir=tmp_path))


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LT_API_TOKEN", "abc")
    monkeypatch.setenv("LT_API_CORS_ORIGINS", "http://a, http://b")
    monkeypatch.setenv("LT_API_ALLOWED_HOSTS", "*")
    monkeypatch.setenv("LT_API_MAX_RPS_CAP", "999999")
    s = ApiSettings.from_env(runs_dir=tmp_path)
    assert s.token == "abc"
    assert s.cors_origins == ["http://a", "http://b"]
    assert s.any_host
    assert s.max_rps_cap == 100_000
    assert s.runs_dir == tmp_path


def test_cors_headers(make_client: MakeClient) -> None:
    client = make_client(cors_origins=["http://localhost:5173"])
    resp = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_worker_rejects_invalid_config_and_deletes_it(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text("- 1")
    code = worker.main(["--config", str(cfg), "--output-dir", str(tmp_path), "--run-id", "x"])
    assert code == worker.EXIT_INVALID
    assert not cfg.exists()


def test_serve_refuses_public_bind_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LT_API_TOKEN", raising=False)
    result = CliRunner().invoke(cli_main, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "LT_API_TOKEN" in result.output


def _wait_for(client: TestClient, run_id: str, timeout: float = 60) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail: dict[str, object] = client.get(f"/api/v1/runs/{run_id}").json()
        if detail["status"] not in ("running", "stopping"):
            return detail
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


@pytest.mark.integration
def test_run_lifecycle_end_to_end(client: TestClient) -> None:
    with ThreadedDemoServer(DemoSettings(rate=30, burst=5)) as srv:
        resp = client.post("/api/v1/runs", json={"yaml": yaml_config(srv.base_url, rate=50)})
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["run_id"]
        assert resp.json()["status"] == "running"
        conflict = client.post("/api/v1/runs", json={"yaml": yaml_config(srv.base_url)})
        assert conflict.status_code == 409
        detail = _wait_for(client, run_id)

    assert detail["status"] == "completed", detail
    summary = detail["summary"]
    assert isinstance(summary, dict)
    assert summary["totals"]["attempted"] == 50
    config = detail["config"]
    assert isinstance(config, dict)
    assert config["routes"][0]["headers"]["Authorization"] == "***REDACTED***"

    analysis = client.post(f"/api/v1/runs/{run_id}/analyze", json={"expected_limit_rps": 30})
    assert analysis.status_code == 200, analysis.text
    assert "sustained" in analysis.json()
    assert client.get(f"/api/v1/runs/{run_id}").json()["analysis"] is not None
    assert client.get(f"/api/v1/runs/{run_id}/timeseries").json()["metrics"]
    staging = Path(client.app.state.runs.runs_dir) / ".staging" / run_id  # type: ignore[attr-defined]
    assert not staging.exists()


@pytest.mark.integration
def test_run_graceful_stop(client: TestClient) -> None:
    with ThreadedDemoServer(DemoSettings(rate=1000)) as srv:
        resp = client.post(
            "/api/v1/runs", json={"yaml": yaml_config(srv.base_url, rate=20, duration="60s")}
        )
        run_id = resp.json()["run_id"]
        deadline = time.monotonic() + 30
        while not client.get(f"/api/v1/runs/{run_id}/timeseries").json()["live"]:
            assert time.monotonic() < deadline, "run never reported progress"
            time.sleep(0.2)
        stopped = client.post(f"/api/v1/runs/{run_id}/stop")
        assert stopped.status_code == 202
        assert stopped.json()["status"] == "stopping"
        detail = _wait_for(client, run_id)
    assert detail["status"] == "interrupted", detail


@pytest.mark.integration
def test_demo_server_lifecycle(client: TestClient) -> None:
    started = client.post("/api/v1/demo-server", json={"port": 0, "rate": 10})
    assert started.status_code == 201, started.text
    try:
        state = started.json()
        assert state["running"] is True
        assert state["settings"]["port"] != 0
        assert client.post("/api/v1/demo-server", json={"port": 0}).status_code == 409
        assert client.get("/api/v1/demo-server/stats").json() == {}
    finally:
        assert client.delete("/api/v1/demo-server").status_code == 204
    assert client.get("/api/v1/demo-server").json()["running"] is False
