"""Per-request runtime: templating, assertions, extraction, test data, pacing and think time.

The JMeter equivalents are User Defined Variables and functions (``{{var}}``, ``{{$uuid}}``),
Response/Duration/JSON assertions, JSON/Regex extractors, CSV Data Set Config, the Constant
Throughput Timer (``Pacer``), and Constant/Uniform Random timers (think time).
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from lt.config import AssertionsConfig, Config
from lt.utils import jsonpath
from lt.utils.time import parse_think_time

_VAR = re.compile(r"\{\{\s*([A-Za-z_$][\w$.-]*)\s*\}\}")


class Context:
    """Variable scope for one virtual user (or one open-model arrival)."""

    __slots__ = ("iteration", "rng", "vars", "vu")

    def __init__(
        self, variables: Mapping[str, str], *, vu: int = 0, rng: random.Random | None = None
    ) -> None:
        self.vars: dict[str, str] = dict(variables)
        self.vu = vu
        self.iteration = 0
        self.rng = rng or random.Random()

    def lookup(self, name: str) -> str | None:
        value = self.vars.get(name)
        if value is not None:
            return value
        match name:
            case "$uuid":
                return str(uuid.uuid4())
            case "$randomInt":
                return str(self.rng.randint(0, 1_000_000))
            case "$randomString":
                return secrets.token_hex(8)
            case "$timestamp":
                return str(int(time.time()))
            case "$timestampMs":
                return str(int(time.time() * 1000))
            case "$isoTimestamp":
                return datetime.now(UTC).isoformat(timespec="milliseconds")
            case "$vu":
                return str(self.vu)
            case "$iteration":
                return str(self.iteration)
        return None


class Template:
    """A string with ``{{name}}`` placeholders; unknown names are left as-is (like JMeter)."""

    __slots__ = ("parts", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        parts: list[tuple[bool, str]] = []
        pos = 0
        for match in _VAR.finditer(text):
            if match.start() > pos:
                parts.append((False, text[pos : match.start()]))
            parts.append((True, match.group(1)))
            pos = match.end()
        if pos < len(text):
            parts.append((False, text[pos:]))
        self.parts = tuple(parts)

    def render(self, ctx: Context) -> str:
        out: list[str] = []
        for is_var, value in self.parts:
            if is_var:
                found = ctx.lookup(value)
                out.append(found if found is not None else "{{" + value + "}}")
            else:
                out.append(value)
        return "".join(out)


def has_template(value: Any) -> bool:
    if isinstance(value, str):
        return _VAR.search(value) is not None
    if isinstance(value, dict):
        return any(has_template(v) for v in value.values())
    if isinstance(value, list):
        return any(has_template(v) for v in value)
    return False


def _compile(value: Any) -> Any:
    if isinstance(value, str):
        return Template(value)
    if isinstance(value, dict):
        return {k: _compile(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_compile(v) for v in value]
    return value


def _render(value: Any, ctx: Context) -> Any:
    if isinstance(value, Template):
        return value.render(ctx)
    if isinstance(value, dict):
        return {k: _render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, ctx) for v in value]
    return value


def safe_path(path: str) -> bool:
    # A variable could otherwise turn the path into an absolute URL and bypass the allowlist.
    return path.startswith("/") and not path.startswith("//") and "://" not in path


@dataclass(frozen=True, slots=True)
class Extractor:
    name: str
    kind: str  # json | regex | header
    segments: tuple[str | int, ...] = ()
    pattern: re.Pattern[str] | None = None
    header: str = ""


def _extractor(name: str, source: str) -> Extractor:
    if source.startswith("regex:"):
        return Extractor(name, "regex", pattern=re.compile(source[6:]))
    if source.startswith("header:"):
        return Extractor(name, "header", header=source[7:].strip().lower())
    return Extractor(name, "json", segments=tuple(jsonpath.parse(source)))


@dataclass(frozen=True, slots=True)
class PreparedRoute:
    name: str
    tenant: str
    method: str
    path: str
    headers: dict[str, str]
    content: bytes | None
    expect_status: frozenset[int]
    weight: float
    allow_429: bool = True
    templated: bool = False
    path_tpl: Template | None = None
    header_tpls: tuple[tuple[str, Template], ...] = ()
    body_tpl: Any = None
    body_is_json: bool = False
    assertions: AssertionsConfig = field(default_factory=AssertionsConfig)
    contains_tpls: tuple[Template, ...] = ()
    not_contains_tpls: tuple[Template, ...] = ()
    json_checks: tuple[tuple[str, tuple[str | int, ...], Any], ...] = ()
    extractors: tuple[Extractor, ...] = ()
    think: tuple[float, float] | None = None

    @property
    def needs_body(self) -> bool:
        return bool(self.contains_tpls or self.not_contains_tpls or self.json_checks) or any(
            e.kind != "header" for e in self.extractors
        )

    def render(self, ctx: Context) -> tuple[str, dict[str, str], bytes | None]:
        if not self.templated:
            return self.path, self.headers, self.content
        path = self.path_tpl.render(ctx) if self.path_tpl is not None else self.path
        headers = dict(self.headers)
        for name, tpl in self.header_tpls:
            headers[name] = tpl.render(ctx)
        content = self.content
        if self.body_tpl is not None:
            rendered = _render(self.body_tpl, ctx)
            content = (
                json.dumps(rendered, separators=(",", ":")).encode()
                if self.body_is_json
                else str(rendered).encode()
            )
        return path, headers, content


def prepare_routes(cfg: Config) -> list[PreparedRoute]:
    routes: list[PreparedRoute] = []
    closed = cfg.model.is_closed
    default_think = cfg.model.think_time
    for r in cfg.routes:
        headers = dict(r.headers)
        content: bytes | None = None
        body_is_json = isinstance(r.body, dict | list)
        if body_is_json:
            content = json.dumps(r.body, separators=(",", ":")).encode()
            if not any(k.lower() == "content-type" for k in {**cfg.default_headers, **headers}):
                headers["Content-Type"] = "application/json"
        elif isinstance(r.body, str):
            content = r.body.encode()
        header_tpls = tuple((k, Template(v)) for k, v in headers.items() if has_template(v))
        body_templated = has_template(r.body)
        a = r.assertions
        think_text = r.think_time if r.think_time is not None else default_think
        routes.append(
            PreparedRoute(
                name=r.name,
                tenant=r.tenant_key,
                method=r.method,
                path=r.path,
                headers=headers,
                content=content,
                expect_status=frozenset(r.expect_status or ()),
                weight=r.weight,
                allow_429=not closed,
                templated=has_template(r.path) or bool(header_tpls) or body_templated,
                path_tpl=Template(r.path) if has_template(r.path) else None,
                header_tpls=header_tpls,
                body_tpl=_compile(r.body) if body_templated else None,
                body_is_json=body_is_json,
                assertions=a,
                contains_tpls=tuple(Template(s) for s in a.body_contains),
                not_contains_tpls=tuple(Template(s) for s in a.body_not_contains),
                json_checks=tuple(
                    (path, tuple(jsonpath.parse(path)), _compile(expected))
                    for path, expected in a.jsonpath.items()
                ),
                extractors=tuple(_extractor(k, v) for k, v in r.extract.items()),
                think=parse_think_time(think_text) if think_text is not None else None,
            )
        )
    return routes


_NOT_JSON = object()


class ResponseView:
    """Decoded body and parsed JSON, computed at most once per response."""

    __slots__ = ("_json", "_text", "body", "headers")

    def __init__(self, body: bytes, headers: Mapping[str, str]) -> None:
        self.body = body
        self.headers = headers
        self._text: str | None = None
        self._json: Any = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.body.decode("utf-8", errors="replace")
        return self._text

    def json(self) -> Any:
        if self._json is None:
            try:
                self._json = json.loads(self.text)
            except ValueError:
                self._json = _NOT_JSON
        return self._json


def _shown(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 60 else text[:57] + "..."


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected or str(actual).lower() == str(expected).lower()
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        return float(actual) == float(expected)
    return actual == expected or str(actual) == str(expected)


def check(
    route: PreparedRoute,
    status: int,
    latency_s: float,
    view: ResponseView | None,
    ctx: Context,
) -> str | None:
    """Return why the sample failed, or ``None`` when it passed every check."""
    if route.expect_status:
        if status not in route.expect_status:
            return f"unexpected status {status}"
    elif status >= 400 and not (route.allow_429 and status == 429):
        return f"status {status}"
    max_ms = route.assertions.max_ms
    if max_ms is not None and latency_s * 1000 > max_ms:
        return f"response time > {max_ms:g} ms"
    if view is None:
        return None
    for tpl in route.contains_tpls:
        needle = tpl.render(ctx)
        if needle not in view.text:
            return f"body does not contain {_shown(needle)}"
    for tpl in route.not_contains_tpls:
        needle = tpl.render(ctx)
        if needle in view.text:
            return f"body contains {_shown(needle)}"
    if route.json_checks:
        data = view.json()
        if data is _NOT_JSON:
            return "response is not JSON"
        for text, segments, expected in route.json_checks:
            found, actual = jsonpath.get(data, list(segments))
            if not found:
                return f"{text} not found"
            wanted = _render(expected, ctx)
            if wanted != "*" and not _same(actual, wanted):
                return f"{text} = {_shown(actual)}, expected {_shown(wanted)}"
    return None


def extract(route: PreparedRoute, view: ResponseView) -> tuple[dict[str, str], list[str]]:
    """Run the route's extractors; returns ``(values, names that matched nothing)``."""
    values: dict[str, str] = {}
    missing: list[str] = []
    for ex in route.extractors:
        value: str | None = None
        if ex.kind == "header":
            value = view.headers.get(ex.header)
        elif ex.kind == "regex" and ex.pattern is not None:
            match = ex.pattern.search(view.text)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
        else:
            data = view.json()
            if data is not _NOT_JSON:
                found, raw = jsonpath.get(data, list(ex.segments))
                if found:
                    value = raw if isinstance(raw, str) else json.dumps(raw)
        if value is None:
            missing.append(ex.name)
        else:
            values[ex.name] = value
    return values, missing


class DataFeeder:
    """Hands out test-data rows; process ``part`` of ``parts`` takes a disjoint stride."""

    def __init__(
        self,
        rows: list[dict[str, str]],
        *,
        mode: str = "sequential",
        recycle: bool = True,
        part: int = 0,
        parts: int = 1,
        seed: int = 0,
    ) -> None:
        self.rows = rows
        self.mode = mode
        self.recycle = recycle
        self.parts = parts
        self._next = part
        self._rng = random.Random(seed * 7919 + part)

    @classmethod
    def for_config(cls, cfg: Config, part: int = 0, parts: int = 1) -> DataFeeder:
        if cfg.data is None:
            return cls([])
        return cls(
            cfg.data.records(),
            mode=cfg.data.mode,
            recycle=cfg.data.recycle,
            part=part,
            parts=parts,
            seed=cfg.model.seed,
        )

    def next(self) -> dict[str, str] | None:
        """Next row, ``{}`` when there is no data, ``None`` once exhausted without recycle."""
        if not self.rows:
            return {}
        if self.mode == "random":
            return self._rng.choice(self.rows)
        index = self._next
        self._next += self.parts
        if index >= len(self.rows):
            if not self.recycle:
                return None
            index %= len(self.rows)
        return self.rows[index]


class Pacer:
    """Caps request starts to ``rate`` per second (JMeter Constant Throughput Timer)."""

    def __init__(self, rate: float, clock: Callable[[], float] = time.perf_counter) -> None:
        self.interval = 1.0 / rate
        self.clock = clock
        self._next = 0.0

    async def wait(self) -> None:
        now = self.clock()
        slot = max(self._next, now)
        self._next = slot + self.interval
        if slot > now:
            await asyncio.sleep(slot - now)


def think_seconds(think: tuple[float, float] | None, rng: random.Random) -> float:
    if think is None:
        return 0.0
    low, high = think
    return low if low == high else rng.uniform(low, high)
