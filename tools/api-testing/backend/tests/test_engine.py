from __future__ import annotations

import json

import httpx
import pytest

from apitest import jsonpath
from apitest.assertions import ResponseView, evaluate, extract
from apitest.config import Settings
from apitest.executor import MASK, RequestBlocked, check_target, execute, prepare
from apitest.runner import PlanItem, parse_data, run_plan
from apitest.schemas import (
    Assertion,
    Auth,
    Body,
    Extraction,
    KeyValue,
    RequestSpec,
    ResponseData,
    Variable,
)
from apitest.variables import resolve, scope, unresolved


def _view(body: object = None, status: int = 200, headers: list[tuple[str, str]] | None = None) -> ResponseView:
    text = body if isinstance(body, str) else json.dumps(body)
    return ResponseView(
        ResponseData(status=status, headers=headers or [("Content-Type", "application/json")], body=text, elapsed_ms=120.5)
    )


# --- variables & JSON path ------------------------------------------------------


def test_resolve_nested_unknown_and_dynamic() -> None:
    variables = {"host": "api.test", "base": "https://{{host}}/v1"}
    assert resolve("{{base}}/users/{{ id }}", variables) == "https://api.test/v1/users/{{ id }}"
    assert len(resolve("{{$uuid}}", {})) == 36
    assert unresolved(resolve("{{base}}/{{missing}}", variables)) == ["missing"]


def test_resolve_self_reference_terminates() -> None:
    assert "{{a}}" in resolve("{{a}}", {"a": "x{{a}}"})


def test_scope_precedence_and_disabled() -> None:
    low = [Variable(key="a", value="1"), Variable(key="b", value="1")]
    high = [Variable(key="a", value="2"), Variable(key="b", value="2", enabled=False)]
    assert scope(low, high) == {"a": "2", "b": "1"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$.data.items[0].id", (True, 7)),
        ("data.items.0.id", (True, 7)),
        ("$.data.items[-1].name", (True, "last")),
        ("$['data']['odd key']", (True, True)),
        ("$.data.items.length", (True, 2)),
        ("$.data.missing", (False, None)),
        ("$.data.items[5]", (False, None)),
        ("$", (True, {"data": {"items": [{"id": 7}, {"name": "last"}], "odd key": True}})),
    ],
)
def test_jsonpath(path: str, expected: tuple[bool, object]) -> None:
    doc = {"data": {"items": [{"id": 7}, {"name": "last"}], "odd key": True}}
    assert jsonpath.get(doc, path) == expected


def test_jsonpath_invalid() -> None:
    with pytest.raises(ValueError):
        jsonpath.parse("$.a..b")


# --- assertions -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("assertion", "passed"),
    [
        (Assertion(source="status", expected="200"), True),
        (Assertion(source="status", expected="2xx"), True),
        (Assertion(source="status", operator="not_equals", expected="4xx"), True),
        (Assertion(source="response_time", operator="lt", expected="500"), True),
        (Assertion(source="response_time", operator="gt", expected="500"), False),
        (Assertion(source="header", property="content-type", operator="contains", expected="json"), True),
        (Assertion(source="header", property="x-missing", operator="not_exists"), True),
        (Assertion(source="json", property="$.id", expected="42"), True),
        (Assertion(source="json", property="$.id", expected="'42'"), False),
        (Assertion(source="json", property="$.active", expected="true"), True),
        (Assertion(source="json", property="$.active", expected="1"), False),
        (Assertion(source="json", property="$.name", expected="Ada"), True),
        (Assertion(source="json", property="$.tags", operator="contains", expected="admin"), True),
        (Assertion(source="json", property="$.tags.length", operator="gte", expected="2"), True),
        (Assertion(source="json", property="$.name", operator="matches", expected="^A.a$"), True),
        (Assertion(source="json", property="$.id", operator="type_is", expected="integer"), True),
        (Assertion(source="json", property="$.tags", operator="type_is", expected="object"), False),
        (Assertion(source="json", property="$.nope", operator="exists"), False),
        (Assertion(source="body", operator="contains", expected='"Ada"'), True),
        (Assertion(source="json", property="$.name", operator="lt", expected="3"), False),
    ],
)
def test_assertions(assertion: Assertion, passed: bool) -> None:
    view = _view({"id": 42, "name": "Ada", "active": True, "tags": ["admin", "dev"]})
    result = evaluate(assertion, view, {})
    assert result.passed is passed, result.message
    if not passed:
        assert result.message


def test_assertion_expected_uses_variables() -> None:
    result = evaluate(Assertion(source="json", property="$.id", expected="{{id}}"), _view({"id": 5}), {"id": "5"})
    assert result.passed


def test_json_schema_assertion() -> None:
    schema = json.dumps({"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}})
    good = evaluate(Assertion(source="json_schema", expected=schema), _view({"id": 1}), {})
    bad = evaluate(Assertion(source="json_schema", expected=schema), _view({"id": "x"}), {})
    invalid = evaluate(Assertion(source="json_schema", expected="{"), _view({"id": 1}), {})
    assert good.passed
    assert not bad.passed and bad.message.startswith("$.id:")
    assert not invalid.passed and "not valid JSON" in invalid.message


def test_non_json_body() -> None:
    result = evaluate(Assertion(source="json", property="$.a", operator="exists"), _view("<html>"), {})
    assert not result.passed and "not valid JSON" in result.message


def test_extractions() -> None:
    view = _view({"token": "abc", "user": {"id": 9}}, headers=[("X-Request-Id", "r-1")])
    assert extract(Extraction(variable="t", property="$.token"), view, {}).value == "abc"
    assert extract(Extraction(variable="u", property="$.user"), view, {}).value == '{"id": 9}'
    assert extract(Extraction(variable="h", source="header", property="x-request-id"), view, {}).value == "r-1"
    assert extract(Extraction(variable="r", source="regex", property=r'"id": (\d+)'), view, {}).value == "9"
    assert extract(Extraction(variable="s", source="status"), view, {}).value == "200"
    assert not extract(Extraction(variable="m", property="$.missing"), view, {}).ok


# --- executor -------------------------------------------------------------------


def test_prepare_resolves_everything() -> None:
    spec = RequestSpec(
        method="POST",
        url="{{base}}/items?x=1#frag",
        params=[KeyValue(key="q", value="{{term}}"), KeyValue(key="off", value="1", enabled=False)],
        headers=[KeyValue(key="X-Trace", value="{{trace}}")],
        body=Body(mode="json", content='{"t": "{{term}}"}'),
        auth=Auth(type="api_key", key="api_key", value="{{key}}", location="query"),
    )
    p = prepare(spec, {"base": "https://h.test", "term": "a b", "trace": "t1", "key": "k"})
    assert p.url == "https://h.test/items?x=1&q=a+b&api_key=k#frag"
    assert ("X-Trace", "t1") in p.headers
    assert ("Content-Type", "application/json") in p.headers
    assert p.body == '{"t": "a b"}'


def test_prepare_basic_and_form() -> None:
    spec = RequestSpec(
        method="POST",
        url="h.test/login",
        auth=Auth(type="basic", username="u", password="p"),
        body=Body(mode="form", form=[KeyValue(key="a", value="1 2")]),
    )
    p = prepare(spec, {})
    assert p.url == "http://h.test/login"
    assert ("Authorization", "Basic dTpw") in p.headers
    assert p.body == "a=1+2"


def test_host_allowlist() -> None:
    settings = Settings(allowed_hosts=["api.test", "*.corp.test"])
    check_target("https://api.test/x", settings)
    check_target("https://svc.corp.test/x", settings)
    with pytest.raises(RequestBlocked):
        check_target("https://evil.test/x", settings)
    with pytest.raises(RequestBlocked):
        check_target("file:///etc/passwd", settings)


def test_link_local_blocked_unless_listed() -> None:
    with pytest.raises(RequestBlocked):
        check_target("http://169.254.169.254/latest", Settings())
    check_target("http://169.254.169.254/latest", Settings(allowed_hosts=["169.254.169.254"]))


def _transport(handler):  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


def test_execute_success_extract_and_redact() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"id": 3, "token": "t-1"})

    spec = RequestSpec(
        url="https://api.test/me?key={{secret}}",
        auth=Auth(type="bearer", token="{{secret}}"),
        assertions=[Assertion(source="status", expected="200"), Assertion(source="json", property="$.id", expected="{{uid}}")],
        extractions=[Extraction(variable="uid", property="$.id")],
    )
    result = execute(spec, {"secret": "s3cr3t"}, Settings(), secrets=["s3cr3t"], transport=_transport(handler))
    assert result.passed, [a.message for a in result.assertions]
    assert seen["auth"] == "Bearer s3cr3t"
    assert result.extracted == {"uid": "3"}
    assert result.request.url == f"https://api.test/me?key={MASK}"
    assert ("Authorization", f"Bearer {MASK}") in result.request.headers


def test_execute_connection_error_fails_assertions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    spec = RequestSpec(url="{{base}}/x", assertions=[Assertion(source="status", expected="200")])
    result = execute(spec, {"base": "http://down.test"}, Settings(), transport=_transport(handler))
    assert not result.passed
    assert result.error and "could not connect" in result.error
    assert result.assertions[0].message == "no response"


def test_execute_reports_unresolved_variables() -> None:
    result = execute(RequestSpec(url="{{baseUrl}}/x"), {}, Settings(), transport=_transport(lambda r: httpx.Response(200)))
    assert not result.passed
    assert result.unresolved == ["baseUrl"]
    assert result.error and "baseUrl" in result.error


def test_execute_truncates_large_bodies() -> None:
    result = execute(
        RequestSpec(url="http://big.test"),
        {},
        Settings(max_response_bytes=10),
        transport=_transport(lambda r: httpx.Response(200, text="x" * 100)),
    )
    assert result.response is not None
    assert result.response.body_truncated and result.response.body == "x" * 10


# --- runner ---------------------------------------------------------------------


def test_parse_data_csv_and_json() -> None:
    assert parse_data("user,pw\nann,1\nbob,2\n", 10) == [{"user": "ann", "pw": "1"}, {"user": "bob", "pw": "2"}]
    assert parse_data('[{"n": 1}, {"n": "x"}]', 10) == [{"n": "1"}, {"n": "x"}]
    assert parse_data("  ", 10) == []
    with pytest.raises(ValueError):
        parse_data("a\n1\n2\n3", 2)
    with pytest.raises(ValueError):
        parse_data("[1, 2]", 10)


def test_run_plan_chains_and_iterates_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            return httpx.Response(200, json={"token": f"tok-{request.url.params['user']}"})
        ok = request.headers.get("authorization", "").startswith("Bearer tok-")
        return httpx.Response(200 if ok else 401)

    plan = [
        PlanItem(1, "login", RequestSpec(url="http://t.test/login", params=[KeyValue(key="user", value="{{user}}")],
                                         extractions=[Extraction(variable="token", property="$.token")])),
        PlanItem(2, "me", RequestSpec(url="http://t.test/me", auth=Auth(type="bearer", token="{{token}}"),
                                      assertions=[Assertion(source="status", expected="200")])),
    ]
    steps, totals, status = run_plan(
        plan, {}, Settings(), data_rows=[{"user": "a"}, {"user": "b"}], transport=_transport(handler)
    )
    assert status == "passed"
    assert (totals.iterations, totals.requests, totals.passed, totals.assertions_passed) == (2, 4, 4, 2)
    assert steps[2].result.extracted == {"token": "tok-b"}


def test_run_plan_stop_on_failure() -> None:
    plan = [
        PlanItem(1, "fails", RequestSpec(url="http://t.test/a", assertions=[Assertion(source="status", expected="201")])),
        PlanItem(2, "never", RequestSpec(url="http://t.test/b")),
    ]
    steps, totals, status = run_plan(
        plan, {}, Settings(), iterations=3, stop_on_failure=True, transport=_transport(lambda r: httpx.Response(200))
    )
    assert status == "failed"
    assert len(steps) == 1 and totals.failed == 1
