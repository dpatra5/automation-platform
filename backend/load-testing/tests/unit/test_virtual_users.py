from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from lt.config import Config, ConfigError, load_config, parse_config
from lt.engine import run_load
from lt.metrics import MetricsCollector, read_csv
from lt.scenario import (
    Context,
    DataFeeder,
    Pacer,
    ResponseView,
    Template,
    check,
    extract,
    prepare_routes,
    safe_path,
)
from lt.thresholds import evaluate
from lt.utils import jsonpath
from lt.utils.time import parse_think_time

BASE: dict[str, Any] = {
    "base_url": "http://127.0.0.1:9",
    "safety": {"allowlist": ["127.0.0.1"], "max_rps_cap": 5000},
    "http": {"max_connections": 8, "read_timeout": "5s"},
}


def closed(**overrides: Any) -> Config:
    data: dict[str, Any] = {
        **BASE,
        "model": {"type": "closed", "users": 2, "duration": "1s"},
        "routes": [{"name": "items", "path": "/items"}],
    }
    data.update(overrides)
    return parse_config(data)


# -- config -------------------------------------------------------------------------------


def test_users_shorthand_expands_into_stages() -> None:
    m = closed(model={"type": "closed", "users": 10, "ramp_up": "10s", "duration": "20s",
                      "ramp_down": "5s"}).model  # fmt: skip
    assert [(s.duration, s.users) for s in m.stages] == [(10, 10), (20, 10), (5, 0)]
    assert m.users is None and m.total_duration == 35 and m.peak_users == 10
    # JMeter-style ramp: first user at t=0, all users by the end of ramp-up, then down to 0.
    assert [m.users_at(t) for t in (0, 0.5, 4.9, 9.99, 15, 32.5, 40)] == [0, 1, 5, 10, 10, 5, 0]
    assert closed(model={"type": "closed", "users": 3, "duration": "5s"}).model.users_at(0) == 3


@pytest.mark.parametrize(
    ("model", "fragment"),
    [
        ({"type": "closed", "users": 5}, "duration is required"),
        ({"type": "closed", "stages": [{"duration": "5s", "users": 0}]}, "users > 0"),
        ({"type": "closed", "users": 5, "duration": "5s", "stages": [{"duration": 1, "users": 1}]},
         "either users"),
        ({"type": "closed", "profile": [{"duration": 1, "rate": 5}]}, "profile is for"),
        ({"profile": [{"duration": 1, "rate": 5}], "users": 3}, "require model.type: closed"),
        ({"type": "closed", "users": 1, "duration": "5s", "think_time": "2s-1s"}, "low-high"),
    ],
)  # fmt: skip
def test_model_validation(model: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ConfigError, match=fragment):
        closed(model=model)


def test_route_and_threshold_validation() -> None:
    with pytest.raises(ConfigError, match="plain identifier"):
        closed(routes=[{"name": "a", "path": "/a", "extract": {"bad-name": "$.x"}}])
    with pytest.raises(ConfigError, match="must start with"):
        closed(routes=[{"name": "a", "path": "/a", "extract": {"x": "token"}}])
    with pytest.raises(ConfigError, match="unknown routes"):
        closed(thresholds={"routes": {"nope": {"p95_ms": 1}}})
    with pytest.raises(ConfigError, match="need model.type: closed"):
        parse_config({**BASE, "model": {"profile": [{"duration": 1, "rate": 5}]},
                      "routes": [{"name": "a", "path": "/a", "extract": {"x": "$.x"}}]})  # fmt: skip


def test_data_sources(tmp_path: Path) -> None:
    cfg = closed(data={"csv": "a;b\n1;2\n", "delimiter": ";"})
    assert cfg.data is not None and cfg.data.records() == [{"a": "1", "b": "2"}]
    headerless = closed(data={"csv": "x\ny\n", "columns": ["user"]})
    assert headerless.data is not None and headerless.data.records() == [{"user": "x"}, {"user": "y"}]
    with pytest.raises(ConfigError, match="exactly one"):
        closed(data={"csv": "a\n1", "rows": [{"a": 1}]})
    (tmp_path / "users.csv").write_text("name\nann\n", encoding="utf-8")
    (tmp_path / "plan.yaml").write_text(
        "base_url: http://127.0.0.1:9\nsafety: {allowlist: [127.0.0.1]}\n"
        "model: {type: closed, users: 1, duration: 1s}\n"
        "routes: [{name: a, path: /a}]\ndata: {file: users.csv}\n",
        encoding="utf-8",
    )
    loaded = load_config(tmp_path / "plan.yaml")
    assert loaded.data is not None and loaded.data.file is None
    assert loaded.data.records() == [{"name": "ann"}]


def test_think_time_parsing() -> None:
    assert parse_think_time("1s") == (1.0, 1.0)
    assert parse_think_time("500ms-2s") == (0.5, 2.0)
    assert parse_think_time(0) == (0.0, 0.0)


# -- templating, checks and extraction ---------------------------------------------------


def test_templates_and_builtins() -> None:
    ctx = Context({"id": "7"}, vu=3)
    ctx.iteration = 2
    assert Template("/items/{{id}}?u={{$vu}}&i={{ $iteration }}&x={{missing}}").render(ctx) == (
        "/items/7?u=3&i=2&x={{missing}}"
    )
    assert len(Template("{{$uuid}}").render(ctx)) == 36
    assert Template("{{$randomInt}}").render(ctx).isdigit()


def test_prepared_route_renders_json_body_with_escaping() -> None:
    cfg = closed(routes=[{"name": "login", "method": "POST", "path": "/u/{{id}}",
                          "headers": {"Authorization": "Bearer {{token}}"},
                          "body": {"name": "{{name}}", "n": 1}}])  # fmt: skip
    route = prepare_routes(cfg)[0]
    ctx = Context({"id": "9", "token": "t", "name": 'a "quoted" name'})
    path, headers, content = route.render(ctx)
    assert path == "/u/9" and headers["Authorization"] == "Bearer t"
    assert json.loads(content or b"") == {"name": 'a "quoted" name', "n": 1}
    static = prepare_routes(closed())[0]
    assert not static.templated and static.render(ctx)[0] == "/items"


def test_safe_path_blocks_absolute_urls() -> None:
    assert safe_path("/ok?x=1")
    assert not safe_path("//evil.test/x") and not safe_path("http://evil.test")
    assert not safe_path("evil")


def _route(**fields: Any):  # type: ignore[no-untyped-def]
    return prepare_routes(closed(routes=[{"name": "r", "path": "/r", **fields}]))[0]


def test_check_status_latency_body_and_json() -> None:
    ctx = Context({"who": "ann"})
    body = ResponseView(json.dumps({"user": "ann", "items": [{"id": 3}], "ok": True}).encode(), {})
    assert check(_route(), 200, 0.1, None, ctx) is None
    assert check(_route(), 404, 0.1, None, ctx) == "status 404"
    assert check(_route(), 429, 0.1, None, ctx) == "status 429"  # closed model: 429 fails
    assert check(_route(expect_status=[201]), 200, 0.1, None, ctx) == "unexpected status 200"
    assert "response time" in (check(_route(assertions={"max_ms": 50}), 200, 0.2, None, ctx) or "")
    passing = _route(assertions={"body_contains": ["{{who}}"], "body_not_contains": ["error"],
                                 "jsonpath": {"$.user": "{{who}}", "$.items[0].id": 3,
                                              "$.ok": True, "$.items.length": "*"}})  # fmt: skip
    assert check(passing, 200, 0.01, body, ctx) is None
    missing = _route(assertions={"jsonpath": {"$.nope": "*"}})
    assert check(missing, 200, 0.01, body, ctx) == "$.nope not found"
    wrong = _route(assertions={"jsonpath": {"$.user": "bob"}})
    assert check(wrong, 200, 0.01, body, ctx) == '$.user = ann, expected bob'


def test_extractors() -> None:
    route = _route(extract={"id": "$.items[0].id", "obj": "$.items[0]", "csrf": "regex:csrf='(\\w+)'",
                            "loc": "header:Location", "gone": "$.missing"})  # fmt: skip
    view = ResponseView(b'{"items":[{"id":3}],"html":"csrf=\'abc\'"}', {"location": "/next"})
    values, missing = extract(route, view)
    assert values == {"id": "3", "obj": '{"id": 3}', "csrf": "abc", "loc": "/next"}
    assert missing == ["gone"]


def test_jsonpath_helper() -> None:
    doc = {"a": {"b": [1, {"c d": 2}]}}
    assert jsonpath.get(doc, jsonpath.parse("$.a.b[1]['c d']")) == (True, 2)
    assert jsonpath.get(doc, jsonpath.parse("$.a.b.length")) == (True, 2)
    assert jsonpath.get(doc, jsonpath.parse("$.a.x")) == (False, None)


# -- data, pacing, thresholds ------------------------------------------------------------


def test_data_feeder_modes() -> None:
    rows = [{"n": str(i)} for i in range(5)]
    seq = DataFeeder(rows)
    assert [seq.next()["n"] for _ in range(7)] == ["0", "1", "2", "3", "4", "0", "1"]  # type: ignore[index]
    once = DataFeeder(rows[:2], recycle=False)
    assert [once.next(), once.next(), once.next()] == [rows[0], rows[1], None]
    part1 = DataFeeder(rows, part=1, parts=2, recycle=False)
    assert [part1.next(), part1.next(), part1.next()] == [rows[1], rows[3], None]
    assert DataFeeder([]).next() == {}
    assert DataFeeder(rows, mode="random", seed=1).next() in rows


async def test_pacer_caps_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(round(seconds, 3))

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    pacer = Pacer(10, clock=lambda: 0.0)
    for _ in range(3):
        await pacer.wait()
    assert slept == [0.1, 0.2]


def test_aggregate_rows_and_thresholds() -> None:
    c = MetricsCollector(apdex_ms=(100, 400))
    for latency in (0.05, 0.05, 0.2, 0.8):
        c.record_result(0.5, "a", 200, latency, failure=None, nbytes=1024)
    c.record_result(0.5, "b", 500, 0.01)
    c.record_result(0.5, "b", None, 0.0, error_type="ConnectError")
    rows = {r["label"]: r for r in c.aggregate_rows(2.0)}
    a, b, total = rows["a"], rows["b"], rows["TOTAL"]
    assert a["samples"] == 4 and a["error_pct"] == 0 and a["throughput_rps"] == 2.0
    assert a["apdex"] == 0.625  # (2 satisfied + 1 tolerating / 2) / 4
    assert a["received_kb_s"] == 2.0 and a["min_ms"] == pytest.approx(50, rel=0.01)
    assert b["error_pct"] == 100 and total["samples"] == 6
    assert c.failure_summary() == {"b": {"status 500": 1, "ConnectError": 1}}
    merged = MetricsCollector()
    merged.merge_state(c.to_state())
    assert merged.aggregate_rows(2.0) == c.aggregate_rows(2.0)

    cfg = closed(routes=[{"name": "a", "path": "/a"}, {"name": "b", "path": "/b"}],
                 thresholds={"p95_ms": 1000, "error_rate": 0.5, "min_apdex": 0.9,
                             "routes": {"b": {"error_rate": 0.0}}})  # fmt: skip
    result = evaluate(cfg.thresholds, c.aggregate_rows(2.0))
    verdicts = {(ch["scope"], ch["metric"]): ch["pass"] for ch in result["checks"]}
    assert result["pass"] is False
    assert verdicts == {("TOTAL", "p95_ms"): True, ("TOTAL", "error_rate"): True,
                        ("TOTAL", "min_apdex"): False, ("b", "error_rate"): False}  # fmt: skip
    assert evaluate(closed().thresholds, [])["pass"] is None


# -- closed-model runs ---------------------------------------------------------------------


def shop_transport(seen: dict[str, int]) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/login":
            user = json.loads(req.content)["user"]
            return httpx.Response(200, json={"token": f"t-{user}"},
                                  headers={"Set-Cookie": f"sid={user}; Path=/"})  # fmt: skip
        auth = req.headers.get("authorization", "")
        cookie = req.headers.get("cookie", "")
        if auth.startswith("Bearer t-"):
            seen["auth"] = seen.get("auth", 0) + 1
            # A shared cookie jar would pair one user's token with another user's session.
            if cookie != f"sid={auth.removeprefix('Bearer t-')}":
                seen["mismatch"] = seen.get("mismatch", 0) + 1
        if cookie.startswith("sid="):
            seen["cookie"] = seen.get("cookie", 0) + 1
        return httpx.Response(200, json={"items": [{"id": 7}]})

    return httpx.MockTransport(handler)


def test_closed_model_flow_end_to_end(tmp_path: Path) -> None:
    seen: dict[str, int] = {}
    cfg = closed(
        model={"type": "closed", "users": 3, "ramp_up": "300ms", "duration": "1s",
               "think_time": "20ms-40ms"},
        data={"csv": "user\nann\nbob\ncid\n"},
        routes=[
            {"name": "login", "method": "POST", "path": "/login", "body": {"user": "{{user}}"},
             "extract": {"token": "$.token"}, "assertions": {"jsonpath": {"$.token": "t-{{user}}"}}},
            {"name": "items", "path": "/items/{{$vu}}",
             "headers": {"Authorization": "Bearer {{token}}"}, "extract": {"first": "$.items[0].id"}},
            {"name": "detail", "path": "/items/{{first}}", "assertions": {"jsonpath": {"$.gone": "*"}}},
        ],
        thresholds={"p95_ms": 2000, "routes": {"detail": {"error_rate": 0}}},
        output={"events_sample_rate": 1.0},
    )  # fmt: skip
    result = run_load(cfg, output_dir=tmp_path, run_id="vu", transport=shop_transport(seen))
    run_dir = tmp_path / "vu"
    metrics = json.loads((run_dir / "metrics.json").read_text())
    rows = {r["label"]: r for r in metrics["aggregate"]}
    assert rows["login"]["error_pct"] == 0 and rows["items"]["error_pct"] == 0
    assert rows["detail"]["error_pct"] == 100
    assert rows["login"]["samples"] >= rows["items"]["samples"] >= 6
    assert metrics["failures"] == {"detail": {"$.gone not found": rows["detail"]["samples"]}}
    assert seen["auth"] == rows["items"]["samples"]
    assert seen.get("mismatch", 0) == 0  # every virtual user keeps its own cookie jar
    assert seen["cookie"] == rows["items"]["samples"] + rows["detail"]["samples"]
    assert metrics["model"]["type"] == "closed" and metrics["model"]["vus_peak"] == 3
    assert result.summary["thresholds"]["pass"] is False
    assert result.summary["aggregate_total"]["label"] == "TOTAL"
    assert max(int(r["vus"]) for r in read_csv(run_dir / "metrics.csv")) == 3
    assert (run_dir / "aggregate.csv").is_file()
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    assert {e["vu"] for e in events} == {1, 2, 3}


def test_iterations_stop_users_early(tmp_path: Path) -> None:
    cfg = closed(model={"type": "closed", "users": 2, "duration": "10s", "iterations": 3})
    ok = httpx.MockTransport(lambda r: httpx.Response(200))
    result = run_load(cfg, output_dir=tmp_path, run_id="it", transport=ok)
    assert result.summary["totals"]["attempted"] == 6
    assert result.summary["model"]["iterations_completed"] == 6
    assert result.summary["duration_s"] < 5  # finished early instead of holding 10s


def test_data_exhaustion_without_recycle(tmp_path: Path) -> None:
    cfg = closed(model={"type": "closed", "users": 2, "duration": "10s"},
                 data={"rows": [{"n": 1}, {"n": 2}, {"n": 3}], "recycle": False},
                 routes=[{"name": "r", "path": "/r/{{n}}"}])  # fmt: skip
    seen: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r.url.path)
        return httpx.Response(200)

    result = run_load(cfg, output_dir=tmp_path, run_id="d", transport=httpx.MockTransport(handler))
    assert sorted(seen) == ["/r/1", "/r/2", "/r/3"]
    assert result.summary["duration_s"] < 5


def test_max_rps_shapes_throughput(tmp_path: Path) -> None:
    cfg = closed(model={"type": "closed", "users": 5, "duration": "1s", "max_rps": 20})
    result = run_load(cfg, output_dir=tmp_path, run_id="p",
                      transport=httpx.MockTransport(lambda r: httpx.Response(200)))  # fmt: skip
    assert 15 <= result.summary["totals"]["attempted"] <= 25


def test_unsafe_rendered_path_is_blocked(tmp_path: Path) -> None:
    cfg = closed(variables={"next": "http://evil.test/steal"},
                 routes=[{"name": "r", "path": "/{{next}}"}, {"name": "s", "path": "/s"}],
                 model={"type": "closed", "users": 1, "duration": "1s", "iterations": 1})  # fmt: skip
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return httpx.Response(200)

    result = run_load(cfg, output_dir=tmp_path, run_id="u", transport=httpx.MockTransport(handler))
    assert calls == ["http://127.0.0.1:9/s"]
    assert result.summary["totals"]["errors"] == 1


def test_open_model_supports_templates_and_assertions(
    tmp_path: Path, config_factory: Callable[..., Config]
) -> None:
    cfg = config_factory(
        variables={"key": "k1"},
        data={"rows": [{"id": 1}, {"id": 2}]},
        routes=[{"name": "r", "path": "/r/{{id}}", "headers": {"X-Key": "{{key}}"},
                 "assertions": {"body_contains": ["ok"]}}],
        model={"profile": [{"duration": "1s", "rate": 20}]},
    )  # fmt: skip
    paths: set[str] = set()

    def handler(r: httpx.Request) -> httpx.Response:
        paths.add(r.url.path)
        assert r.headers["x-key"] == "k1"
        return httpx.Response(200, text="ok" if r.url.path == "/r/1" else "nope")

    run_load(cfg, output_dir=tmp_path, run_id="o", transport=httpx.MockTransport(handler))
    metrics = json.loads((tmp_path / "o" / "metrics.json").read_text())
    assert paths == {"/r/1", "/r/2"}
    assert metrics["aggregate"][0]["error_pct"] == 50
    assert metrics["model"] == {"type": "open", "peak_rps": 20}
