from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
import yaml
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from lt.api.app import create_app
from lt.api.settings import ApiSettings
from lt.cli import main as cli_main
from lt.config import parse_config
from lt.discover import DiscoveryOptions, LoadPlan, build_configs, discover

pytestmark = pytest.mark.integration

INDEX = """<!doctype html><html><body>
<a href="/page2">next</a> <a href="/logout">logout</a> <a href="/report.pdf">pdf</a>
<script>
fetch('/api/items');
fetch('/api/users/123');
fetch('/api/users/456');
fetch('/api/login', {method: 'POST', body: '{"user":"a","password":"b"}'});
fetch('/api/cart', {method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: '{"sku":1}'});
fetch('https://analytics.invalid/collect').catch(() => {});
</script></body></html>"""

PAGE2 = "<!doctype html><script>fetch('/api/orders?page=1')</script>"


class WebApp:
    def __init__(self) -> None:
        self.visited: list[str] = []
        self.auth_headers: list[str | None] = []
        app = FastAPI()

        @app.middleware("http")
        async def track(request, call_next):  # type: ignore[no-untyped-def]
            self.visited.append(request.url.path)
            self.auth_headers.append(request.headers.get("x-test-auth"))
            return await call_next(request)

        @app.get("/", response_class=HTMLResponse)
        def index() -> str:
            return INDEX

        @app.get("/page2", response_class=HTMLResponse)
        def page2() -> str:
            return PAGE2

        @app.get("/logout", response_class=HTMLResponse)
        def logout() -> str:
            return "bye"

        @app.api_route("/api/{path:path}", methods=["GET", "POST"])
        def api(path: str) -> dict[str, str]:
            return {"ok": path}

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        self.server = uvicorn.Server(
            uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off")
        )
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def webapp() -> Iterator[WebApp]:
    app = WebApp()
    yield app
    app.stop()


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception:
        return False
    return True


requires_browser = pytest.mark.skipif(
    not _chromium_available(), reason="Chromium not installed (playwright install chromium)"
)


@requires_browser
def test_discover_records_api_calls(webapp: WebApp) -> None:
    result = discover(DiscoveryOptions(url=webapp.url, wait_ms=300, headers={"X-Test-Auth": "tok"}))
    by_key = {(e.method, e.template): e for e in result.endpoints}
    assert ("GET", "/api/items") in by_key
    users = by_key[("GET", "/api/users/{id}")]
    assert users.count == 2
    assert by_key[("GET", "/api/orders")].path == "/api/orders?page=1"
    cart = by_key[("POST", "/api/cart")]
    assert cart.body == '{"sku":1}'
    assert not cart.safe
    login = by_key[("POST", "/api/login")]
    assert login.sensitive
    assert login.body is None
    assert "/logout" not in webapp.visited
    assert "/report.pdf" not in webapp.visited
    assert "analytics.invalid" in result.out_of_scope_hosts
    scoped = {e.base_url.startswith("https://analytics"): e.in_scope for e in result.endpoints}
    assert scoped == {True: False, False: True}
    assert "tok" in webapp.auth_headers
    assert len(result.pages) == 2


@requires_browser
def test_scan_api_discovers_and_runs_each_endpoint(tmp_path: Path, webapp: WebApp) -> None:
    app = create_app(ApiSettings(runs_dir=tmp_path / "runs"))
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/scans",
            json={
                "discovery": {"url": webapp.url, "wait_ms": 300, "max_depth": 0},
                "plan": {"rate": 20, "duration": "1s"},
            },
        )
        assert resp.status_code == 201, resp.text
        scan_id = resp.json()["id"]
        deadline = time.monotonic() + 120
        while True:
            scan = client.get(f"/api/v1/scans/{scan_id}").json()
            if scan["status"] not in ("discovering", "running"):
                break
            assert time.monotonic() < deadline, scan
            time.sleep(0.5)

        assert scan["status"] == "completed", scan
        templates = {i["name"] for i in scan["items"]}
        assert any("/api/items" in n for n in templates)
        assert any("/api/users/{id}" in n for n in templates)
        assert not any("cart" in n or "login" in n for n in templates)
        for item in scan["items"]:
            assert item["status"] == "completed", item
            assert item["accepted_rps"] == pytest.approx(20, rel=0.2)
        run_ids = {i["run_id"] for i in scan["items"]}
        listed = {r["run_id"] for r in client.get("/api/v1/runs").json()}
        assert run_ids <= listed
        assert client.get("/api/v1/scans").json()[0]["id"] == scan_id
        assert "X-Test-Auth" not in (tmp_path / "runs" / ".scans" / f"{scan_id}.json").read_text()


@requires_browser
def test_cli_discover_writes_configs(tmp_path: Path, webapp: WebApp) -> None:
    out = tmp_path / "scans"
    result = CliRunner().invoke(
        cli_main,
        [
            "discover", webapp.url, "--max-depth", "0", "--wait-ms", "300",
            "-H", "Authorization: Bearer s3cret", "--out-dir", str(out),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    files = sorted(out.glob("*.yaml"))
    assert len(files) == 2
    text = files[0].read_text()
    assert "s3cret" not in text
    assert "${LT_HEADER_AUTHORIZATION}" in text
    assert "LT_HEADER_AUTHORIZATION" in result.output


@requires_browser
def test_cli_scan_runs_every_endpoint(tmp_path: Path, webapp: WebApp) -> None:
    result = CliRunner().invoke(
        cli_main,
        [
            "scan", webapp.url, "--max-depth", "0", "--wait-ms", "300", "--mode", "combined",
            "--rate", "20", "--duration", "1s", "--output-dir", str(tmp_path), "--strict",
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "scan summary" in result.output
    assert "[   PASS    ]" in result.output
    assert len([d for d in tmp_path.iterdir() if (d / "summary.json").is_file()]) == 1


def test_build_configs_modes() -> None:
    from lt.discover import Endpoint

    eps = [
        Endpoint("a", "GET", "http://127.0.0.1:1", "/api/x?q=1", "/api/x", "fetch", True,
                 count=3, request_headers={"referer": "http://127.0.0.1/app"}),
        Endpoint("b", "POST", "http://127.0.0.1:1", "/api/y", "/api/y", "xhr", True, status=201,
                 request_headers={"content-type": "application/json"}, body='{"a":1}'),
    ]  # fmt: skip
    plan = LoadPlan(rate=5, duration="2s", warmup="1s", expected_limit_rps=4)
    per = build_configs(eps, plan, {"Authorization": "x"}, verify_tls=False)
    assert [ids for ids, _ in per] == [["a"], ["b"]]
    get_cfg = parse_config(per[0][1])
    assert get_cfg.routes[0].headers == {"referer": "http://127.0.0.1/app"}
    assert get_cfg.http.verify_tls is False
    cfg = parse_config(per[1][1])
    route = cfg.routes[0]
    assert route.body == '{"a":1}'
    assert route.headers == {"content-type": "application/json"}
    assert route.expect_status == [201, 429]
    assert cfg.default_headers["Authorization"] == "x"
    assert cfg.model.peak_rate == 5
    assert cfg.analysis.expected_limit_rps == 4
    assert [s.name for s in cfg.model.profile] == ["warmup", None]

    combined = build_configs(eps, LoadPlan(mode="combined", rate=5))
    assert len(combined) == 1
    ids, data = combined[0]
    assert ids == ["a", "b"]
    cfg = parse_config(data)
    assert [r.weight for r in cfg.routes] == [3.0, 1.0]
    yaml.safe_dump(data)
