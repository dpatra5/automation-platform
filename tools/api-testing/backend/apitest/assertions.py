"""Declarative assertions and variable extraction against a response."""

from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import exceptions as schema_exceptions
from jsonschema import validators

from apitest import jsonpath
from apitest.schemas import Assertion, AssertionResult, Extraction, ExtractionResult, ResponseData
from apitest.variables import resolve

_NOT_JSON = object()
_STATUS_CLASS = re.compile(r"[1-5]xx")


class ResponseView:
    """A response with its JSON body parsed at most once."""

    def __init__(self, response: ResponseData) -> None:
        self.response = response
        self._parsed: Any = None
        self._done = False

    def json(self) -> Any:
        if not self._done:
            self._done = True
            body = self.response.body
            try:
                self._parsed = json.loads(body) if body.strip() else _NOT_JSON
            except ValueError:
                self._parsed = _NOT_JSON
        return self._parsed

    def header(self, name: str) -> str | None:
        wanted = name.strip().lower()
        values = [v for k, v in self.response.headers if k.lower() == wanted]
        return ", ".join(values) if values else None


def display(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 300 else text[:297] + "..."


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _coerce(expected: str, actual: Any) -> Any:
    if isinstance(actual, str):
        return expected
    try:
        return json.loads(expected)
    except ValueError:
        return expected


def values_equal(actual: Any, expected: str) -> bool:
    exp = _coerce(expected, actual)
    if isinstance(actual, bool) or isinstance(exp, bool):
        return isinstance(actual, bool) and isinstance(exp, bool) and actual is exp
    if isinstance(actual, (int, float)) and isinstance(exp, (int, float)):
        return float(actual) == float(exp)
    return bool(actual == exp)


def _contains(actual: Any, expected: str) -> bool:
    if isinstance(actual, list):
        return any(values_equal(item, expected) for item in actual)
    if isinstance(actual, dict):
        return expected in actual
    if isinstance(actual, str):
        return expected in actual
    return expected in display(actual)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} value {value!r} is not a number")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        raise ValueError(f"{label} value {display(value)!r} is not a number") from None


def _actual(a: Assertion, view: ResponseView) -> tuple[bool, Any, str]:
    r = view.response
    if a.source == "status":
        return True, r.status, ""
    if a.source == "response_time":
        return True, round(r.elapsed_ms, 2), ""
    if a.source == "body":
        return True, r.body, ""
    if a.source == "header":
        value = view.header(a.property)
        return value is not None, value, f"header {a.property!r} is not present"
    data = view.json()
    if data is _NOT_JSON:
        return False, None, "response body is not valid JSON"
    found, value = jsonpath.get(data, a.property or "$")
    return found, value, f"JSON path {a.property or '$'!r} not found"


_SYMBOLS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


def _compare(a: Assertion, found: bool, actual: Any, missing: str) -> AssertionResult:
    op, exp = a.operator, a.expected
    shown = display(actual) if found else None

    def result(ok: bool, message: str = "") -> AssertionResult:
        return AssertionResult(assertion=a, passed=ok, actual=shown, message="" if ok else message)

    if op == "exists":
        return result(found, missing)
    if op == "not_exists":
        return result(not found, f"expected it to be absent, got {shown}")
    if not found:
        return result(False, missing)

    if op in ("equals", "not_equals"):
        if a.source == "status" and _STATUS_CLASS.fullmatch(exp.strip().lower()):
            same = str(actual)[:1] == exp.strip()[:1]
        else:
            same = values_equal(actual, exp)
        ok = same if op == "equals" else not same
        return result(ok, f"expected {'not ' if op == 'not_equals' else ''}{exp!r}, got {shown}")
    if op in ("contains", "not_contains"):
        has = _contains(actual, exp)
        ok = has if op == "contains" else not has
        return result(ok, f"expected {shown} {'not ' if op == 'not_contains' else ''}to contain {exp!r}")
    if op in _SYMBOLS:
        left, right = _number(actual, "actual"), _number(exp, "expected")
        ok = {"lt": left < right, "lte": left <= right, "gt": left > right, "gte": left >= right}[op]
        return result(ok, f"expected {shown} {_SYMBOLS[op]} {exp}")
    if op == "matches":
        target = actual if isinstance(actual, str) else display(actual)
        return result(re.search(exp, target) is not None, f"{shown} does not match /{exp}/")
    if op == "type_is":
        wanted = exp.strip().lower()
        kind = json_type(actual)
        ok = kind == wanted or (
            wanted == "integer" and isinstance(actual, int) and not isinstance(actual, bool)
        )
        return result(ok, f"expected type {wanted}, got {kind}")
    return result(False, f"unknown operator {op!r}")


def _schema(a: Assertion, view: ResponseView) -> AssertionResult:
    def fail(message: str) -> AssertionResult:
        return AssertionResult(assertion=a, passed=False, message=message)

    data = view.json()
    if data is _NOT_JSON:
        return fail("response body is not valid JSON")
    try:
        schema = json.loads(a.expected)
    except ValueError as exc:
        return fail(f"schema is not valid JSON: {exc}")
    if not isinstance(schema, (dict, bool)):
        return fail("schema must be a JSON object")
    cls = validators.validator_for(schema)
    try:
        cls.check_schema(schema)
    except schema_exceptions.SchemaError as exc:
        return fail(f"invalid JSON Schema: {exc.message}")
    errors = sorted(cls(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    if not errors:
        return AssertionResult(assertion=a, passed=True)
    first = errors[0]
    where = "$" + "".join(
        f"[{p}]" if isinstance(p, int) else f".{p}" for p in first.absolute_path
    )
    more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
    return fail(f"{where}: {first.message}{more}")


def evaluate(assertion: Assertion, view: ResponseView, variables: dict[str, str]) -> AssertionResult:
    a = assertion.model_copy(
        update={
            "property": resolve(assertion.property, variables),
            "expected": resolve(assertion.expected, variables),
        }
    )
    try:
        if a.source == "json_schema":
            return _schema(a, view)
        found, actual, missing = _actual(a, view)
        return _compare(a, found, actual, missing)
    except (ValueError, re.error) as exc:
        return AssertionResult(assertion=a, passed=False, message=str(exc))


def extract(extraction: Extraction, view: ResponseView, variables: dict[str, str]) -> ExtractionResult:
    name = extraction.variable.strip()
    prop = resolve(extraction.property, variables)

    def fail(message: str) -> ExtractionResult:
        return ExtractionResult(variable=name, ok=False, message=message)

    try:
        if extraction.source == "status":
            value: str | None = str(view.response.status)
        elif extraction.source == "header":
            value = view.header(prop)
            if value is None:
                return fail(f"header {prop!r} is not present")
        elif extraction.source == "regex":
            match = re.search(prop, view.response.body)
            if not match:
                return fail(f"/{prop}/ did not match the body")
            value = (match.group(1) if match.groups() else match.group(0)) or ""
        else:
            data = view.json()
            if data is _NOT_JSON:
                return fail("response body is not valid JSON")
            found, raw = jsonpath.get(data, prop or "$")
            if not found:
                return fail(f"JSON path {prop or '$'!r} not found")
            value = raw if isinstance(raw, str) else json.dumps(raw)
    except (ValueError, re.error) as exc:
        return fail(str(exc))
    return ExtractionResult(variable=name, value=value, ok=True)
