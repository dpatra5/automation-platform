"""API, demo-shop and real-HTTP coverage for virtual users, thresholds and JMX import."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from click.testing import CliRunner
from fastapi.testclient import TestClient

from lt.api.app import create_app
from lt.api.settings import ApiSettings
from lt.cli import EXIT_THRESHOLDS
from lt.cli import main as cli_main
from lt.config import load_config
from lt.demo_server import DemoSettings, ThreadedDemoServer
from lt.demo_server import create_app as create_demo_app
from lt.engine import run_load

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
FIXTURES = ROOT / "tests" / "fixtures"

VU_YAML = """
name: vu-api
base_url: http://127.0.0.1:9
safety: { allowlist: [127.0.0.1], max_rps_cap: 5000 }
model: { type: closed, users: 4, ramp_up: 2s, duration: 10s, think_time: 1s }
data: { csv: "user\\nann\\nbob\\n" }
routes:
  - name: login
    method: POST
    path: /login
    body: { user: "{{user}}" }
    extract: { token: "$.token" }
    assertions: { max_ms: 500 }
  - { name: items, path: /items, expect_status: [200] }
thresholds: { p95_ms: 300, routes: { login: { error_rate: 0 } } }
"""


def api(tmp_path: Path, **overrides: object) -> TestClient:
    values: dict[str, object] = {"runs_dir": tmp_path / "runs", "examples_dir": EXAMPLES}
    values.update(overrides)
    return TestClient(create_app(ApiSettings(**values)))  # type: ignore[arg-type]


def test_validate_closed_model_summary(tmp_path: Path) -> None:
    with api(tmp_path) as client:
        body = client.post("/api/v1/configs/validate", json={"yaml": VU_YAML}).json()
    assert body["valid"] is True, body
    s = body["summary"]
    assert s["model_type"] == "closed" and s["peak_users"] == 4 and s["duration_s"] == 12
    assert s["stages"] == [{"duration_s": 2, "users": 4}, {"duration_s": 10, "users": 4}]
    assert s["data_rows"] == 2 and s["thresholds"] == 2
    assert s["routes"][0]["extracts"] == ["token"] and s["routes"][0]["checks"] == 1
    assert s["routes"][1]["think_time"] == "1s"
    assert any("not shaped" in w for w in body["warnings"])


def test_api_guards_for_closed_model(tmp_path: Path) -> None:
    with api(tmp_path, max_rps_cap=50) as client:
        file_data = VU_YAML.replace('data: { csv: "user\\nann\\nbob\\n" }', "data: { file: /etc/passwd }")
        body = client.post("/api/v1/configs/validate", json={"yaml": file_data}).json()
        assert body["valid"] is False and "data.file is not allowed" in body["errors"][0]
        too_many = VU_YAML.replace("users: 4", "users: 5000")
        body = client.post("/api/v1/configs/validate", json={"yaml": too_many}).json()
        assert body["valid"] is False and "max_users_cap" in body["errors"][0]
        # The server-wide cap is written into the config so runtime pacing honours it.
        ok = client.post("/api/v1/configs/validate", json={"yaml": VU_YAML}).json()
        assert ok["summary"]["effective_cap"] == 50 and ok["summary"]["peak_rps"] == 50
        rps = client.post(
            "/api/v1/configs/validate", json={"yaml": VU_YAML, "overrides": {"rps": 10}}
        ).json()
        assert rps["valid"] is False and "open-model" in rps["errors"][0]


def test_import_jmx_endpoint(tmp_path: Path) -> None:
    jmx = (FIXTURES / "shop.jmx").read_text(encoding="utf-8")
    with api(tmp_path) as client:
        ok = client.post("/api/v1/configs/import/jmx", json={"jmx": jmx})
        assert ok.status_code == 200 and "type: closed" in ok.json()["yaml"]
        validated = client.post("/api/v1/configs/validate", json={"yaml": ok.json()["yaml"]})
        assert validated.json()["valid"] is True, validated.json()
        bad = client.post("/api/v1/configs/import/jmx", json={"jmx": "<nope/>"})
        assert bad.status_code == 422 and "JMeter" in bad.json()["detail"]


def test_examples_include_virtual_user_plans(tmp_path: Path) -> None:
    for name in ("vu-smoke.yaml", "vu-shop-journey.yaml", "vu-spike.yaml"):
        assert load_config(EXAMPLES / name).model.is_closed, name
    with api(tmp_path) as client:
        names = {e["name"] for e in client.get("/api/v1/examples").json()}
    assert {"vu-smoke", "vu-shop-journey", "vu-spike"} <= names


async def test_demo_shop_app_flow() -> None:
    app = create_demo_app(DemoSettings(rate=1))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://d") as c:
        assert (await c.post("/app/login", json={"username": "a", "password": "x"})).status_code == 401
        login = await c.post("/app/login", json={"username": "ann", "password": "demo"})
        token = login.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert (await c.get("/app/products")).status_code == 401
        found = (await c.get("/app/products?q=desk", headers=auth)).json()
        assert found["count"] == 3 and found["items"][0]["name"] == "Desk lamp"
        assert (await c.get("/app/products/2", headers=auth)).json()["in_stock"] is True
        assert (await c.get("/app/products/99", headers=auth)).status_code == 404
        cart = await c.post("/app/cart", json={"product_id": 2}, headers=auth)
        assert cart.status_code == 201 and cart.json() == {"items": 1, "user": "ann"}
        assert (await c.get("/app/profile")).json() == {"username": "ann"}  # session cookie
        # /app/* is never rate limited even though the limit is 1 request/second.
        for _ in range(3):
            assert (await c.get("/app/products", headers=auth)).status_code == 200


def test_shop_journey_against_real_demo_server(tmp_path: Path) -> None:
    cfg = load_config(EXAMPLES / "vu-shop-journey.yaml")
    with ThreadedDemoServer(DemoSettings(rate=10_000)) as server:
        data = cfg.model_dump(mode="python")
        data["base_url"] = server.base_url
        data["model"].update(
            stages=[{"duration": 0.5, "users": 4}, {"duration": 2, "users": 4}],
            think_time="50ms-100ms",
            max_rps=None,
        )
        cfg = cfg.model_validate(data)
        result = run_load(cfg, output_dir=tmp_path, run_id="shop")
    metrics = json.loads((tmp_path / "shop" / "metrics.json").read_text())
    rows = {r["label"]: r for r in metrics["aggregate"]}
    assert set(rows) == {"login", "profile (session cookie)", "search", "product detail",
                         "add to cart", "TOTAL"}  # fmt: skip
    assert rows["TOTAL"]["error_pct"] == 0, metrics["failures"]
    assert rows["add to cart"]["samples"] >= 4
    assert result.summary["thresholds"]["pass"] is True


def test_cli_import_jmx_and_threshold_exit_code(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "plan.yaml"
    imported = runner.invoke(cli_main, ["import-jmx", str(FIXTURES / "shop.jmx"), "-o", str(out)])
    assert imported.exit_code == 0, imported.output
    assert load_config(out).data is not None

    with ThreadedDemoServer(DemoSettings(rate=10_000)) as server:
        plan = tmp_path / "strict.yaml"
        plan.write_text(
            f"base_url: {server.base_url}\nsafety: {{allowlist: [127.0.0.1]}}\n"
            "model: {type: closed, users: 2, duration: 1s, iterations: 2}\n"
            "routes: [{name: health, path: /healthz}]\n"
            "thresholds: {min_rps: 100000}\n",
            encoding="utf-8",
        )
        ran = runner.invoke(cli_main, ["run", "-c", str(plan), "--output-dir", str(tmp_path / "r")])
    assert ran.exit_code == EXIT_THRESHOLDS, ran.output
    assert "aggregate report" in ran.output and "thresholds [FAIL]" in ran.output
