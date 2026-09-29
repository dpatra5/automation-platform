from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lt.api.app import create_app
from lt.api.scans import SCANS_DIR
from lt.api.settings import ApiSettings
from lt.discover import DiscoveryOptions, LoadPlan, default_scope, path_template


@pytest.mark.parametrize(
    ("path", "template"),
    [
        ("/api/users/123", "/api/users/{id}"),
        ("/api/users/123/orders/9f1c2a3b4d5e6f70", "/api/users/{id}/orders/{id}"),
        ("/v1/items/0b9e5f0e-1c2d-4e3f-8a9b-0c1d2e3f4a5b", "/v1/items/{id}"),
        ("/api/tokens/abcDEF1234567890ghijKL", "/api/tokens/{id}"),
        ("/api/v2/search", "/api/v2/search"),
        ("/", "/"),
    ],
)
def test_path_template(path: str, template: str) -> None:
    assert path_template(path) == template


@pytest.mark.parametrize(
    ("host", "scope"),
    [
        ("127.0.0.1", ["127.0.0.1"]),
        ("localhost", ["localhost"]),
        ("example.com", ["example.com", "*.example.com"]),
        ("app.example.com", ["app.example.com", "example.com", "*.example.com"]),
    ],
)
def test_default_scope(host: str, scope: list[str]) -> None:
    assert default_scope(host) == scope


def test_options_validation() -> None:
    with pytest.raises(ValueError, match="http"):
        DiscoveryOptions(url="ftp://x")
    assert DiscoveryOptions(url=" http://a.b.c/x ").host == "a.b.c"
    with pytest.raises(ValueError, match="duration"):
        LoadPlan(duration="0s")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(ApiSettings(runs_dir=tmp_path / "runs")))


def test_scan_url_must_pass_server_allowlist(client: TestClient) -> None:
    resp = client.post("/api/v1/scans", json={"discovery": {"url": "https://example.com"}})
    assert resp.status_code == 422
    assert "not permitted" in resp.json()["detail"]


def test_scan_not_found_and_listing(client: TestClient) -> None:
    assert client.get("/api/v1/scans").json() == []
    assert client.get("/api/v1/scans/scan-nope").status_code == 404
    assert client.get("/api/v1/scans/../x").status_code == 404
    assert client.post("/api/v1/scans/scan-nope/cancel").status_code == 404
    assert client.delete("/api/v1/scans/scan-nope").status_code == 404
    run = client.post("/api/v1/scans/scan-nope/run", json={"endpoint_ids": ["x"]})
    assert run.status_code == 404


def test_persisted_active_scan_is_marked_failed(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / SCANS_DIR).mkdir(parents=True)
    (runs / SCANS_DIR / "scan-1.json").write_text(
        '{"id": "scan-1", "url": "http://127.0.0.1/", "created_at": "2026-01-01T00:00:00Z",'
        ' "options": {"url": "http://127.0.0.1/"}, "status": "running", "result": null,'
        ' "plan": null, "items": [{"name": "a", "endpoint_ids": ["x"], "status": "pending"}]}'
    )
    client = TestClient(create_app(ApiSettings(runs_dir=runs)))
    scan = client.get("/api/v1/scans/scan-1").json()
    assert scan["status"] == "failed"
    assert "restart" in scan["error"]
    assert scan["items"][0]["status"] == "cancelled"
    assert client.post("/api/v1/scans/scan-1/cancel").status_code == 409
    assert client.post("/api/v1/scans/scan-1/run", json={"endpoint_ids": ["x"]}).status_code == 409
    assert client.delete("/api/v1/scans/scan-1").status_code == 204
    assert not (runs / SCANS_DIR / "scan-1.json").exists()
