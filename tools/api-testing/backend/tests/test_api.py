from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from apitest.config import Settings
from apitest.main import create_app


def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok", "version": "0.1.0", "auth_required": False}


def test_collection_request_crud(client: TestClient) -> None:
    col = client.post("/api/v1/collections", json={"name": " Shop ", "variables": [{"key": "k", "value": "v"}]})
    assert col.status_code == 201 and col.json()["name"] == "Shop"
    cid = col.json()["id"]

    first = client.post(f"/api/v1/collections/{cid}/requests", json={"name": "A", "url": "http://a.test"}).json()
    second = client.post(f"/api/v1/collections/{cid}/requests", json={"name": "B", "method": "POST"}).json()
    copy = client.post(f"/api/v1/requests/{first['id']}/duplicate").json()
    names = [r["name"] for r in client.get(f"/api/v1/collections/{cid}").json()["requests"]]
    assert names == ["A", "A (copy)", "B"]

    updated = client.put(f"/api/v1/requests/{second['id']}", json={**second, "name": "B2", "url": "http://b.test"})
    assert updated.json()["name"] == "B2" and updated.json()["url"] == "http://b.test"

    order = [second["id"], first["id"], copy["id"]]
    reordered = client.put(f"/api/v1/collections/{cid}/order", json={"request_ids": order}).json()
    assert [r["id"] for r in reordered["requests"]] == order
    assert client.put(f"/api/v1/collections/{cid}/order", json={"request_ids": [1]}).status_code == 422

    summary = client.get("/api/v1/collections").json()
    assert summary[0]["request_count"] == 3

    assert client.delete(f"/api/v1/requests/{copy['id']}").status_code == 204
    assert client.delete(f"/api/v1/collections/{cid}").status_code == 204
    assert client.get(f"/api/v1/requests/{first['id']}").status_code == 404


def test_validation_errors(client: TestClient) -> None:
    assert client.post("/api/v1/collections", json={"name": "  "}).status_code == 422
    assert client.post("/api/v1/collections/999/requests", json={"name": "x"}).status_code == 404
    bad_method = client.post("/api/v1/execute", json={"request": {"method": "TRACE", "url": "x"}})
    assert bad_method.status_code == 422


def test_export_hides_secrets_and_reimports(client: TestClient) -> None:
    cid = client.post(
        "/api/v1/collections",
        json={"name": "Exp", "variables": [{"key": "pw", "value": "hunter2", "secret": True}, {"key": "u", "value": "x"}]},
    ).json()["id"]
    client.post(f"/api/v1/collections/{cid}/requests", json={"name": "r", "url": "{{u}}"})
    exported = client.get(f"/api/v1/collections/{cid}/export")
    assert "attachment" in exported.headers["content-disposition"]
    doc = exported.json()
    assert {v["key"]: v["value"] for v in doc["variables"]} == {"pw": "", "u": "x"}
    imported = client.post("/api/v1/import", json={"content": json.dumps(doc), "name": "Copy"})
    assert imported.status_code == 201
    assert imported.json()["format"] == "native" and imported.json()["collection"]["name"] == "Copy"


def test_import_rejects_garbage(client: TestClient) -> None:
    response = client.post("/api/v1/import", json={"content": "not a spec"})
    assert response.status_code == 422 and "detect" in response.json()["detail"]


def test_execute_with_scoped_variables_and_redaction() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-api-key"]
        return httpx.Response(200, json={"ok": True})

    app = create_app(Settings(db_url="sqlite://", seed_demo=False), transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        cid = client.post(
            "/api/v1/collections", json={"name": "c", "variables": [{"key": "base", "value": "http://col.test"}]}
        ).json()["id"]
        eid = client.post(
            "/api/v1/environments",
            json={"name": "e", "variables": [{"key": "base", "value": "http://env.test"}, {"key": "key", "value": "top-secret", "secret": True}]},
        ).json()["id"]
        body = {
            "request": {
                "url": "{{base}}/{{path}}",
                "headers": [{"key": "X-Api-Key", "value": "{{key}}"}],
                "assertions": [{"source": "json", "property": "$.ok", "expected": "true"}],
            },
            "collection_id": cid,
            "environment_id": eid,
            "variables": {"path": "p"},
        }
        result = client.post("/api/v1/execute", json=body).json()
    assert result["passed"] is True
    assert seen == {"url": "http://env.test/p", "key": "top-secret"}
    assert ["X-Api-Key", "••••••"] in result["request"]["headers"]


def test_token_auth() -> None:
    app = create_app(Settings(db_url="sqlite://", seed_demo=False, token="t0ken"))
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/collections").status_code == 401
        assert client.get("/api/v1/collections", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get("/api/v1/collections", headers={"Authorization": "Bearer t0ken"}).status_code == 200


def test_sample_collection_runs_green_end_to_end(live_server: tuple[str, TestClient]) -> None:
    _base, client = live_server
    collection = next(c for c in client.get("/api/v1/collections").json() if "sample" in c["name"])
    env = next(e for e in client.get("/api/v1/environments").json() if e["name"] == "Local demo")

    run = client.post("/api/v1/runs", json={"collection_id": collection["id"], "environment_id": env["id"], "iterations": 2})
    assert run.status_code == 201, run.text
    detail = run.json()
    failures = [
        (s["request_name"], s["result"]["error"], [a["message"] for a in s["result"]["assertions"] if not a["passed"]])
        for s in detail["steps"]
        if not s["result"]["passed"]
    ]
    assert detail["status"] == "passed", failures
    assert detail["totals"]["requests"] == 14 and detail["totals"]["iterations"] == 2
    # The environment's secret password never appears in stored request bodies.
    assert "demo123" not in json.dumps(detail)

    runs = client.get(f"/api/v1/runs?collection_id={collection['id']}").json()
    assert runs[0]["id"] == detail["id"]
    junit = client.get(f"/api/v1/runs/{detail['id']}/report?format=junit")
    assert junit.status_code == 200 and "<testsuite" in junit.text and "<failure" not in junit.text
    html = client.get(f"/api/v1/runs/{detail['id']}/report?format=html")
    assert "PASSED" in html.text
    assert client.delete(f"/api/v1/runs/{detail['id']}").status_code == 204


def test_data_driven_run_reports_failures(live_server: tuple[str, TestClient]) -> None:
    base, client = live_server
    cid = client.post("/api/v1/collections", json={"name": "Logins"}).json()["id"]
    client.post(
        f"/api/v1/collections/{cid}/requests",
        json={
            "name": "login",
            "method": "POST",
            "url": f"{base}/demo/auth/login",
            "body": {"mode": "json", "content": '{"username": "{{user}}", "password": "{{pw}}"}'},
            "assertions": [{"source": "status", "expected": "{{expect}}"}],
        },
    )
    data = "user,pw,expect\ndemo,demo123,200\ndemo,wrong,200\n"
    detail = client.post("/api/v1/runs", json={"collection_id": cid, "data": data}).json()
    assert detail["status"] == "failed"
    assert [s["result"]["passed"] for s in detail["steps"]] == [True, False]
    assert "<failure" in client.get(f"/api/v1/runs/{detail['id']}/report?format=junit").text
    assert client.post("/api/v1/runs", json={"collection_id": cid, "data": "[1]"}).status_code == 422
