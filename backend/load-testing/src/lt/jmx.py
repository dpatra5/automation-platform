"""Convert an Apache JMeter test plan (.jmx) into an lt configuration.

Supported: Thread Group (users, ramp-up, duration/scheduler, loop count), Concurrency Thread
Group, HTTP Request samplers, HTTP Request Defaults, HTTP Header Manager, Cookie Manager,
User Defined Variables, CSV Data Set Config, Response/Duration/JSON assertions, JSON/Regex/
Boundary extractors, Constant/Uniform/Gaussian timers, Constant Throughput Timer, and
Transaction/Simple/Loop/If controllers (flattened). Everything else is reported as a warning.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET  # noqa: S405 - types only; parsing uses defusedxml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import yaml
from defusedxml import ElementTree as SafeET

from lt.utils import jsonpath

MAX_JMX_BYTES = 5 * 1024 * 1024
_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_THREAD_GROUPS = {"ThreadGroup", "SetupThreadGroup", "PostThreadGroup"}
_CONCURRENCY_GROUP = "com.blazemeter.jmeter.threads.concurrency.ConcurrencyThreadGroup"
_FLATTEN = {
    "TransactionController": "",
    "GenericController": "",
    "LoopController": "loop count is ignored; its requests run once per iteration",
    "IfController": "condition is ignored; its requests always run",
    "WhileController": "condition is ignored; its requests run once per iteration",
    "OnceOnlyController": "runs every iteration here, not once per user",
    "RandomController": "all children run in order instead of one at random",
    "InterleaveControl": "all children run in order instead of interleaving",
    "ThroughputController": "percentage is ignored; its requests always run",
    "RunTime": "runtime limit is ignored",
    "SwitchController": "all children run in order",
    "ForeachController": "loop is ignored; its requests run once",
}
_FUNCTIONS: dict[str, str] = {
    "__UUID": "$uuid",
    "__time": "$timestampMs",
    "__threadNum": "$vu",
    "__Random": "$randomInt",
    "__RandomString": "$randomString",
}
_VAR_RE = re.compile(r"\$\{([^{}]+)\}")


class JmxError(ValueError):
    """The input is not a usable JMeter test plan."""


@dataclass
class _Scope:
    headers: dict[str, str] = field(default_factory=dict)
    expect_status: list[int] = field(default_factory=list)
    body_contains: list[str] = field(default_factory=list)
    body_not_contains: list[str] = field(default_factory=list)
    max_ms: float | None = None
    json_checks: dict[str, Any] = field(default_factory=dict)
    extract: dict[str, str] = field(default_factory=dict)
    think: tuple[float, float] = (0.0, 0.0)

    def merged(self, other: _Scope) -> _Scope:
        return _Scope(
            headers={**self.headers, **other.headers},
            expect_status=other.expect_status or self.expect_status,
            body_contains=self.body_contains + other.body_contains,
            body_not_contains=self.body_not_contains + other.body_not_contains,
            max_ms=other.max_ms if other.max_ms is not None else self.max_ms,
            json_checks={**self.json_checks, **other.json_checks},
            extract={**self.extract, **other.extract},
            think=(self.think[0] + other.think[0], self.think[1] + other.think[1]),
        )


@dataclass
class _Plan:
    warnings: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    routes: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] | None = None
    throughput_per_min: float | None = None
    throughput_per_user: bool = False
    base: tuple[str, str, str] | None = None  # scheme, host, port

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


# -- XML helpers ------------------------------------------------------------------------


def _prop(el: ET.Element | None, name: str, default: str = "") -> str:
    if el is None:
        return default
    for child in el:
        if child.get("name") == name and child.tag != "elementProp":
            return (child.text or default).strip()
    return default


def _bool(el: ET.Element, name: str, default: bool = False) -> bool:
    value = _prop(el, name, "")
    return default if value == "" else value.lower() == "true"


def _element_prop(el: ET.Element, name: str) -> ET.Element | None:
    for child in el:
        if child.tag == "elementProp" and child.get("name") == name:
            return child
    return None


def _collection(el: ET.Element | None, name: str) -> list[ET.Element]:
    if el is None:
        return []
    for child in el:
        if child.tag == "collectionProp" and child.get("name") == name:
            return list(child)
    return []


def _arguments(el: ET.Element | None) -> list[tuple[str, str]]:
    return [
        (_prop(arg, "Argument.name"), _prop(arg, "Argument.value"))
        for arg in _collection(el, "Arguments.arguments")
    ]


def _pairs(tree: ET.Element | None) -> list[tuple[ET.Element, ET.Element | None]]:
    """JMeter stores each element followed by a ``hashTree`` holding its children."""
    if tree is None:
        return []
    children = list(tree)
    pairs: list[tuple[ET.Element, ET.Element | None]] = []
    i = 0
    while i < len(children):
        el = children[i]
        nxt = children[i + 1] if i + 1 < len(children) else None
        sub = nxt if nxt is not None and nxt.tag == "hashTree" else None
        pairs.append((el, sub))
        i += 2 if sub is not None else 1
    return pairs


def _enabled(el: ET.Element) -> bool:
    return el.get("enabled", "true").lower() != "false"


def _kind(el: ET.Element) -> str:
    return el.tag if el.tag != "ConfigTestElement" else el.get("guiclass", el.tag)


# -- value conversion -------------------------------------------------------------------


def _convert(text: str, plan: _Plan) -> str:
    """``${var}`` -> ``{{var}}``; common functions -> built-ins; others stay literal."""

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if not inner.startswith("__"):
            return "{{" + inner + "}}"
        name, _, args = inner.partition("(")
        if name in _FUNCTIONS:
            if name == "__Random":
                plan.warn("${__Random(min,max)} became {{$randomInt}} (0..1000000); ranges are ignored")
            return "{{" + _FUNCTIONS[name] + "}}"
        if name in ("__P", "__property"):
            parts = [p.strip() for p in args.rstrip(")").split(",")]
            if len(parts) > 1 and parts[1]:
                return parts[1]
            return "{{" + parts[0] + "}}" if parts and parts[0] else ""
        plan.warn(f"JMeter function {name}() is not supported and was left as-is")
        return match.group(0)

    return _VAR_RE.sub(repl, text)


def _resolve(text: str, plan: _Plan) -> str:
    """Substitute user-defined variables (used for base URL parts and thread counts)."""
    return _VAR_RE.sub(lambda m: plan.variables.get(m.group(1).strip(), m.group(0)), text)


def _seconds(text: str, default: float = 0.0) -> float:
    try:
        return max(float(text), 0.0)
    except ValueError:
        return default


def _ms_range(delay: str, spread: str, plan: _Plan) -> tuple[float, float]:
    try:
        low = float(delay or 0) / 1000
        high = low + float(spread or 0) / 1000
    except ValueError:
        plan.warn("a timer uses a variable delay; it was ignored")
        return 0.0, 0.0
    return low, high


def _add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] + b[0], a[1] + b[1]


def _identifier(name: str) -> str:
    return re.sub(r"\W", "_", name.strip()) or "value"


def _valid_jsonpath(path: str, plan: _Plan, name: str) -> bool:
    try:
        jsonpath.parse(path)
    except ValueError:
        plan.warn(f"{name}: JSON path {path!r} uses unsupported syntax (filters/recursion); skipped")
        return False
    return True


def _json_value(text: Any) -> Any:
    if not isinstance(text, str) or text == "*" or "{{" in text:
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


# -- scope elements ---------------------------------------------------------------------


def _scope_of(pairs: list[tuple[ET.Element, ET.Element | None]], plan: _Plan) -> _Scope:
    scope = _Scope()
    for el, _ in pairs:
        if not _enabled(el):
            continue
        kind = _kind(el)
        name = el.get("testname", kind)
        if kind == "HeaderManager":
            for h in _collection(el, "HeaderManager.headers"):
                key = _prop(h, "Header.name")
                if key:
                    scope.headers[key] = _convert(_prop(h, "Header.value"), plan)
        elif kind == "ResponseAssertion":
            _response_assertion(el, scope, plan, name)
        elif kind == "DurationAssertion":
            duration = _prop(el, "DurationAssertion.duration")
            if duration.isdigit():
                scope.max_ms = float(duration)
        elif kind == "JSONPathAssertion":
            path = _prop(el, "JSON_PATH")
            if _bool(el, "INVERT") or _bool(el, "EXPECT_NULL"):
                plan.warn(f"{name}: inverted/null JSON assertions are not supported; skipped")
            elif _valid_jsonpath(path, plan, name):
                validate = _bool(el, "JSONVALIDATION") and not _bool(el, "ISREGEX")
                if _bool(el, "ISREGEX"):
                    plan.warn(f"{name}: regex JSON assertion reduced to an existence check")
                expected = _convert(_prop(el, "EXPECTED_VALUE"), plan) if validate else "*"
                scope.json_checks[path] = _json_value(expected)
        elif kind == "JSONPostProcessor":
            names = [n.strip() for n in _prop(el, "JSONPostProcessor.referenceNames").split(";")]
            paths = [p.strip() for p in _prop(el, "JSONPostProcessor.jsonPathExprs").split(";")]
            for var, path in zip(names, paths, strict=False):
                if var and _valid_jsonpath(path, plan, name):
                    scope.extract[_identifier(var)] = path
        elif kind == "RegexExtractor":
            var, regex = _prop(el, "RegexExtractor.refname"), _prop(el, "RegexExtractor.regex")
            if _prop(el, "RegexExtractor.useHeaders") not in ("", "false"):
                plan.warn(f"{name}: regex extractors on headers are applied to the body instead")
            if var and regex:
                scope.extract[_identifier(var)] = "regex:" + regex
        elif kind == "BoundaryExtractor":
            var = _prop(el, "BoundaryExtractor.refname")
            left = re.escape(_prop(el, "BoundaryExtractor.lboundary"))
            right = re.escape(_prop(el, "BoundaryExtractor.rboundary"))
            if var:
                scope.extract[_identifier(var)] = f"regex:{left}(.*?){right}"
        elif kind == "ConstantTimer":
            scope.think = _add(scope.think, _ms_range(_prop(el, "ConstantTimer.delay"), "0", plan))
        elif kind in ("UniformRandomTimer", "GaussianRandomTimer"):
            spread = _ms_range(_prop(el, "ConstantTimer.delay"), _prop(el, "RandomTimer.range"), plan)
            scope.think = _add(scope.think, spread)
        elif kind == "ConstantThroughputTimer":
            try:
                plan.throughput_per_min = float(_prop(el, "throughput") or 0) or None
            except ValueError:
                plan.warn(f"{name}: variable throughput is not supported")
            plan.throughput_per_user = _prop(el, "calcMode", "0") == "0"
        elif kind == "Arguments":
            for key, value in _arguments(el):
                if key:
                    plan.variables[key] = _convert(value, plan)
        elif kind == "HttpDefaultsGui":
            for key in ("domain", "port", "protocol"):
                value = _prop(el, f"HTTPSampler.{key}")
                if value:
                    plan.defaults[key] = value
        elif kind == "CSVDataSet":
            _csv_data_set(el, plan, name)
        elif kind in ("AuthManager", "KeystoreConfig"):
            plan.warn(f"{name}: {kind} is not supported; add credentials as headers")
        elif kind.startswith(("JSR223", "BeanShell")) and not kind.endswith("Sampler"):
            plan.warn(f"{name}: scripted {kind} was skipped")
        elif kind.endswith(("Assertion", "Extractor", "PostProcessor", "PreProcessor", "Timer")):
            plan.warn(f"{name}: {kind} is not supported and was skipped")
    return scope


def _response_assertion(el: ET.Element, scope: _Scope, plan: _Plan, name: str) -> None:
    field_name = _prop(el, "Assertion.test_field")
    try:
        test_type = int(_prop(el, "Assertion.test_type", "16") or 16)
    except ValueError:
        test_type = 16
    negate = bool(test_type & 4)
    strings = [
        _convert((s.text or "").strip(), plan)
        for s in _collection(el, "Asserion.test_strings")  # sic: JMeter's property name
        if (s.text or "").strip()
    ]
    if field_name == "Assertion.response_code":
        codes = [int(s) for s in strings if s.isdigit()]
        if negate or len(codes) != len(strings):
            plan.warn(f"{name}: only positive, literal status-code assertions are supported")
        elif codes:
            scope.expect_status = codes
    elif field_name in ("Assertion.response_data", "Assertion.response_data_as_document", ""):
        if test_type & 1 or test_type & 8:
            plan.warn(f"{name}: matches/equals body assertions were converted to 'contains'")
        (scope.body_not_contains if negate else scope.body_contains).extend(strings)
    else:
        plan.warn(f"{name}: assertions on {field_name or 'this field'} are not supported")


def _csv_data_set(el: ET.Element, plan: _Plan, name: str) -> None:
    if plan.data is not None:
        plan.warn(f"{name}: only the first CSV Data Set Config is used")
        return
    names = [n.strip() for n in _prop(el, "variableNames").split(",") if n.strip()]
    delimiter = _prop(el, "delimiter", ",") or ","
    delimiter = "\t" if delimiter == "\\t" else delimiter[0]
    plan.data = {
        "filename": _prop(el, "filename"),
        "columns": names or None,
        "delimiter": delimiter,
        "skip_first": _bool(el, "ignoreFirstLine"),
        # Without recycle JMeter either stops the thread or feeds <EOF>; only the former fits.
        "recycle": _bool(el, "recycle", True) or not _bool(el, "stopThread"),
        "mode": "random" if _prop(el, "shareMode") == "shareMode.random" else "sequential",
    }


# -- samplers ---------------------------------------------------------------------------


def _encode(value: str) -> str:
    # Keep {{placeholders}} intact so they are substituted at run time.
    return "".join(
        part if part.startswith("{{") else quote(part, safe="")
        for part in re.split(r"(\{\{[^{}]+\}\})", value)
    )


def _fmt(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms}ms" if ms % 1000 else f"{ms // 1000}s"


def _sampler(el: ET.Element, scope: _Scope, prefix: str, plan: _Plan) -> dict[str, Any] | None:
    name = prefix + el.get("testname", "request")
    method = (_prop(el, "HTTPSampler.method", "GET") or "GET").upper()
    if method not in _HTTP_METHODS:
        plan.warn(f"{name}: method {method} is not supported; skipped")
        return None
    scheme = _resolve(_prop(el, "HTTPSampler.protocol") or plan.defaults.get("protocol", ""), plan)
    host = _resolve(_prop(el, "HTTPSampler.domain") or plan.defaults.get("domain", ""), plan)
    port = _resolve(_prop(el, "HTTPSampler.port") or plan.defaults.get("port", ""), plan)
    path = _prop(el, "HTTPSampler.path") or "/"
    if path.lower().startswith(("http://", "https://")):
        parts = urlsplit(path)
        scheme, host, port = parts.scheme, parts.hostname or "", str(parts.port or "")
        path = parts.path + (f"?{parts.query}" if parts.query else "")
    target = ((scheme or "http").lower(), host.lower(), port)
    if plan.base is None:
        plan.base = target
    elif host and target != plan.base:
        plan.warn(f"{name}: targets {host}, a different host from the base URL; skipped")
        return None
    path = _convert(path if path.startswith("/") else "/" + path, plan)

    route: dict[str, Any] = {"name": name, "method": method, "path": path}
    headers = dict(scope.headers)
    arguments = _collection(_element_prop(el, "HTTPsampler.Arguments"), "Arguments.arguments")
    if _bool(el, "HTTPSampler.postBodyRaw") and arguments:
        route["body"] = _convert(_prop(arguments[0], "Argument.value"), plan)
    elif arguments:
        encoded = "&".join(
            f"{_encode(_convert(_prop(a, 'Argument.name'), plan))}="
            f"{_encode(_convert(_prop(a, 'Argument.value'), plan))}"
            for a in arguments
            if _prop(a, "Argument.name")
        )
        if encoded and method in ("GET", "DELETE", "HEAD", "OPTIONS"):
            route["path"] = path + ("&" if "?" in path else "?") + encoded
        elif encoded:
            route["body"] = encoded
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/x-www-form-urlencoded"
    if _collection(_element_prop(el, "HTTPsampler.Files"), "HTTPFileArgs.files"):
        plan.warn(f"{name}: file uploads are not supported; the request is sent without files")
    if headers:
        route["headers"] = headers
    if scope.expect_status:
        route["expect_status"] = scope.expect_status
    assertions: dict[str, Any] = {}
    if scope.max_ms is not None:
        assertions["max_ms"] = scope.max_ms
    if scope.body_contains:
        assertions["body_contains"] = scope.body_contains
    if scope.body_not_contains:
        assertions["body_not_contains"] = scope.body_not_contains
    if scope.json_checks:
        assertions["jsonpath"] = scope.json_checks
    if assertions:
        route["assertions"] = assertions
    if scope.extract:
        route["extract"] = scope.extract
    low, high = scope.think
    if high > 0:
        route["think_time"] = _fmt(low) if low == high else f"{_fmt(low)}-{_fmt(high)}"
    return route


def _walk(tree: ET.Element, inherited: _Scope, prefix: str, plan: _Plan) -> None:
    pairs = _pairs(tree)
    scope = inherited.merged(_scope_of(pairs, plan))
    for el, sub in pairs:
        if not _enabled(el):
            continue
        kind = _kind(el)
        if kind == "HTTPSamplerProxy":
            own = scope.merged(_scope_of(_pairs(sub), plan)) if sub is not None else scope
            route = _sampler(el, own, prefix, plan)
            if route is not None:
                plan.routes.append(route)
        elif kind in _FLATTEN:
            note = _FLATTEN[kind]
            if note:
                plan.warn(f"{el.get('testname', kind)}: {note}")
            if sub is not None:
                label = el.get("testname", "")
                inner = f"{prefix}{label} / " if kind == "TransactionController" and label else prefix
                _walk(sub, scope, inner, plan)
        elif kind.endswith(("Sampler", "SamplerProxy")):
            plan.warn(f"{el.get('testname', kind)}: {kind} is not an HTTP request; skipped")


# -- thread groups ----------------------------------------------------------------------


def _model(group: ET.Element, plan: _Plan) -> dict[str, Any]:
    if group.tag == _CONCURRENCY_GROUP:
        unit = 60.0 if _prop(group, "Unit", "M") == "M" else 1.0
        users = int(_seconds(_resolve(_prop(group, "TargetLevel", "1"), plan), 1)) or 1
        ramp = _seconds(_resolve(_prop(group, "RampUp", "0"), plan)) * unit
        hold = _seconds(_resolve(_prop(group, "Hold", "1"), plan), 1) * unit
        return {"users": users, "ramp_up": _fmt(ramp), "duration": _fmt(max(hold, 1.0))}

    users = int(_seconds(_resolve(_prop(group, "ThreadGroup.num_threads", "1"), plan), 1)) or 1
    ramp = _seconds(_resolve(_prop(group, "ThreadGroup.ramp_time", "0"), plan))
    loops_el = _element_prop(group, "ThreadGroup.main_controller")
    forever = loops_el is not None and _bool(loops_el, "LoopController.continue_forever")
    try:
        loops = int(float(_resolve(_prop(loops_el, "LoopController.loops", "1"), plan)))
    except ValueError:
        loops = 1
        plan.warn("loop count uses a variable; imported as 1 iteration per user")
    model: dict[str, Any] = {"users": users, "ramp_up": _fmt(ramp)}
    if _bool(group, "ThreadGroup.scheduler"):
        # JMeter's duration covers the whole thread group, ramp-up included.
        duration = _seconds(_resolve(_prop(group, "ThreadGroup.duration", "0"), plan))
        model["duration"] = _fmt(max(duration - ramp, 1.0))
        if loops > 0 and not forever:
            model["iterations"] = loops
    elif loops <= 0 or forever:
        model["duration"] = "10m"
        plan.warn("the thread group loops forever without a duration; limited to 10 minutes")
    else:
        model["iterations"] = loops
        model["duration"] = "1h"
        plan.warn("no scheduler duration: users stop after their loop count (1 hour maximum)")
    if _prop(group, "ThreadGroup.delay") not in ("", "0"):
        plan.warn("thread group startup delay is not supported and was ignored")
    return model


def _data_section(plan: _Plan, data_dir: Path | None) -> dict[str, Any]:
    spec = plan.data or {}
    columns = spec["columns"]
    section: dict[str, Any] = {"mode": spec["mode"], "recycle": spec["recycle"]}
    if spec["delimiter"] != ",":
        section["delimiter"] = spec["delimiter"]
    filename = spec["filename"]
    text: str | None = None
    if data_dir is not None and filename and "${" not in filename:
        try:
            text = (data_dir / filename).read_text(encoding="utf-8-sig")
        except OSError:
            plan.warn(f"CSV file {filename!r} was not found next to the .jmx file")
    if text is not None:
        lines = text.splitlines()
        if spec["skip_first"] and columns:
            lines = lines[1:]
        section["csv"] = "\n".join(lines)
        if columns:
            section["columns"] = columns
        return section
    plan.warn(f"CSV Data Set {filename or ''!r}: paste the file into data.csv (placeholder added)")
    section["rows"] = [{name: "" for name in (columns or ["value"])}]
    return section


def convert_jmx(text: str, *, data_dir: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Return ``(config dict, warnings)``. ``data_dir`` lets the CLI inline CSV data files."""
    if len(text.encode()) > MAX_JMX_BYTES:
        raise JmxError("the .jmx file is larger than 5 MiB")
    try:
        root = SafeET.fromstring(text)
    except Exception as exc:  # defusedxml raises several parser/security error types
        raise JmxError(f"not a valid JMeter .jmx (XML) file: {exc}") from exc
    if root.tag != "jmeterTestPlan":
        raise JmxError("not a JMeter test plan (expected a <jmeterTestPlan> root element)")
    top_pairs = _pairs(root.find("hashTree"))
    if not top_pairs or top_pairs[0][0].tag != "TestPlan":
        raise JmxError("the .jmx file has no TestPlan element")
    test_plan, plan_tree = top_pairs[0]
    if plan_tree is None:
        raise JmxError("the test plan is empty")
    plan = _Plan()
    for key, value in _arguments(_element_prop(test_plan, "TestPlan.user_defined_variables")):
        if key:
            plan.variables[key] = _convert(value, plan)

    plan_pairs = _pairs(plan_tree)
    plan_scope = _scope_of(plan_pairs, plan)
    groups = [
        (el, sub)
        for el, sub in plan_pairs
        if (el.tag in _THREAD_GROUPS or el.tag == _CONCURRENCY_GROUP) and _enabled(el)
    ]
    main = [g for g in groups if g[0].tag not in ("SetupThreadGroup", "PostThreadGroup")] or groups
    if not main:
        raise JmxError("the test plan has no enabled Thread Group")
    group, group_tree = main[0]
    if len(groups) > 1:
        plan.warn(
            f"only thread group {group.get('testname', 'Thread Group')!r} was imported; "
            f"{len(groups) - 1} other thread group(s) were skipped"
        )
    model = _model(group, plan)
    if group_tree is not None:
        _walk(group_tree, plan_scope, "", plan)
    if not plan.routes:
        raise JmxError("no HTTP Request samplers could be imported")

    seen: dict[str, int] = {}
    for route in plan.routes:
        base_name = route["name"][:120] or "request"
        seen[base_name] = seen.get(base_name, 0) + 1
        route["name"] = base_name if seen[base_name] == 1 else f"{base_name} ({seen[base_name]})"

    scheme, host, port = plan.base or ("http", "", "")
    if not host or "${" in host or "{{" in host:
        plan.warn("the server host could not be determined; set base_url before running")
        host = "localhost"
    default_port = {"http": "80", "https": "443"}.get(scheme)
    netloc = host if not port or port == default_port else f"{host}:{port}"
    users = int(model["users"])
    if plan.throughput_per_min:
        per_min = plan.throughput_per_min * (users if plan.throughput_per_user else 1)
        model["max_rps"] = round(per_min / 60, 3)

    cfg: dict[str, Any] = {
        "version": 1,
        "name": test_plan.get("testname") or "Imported JMeter plan",
        "base_url": f"{scheme}://{netloc}",
        "safety": {"allowlist": [host], "max_rps_cap": 1000, "max_users_cap": max(1000, users)},
        "model": {"type": "closed", **model},
        # JMeter uses HTTP/1.1 and follows redirects by default.
        "http": {
            "http2": False,
            "follow_redirects": True,
            "cookies": True,
            "max_connections": max(100, users),
            "max_keepalive": max(100, users),
        },
        "routes": plan.routes,
    }
    if plan.variables:
        cfg["variables"] = plan.variables
    if plan.data is not None:
        cfg["data"] = _data_section(plan, data_dir)
    return cfg, plan.warnings


def jmx_to_yaml(text: str, *, data_dir: Path | None = None) -> tuple[str, list[str]]:
    cfg, warnings = convert_jmx(text, data_dir=data_dir)
    return yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=100), warnings
