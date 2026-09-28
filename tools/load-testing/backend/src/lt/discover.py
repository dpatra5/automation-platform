"""Automatic API discovery: crawl a web app with Playwright, record the XHR/fetch calls it
makes, and turn them into ready-to-run load profiles.

Run as ``python -m lt.discover`` to execute one discovery in an isolated process: options are
read as JSON from stdin (so credentials never appear in the process list) and the result is
written as JSON to stdout.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import sys
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lt.config import host_allowed
from lt.utils.time import parse_duration

API_RESOURCE_TYPES = frozenset({"xhr", "fetch"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SKIP_LINK_RE = re.compile(r"log-?out|sign-?out|log-?off|/logout|delete|remove", re.IGNORECASE)
_SKIP_EXT_RE = re.compile(
    r"\.(pdf|zip|gz|tar|png|jpe?g|gif|svg|webp|ico|mp4|mp3|woff2?|ttf|css|js|map|xml|csv)$",
    re.IGNORECASE,
)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.I)
_NUM_RE = re.compile(r"^\d+$")
_TOKEN_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{20,}$")
_REPLAY_HEADERS = frozenset(
    {"content-type", "accept", "origin", "referer", "user-agent", "x-requested-with"}
)
_SENSITIVE_PATH_RE = re.compile(
    r"log-?in|sign-?in|auth|token|password|passwd|session|oauth|otp|mfa|register|sign-?up",
    re.IGNORECASE,
)
MAX_BODY_BYTES = 16 * 1024


class DiscoveryError(RuntimeError):
    pass


class DiscoveryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    max_pages: int = Field(default=10, ge=1, le=200)
    max_depth: int = Field(default=2, ge=0, le=10)
    wait_ms: int = Field(default=1500, ge=0, le=30_000)
    nav_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    # Extra hosts (exact or "*.suffix") whose API calls count as in scope.
    scope: list[str] = Field(default_factory=list)
    # Sent by the browser and reused by generated load profiles (e.g. Authorization).
    headers: dict[str, str] = Field(default_factory=dict)
    ignore_https_errors: bool = False

    @field_validator("url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        parts = urlsplit(v.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        return v.strip()

    @property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").lower()

    def scope_patterns(self) -> list[str]:
        return [*default_scope(self.host), *self.scope]


@dataclass
class Endpoint:
    id: str
    method: str
    base_url: str
    path: str
    template: str
    resource_type: str
    in_scope: bool
    sensitive: bool = False
    count: int = 1
    status: int | None = None
    content_type: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    pages: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return self.method in SAFE_METHODS


@dataclass
class DiscoveryResult:
    url: str
    pages: list[str]
    endpoints: list[Endpoint]
    errors: list[str]
    out_of_scope_hosts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryResult:
        return cls(
            url=data["url"],
            pages=list(data["pages"]),
            endpoints=[Endpoint(**e) for e in data["endpoints"]],
            errors=list(data["errors"]),
            out_of_scope_hosts=dict(data["out_of_scope_hosts"]),
        )


def default_scope(host: str) -> list[str]:
    """The page host plus its sibling subdomains (app.x.com -> x.com, *.x.com)."""
    labels = host.split(".")
    if re.fullmatch(r"[\d.]+|\[.*\]|localhost", host) or len(labels) < 3:
        return [host, f"*.{host}"] if len(labels) == 2 else [host]
    parent = ".".join(labels[1:])
    return [host, parent, f"*.{parent}"]


def normalize_segment(segment: str) -> str:
    if (
        _NUM_RE.match(segment)
        or _UUID_RE.match(segment)
        or _HEX_RE.match(segment)
        or _TOKEN_RE.match(segment)
    ):
        return "{id}"
    return segment


def path_template(path: str) -> str:
    return "/".join(normalize_segment(s) if s else s for s in path.split("/")) or "/"


def _origin(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _page_key(url: str) -> str:
    """Drop fragments except SPA hash routes (#/...)."""
    p = urlsplit(url)
    frag = p.fragment if p.fragment.startswith("/") else ""
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", p.query, frag))


def endpoint_id(method: str, base_url: str, template: str) -> str:
    return hashlib.sha1(
        f"{method} {base_url}{template}".encode(), usedforsecurity=False
    ).hexdigest()[:12]


class _Recorder:
    def __init__(self, opts: DiscoveryOptions) -> None:
        self.scope = opts.scope_patterns()
        self.endpoints: dict[str, Endpoint] = {}
        self.out_of_scope: Counter[str] = Counter()
        self.current_page = opts.url

    @staticmethod
    def _key(request: Any) -> tuple[str, str, str, Any] | None:
        if request.resource_type not in API_RESOURCE_TYPES:
            return None
        parts = urlsplit(request.url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None
        method = request.method.upper()
        base = _origin(request.url)
        template = path_template(parts.path or "/")
        return endpoint_id(method, base, template), base, template, parts

    def on_response(self, response: Any) -> None:
        found = self._key(response.request)
        ep = self.endpoints.get(found[0]) if found else None
        if ep is not None and ep.status is None:
            ep.status = response.status
            ep.content_type = (response.headers.get("content-type") or "").split(";")[0] or None

    def on_request(self, request: Any) -> None:
        found = self._key(request)
        if found is None:
            return
        key, base, template, parts = found
        host = parts.hostname.lower()
        in_scope = host_allowed(host, self.scope)
        if not in_scope:
            self.out_of_scope[host] += 1
        method = request.method.upper()
        existing = self.endpoints.get(key)
        if existing is not None:
            existing.count += 1
            if self.current_page not in existing.pages and len(existing.pages) < 5:
                existing.pages.append(self.current_page)
            return
        path = parts.path or "/"
        if parts.query:
            path += f"?{parts.query}"
        # Credentials-bearing calls are listed but never replayed with their payload.
        sensitive = bool(_SENSITIVE_PATH_RE.search(parts.path or ""))
        body: str | None = None
        if not sensitive:
            try:
                body = request.post_data
            except (UnicodeDecodeError, ValueError):
                body = None
        if body is not None and len(body.encode()) > MAX_BODY_BYTES:
            body = None
        headers = {k: v for k, v in request.headers.items() if k.lower() in _REPLAY_HEADERS}
        self.endpoints[key] = Endpoint(
            id=key,
            method=method,
            base_url=base,
            path=path,
            template=template,
            resource_type=request.resource_type,
            in_scope=in_scope,
            sensitive=sensitive,
            request_headers=headers,
            body=body,
            pages=[self.current_page],
        )


def discover(opts: DiscoveryOptions) -> DiscoveryResult:
    """Crawl same-origin pages breadth-first and record every in-page API call."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise DiscoveryError("playwright is not installed: pip install playwright") from exc

    recorder = _Recorder(opts)
    start_origin = _origin(opts.url)
    pages: list[str] = []
    errors: list[str] = []
    queue: deque[tuple[str, int]] = deque([(opts.url, 0)])
    seen = {_page_key(opts.url)}

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            raise DiscoveryError(
                f"could not launch Chromium ({exc.message.splitlines()[0]}); "
                "run `playwright install chromium`"
            ) from exc
        try:
            context = browser.new_context(
                ignore_https_errors=opts.ignore_https_errors,
                extra_http_headers=opts.headers or None,
            )
            page = context.new_page()
            page.on("request", recorder.on_request)
            page.on("response", recorder.on_response)
            while queue and len(pages) < opts.max_pages:
                url, depth = queue.popleft()
                recorder.current_page = url
                try:
                    page.goto(url, wait_until="load", timeout=opts.nav_timeout_ms)
                except (PlaywrightTimeout, PlaywrightError) as exc:
                    errors.append(f"{url}: {exc.message.splitlines()[0]}")
                    continue
                with contextlib.suppress(PlaywrightTimeout):
                    page.wait_for_load_state("networkidle", timeout=opts.nav_timeout_ms)
                # Scrolling triggers lazy-loaded lists and infinite-scroll APIs.
                page.evaluate("window.scrollTo(0, document.body ? document.body.scrollHeight : 0)")
                page.wait_for_timeout(opts.wait_ms)
                pages.append(url)
                if depth >= opts.max_depth:
                    continue
                hrefs: list[str] = page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                for href in hrefs:
                    key = _page_key(href)
                    if (
                        key in seen
                        or _origin(href) != start_origin
                        or _SKIP_LINK_RE.search(href)
                        or _SKIP_EXT_RE.search(urlsplit(href).path)
                    ):
                        continue
                    seen.add(key)
                    queue.append((key, depth + 1))
        finally:
            browser.close()

    endpoints = sorted(
        recorder.endpoints.values(), key=lambda e: (not e.in_scope, e.base_url, e.template)
    )
    return DiscoveryResult(
        url=opts.url,
        pages=pages,
        endpoints=endpoints,
        errors=errors,
        out_of_scope_hosts=dict(recorder.out_of_scope.most_common()),
    )


# -- load profile generation -----------------------------------------------------------


class LoadPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["per-endpoint", "combined"] = "per-endpoint"
    rate: float = Field(default=10.0, gt=0)
    duration: str = Field(default="30s", max_length=32)
    warmup: str | None = Field(default=None, max_length=32)
    expected_limit_rps: float | None = Field(default=None, gt=0)

    @field_validator("duration", "warmup")
    @classmethod
    def _duration(cls, v: str | None) -> str | None:
        if v is not None and parse_duration(v) <= 0:
            raise ValueError("duration must be > 0")
        return v


def _slug(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].strip("-") or "root"


def _route(ep: Endpoint, name: str, weight: float = 1.0) -> dict[str, Any]:
    expect = sorted({ep.status, 429} if ep.status and 200 <= ep.status < 400 else {200, 429})
    route: dict[str, Any] = {
        "name": name,
        "method": ep.method,
        "path": ep.path,
        "expect_status": expect,
        "weight": weight,
    }
    headers = {k: v for k, v in ep.request_headers.items() if k.lower() != "accept"}
    if headers:
        route["headers"] = headers
    if ep.body is not None:
        route["body"] = ep.body
    return route


def _config(
    name: str,
    base_url: str,
    routes: list[dict[str, Any]],
    plan: LoadPlan,
    headers: dict[str, str],
    verify_tls: bool,
) -> dict[str, Any]:
    host = (urlsplit(base_url).hostname or "").lower()
    profile: list[dict[str, Any]] = []
    if plan.warmup:
        profile.append({"duration": plan.warmup, "rate": max(plan.rate / 10, 1), "name": "warmup"})
    profile.append({"duration": plan.duration, "rate": plan.rate})
    config: dict[str, Any] = {
        "version": 1,
        "name": name,
        "base_url": base_url,
        "default_headers": {"Accept": "application/json, */*", **headers},
        "safety": {"allowlist": [host], "max_rps_cap": max(math.ceil(plan.rate), 1)},
        "model": {"type": "open", "workers": 4, "profile": profile},
        "http": {
            "max_connections": 64,
            "concurrency": 256,
            "read_timeout": "10s",
            "verify_tls": verify_tls,
        },
        "routes": routes,
    }
    if plan.expected_limit_rps:
        config["analysis"] = {"expected_limit_rps": plan.expected_limit_rps}
    return config


def build_configs(
    endpoints: list[Endpoint],
    plan: LoadPlan,
    headers: dict[str, str] | None = None,
    *,
    verify_tls: bool = True,
) -> list[tuple[list[str], dict[str, Any]]]:
    """Return ``(endpoint_ids, config)`` pairs: one per endpoint, or one per API host."""
    headers = headers or {}
    out: list[tuple[list[str], dict[str, Any]]] = []
    if plan.mode == "per-endpoint":
        for ep in endpoints:
            name = f"{ep.method.lower()}-{_slug(ep.template)}"
            host = urlsplit(ep.base_url).hostname or "api"
            out.append(
                ([ep.id], _config(f"scan {ep.method} {ep.template} @ {host}", ep.base_url,
                                  [_route(ep, name)], plan, headers, verify_tls))
            )  # fmt: skip
        return out
    by_base: dict[str, list[Endpoint]] = {}
    for ep in endpoints:
        by_base.setdefault(ep.base_url, []).append(ep)
    for base, eps in by_base.items():
        used: set[str] = set()
        routes = []
        for ep in eps:
            name = f"{ep.method.lower()}-{_slug(ep.template)}"
            while name in used:
                name = f"{name}-{len(used)}"
            used.add(name)
            # One tenant per host: fairness across unrelated endpoints is not meaningful.
            routes.append({**_route(ep, name, weight=float(ep.count)), "tenant": "app"})
        host = urlsplit(base).hostname or "api"
        out.append(
            (
                [e.id for e in eps],
                _config(f"scan {host} (combined)", base, routes, plan, headers, verify_tls),
            )
        )
    return out


def main() -> int:  # pragma: no cover - exercised via subprocess in integration tests
    try:
        opts = DiscoveryOptions.model_validate_json(sys.stdin.read())
        result = discover(opts)
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(result.to_dict(), sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
