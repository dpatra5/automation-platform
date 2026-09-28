"""Resolve a request spec, guard the target, send it, and evaluate the response."""

from __future__ import annotations

import base64
import functools
import ipaddress
import os
import socket
import ssl
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import quote, quote_plus, urlencode

import certifi
import httpx

from apitest.assertions import ResponseView, evaluate, extract
from apitest.config import Settings
from apitest.schemas import (
    AssertionResult,
    ExecutionResult,
    ExtractionResult,
    RequestSettings,
    RequestSpec,
    ResolvedRequest,
    ResponseData,
)
from apitest.variables import resolve, unresolved

MASK = "••••••"
SENSITIVE_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key", "x-auth-token"}
)
_TEXT_HINTS = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "html", "yaml", "csv")
_CONTENT_TYPES = {
    "json": "application/json",
    "text": "text/plain; charset=utf-8",
    "xml": "application/xml",
    "form": "application/x-www-form-urlencoded",
}


class RequestBlocked(Exception):
    """The target is not permitted by server policy."""


@dataclass
class Prepared:
    method: str
    url: str
    headers: list[tuple[str, str]]
    body: str | None


def _has_header(headers: list[tuple[str, str]], name: str) -> bool:
    return any(k.lower() == name for k, _ in headers)


def prepare(spec: RequestSpec, variables: Mapping[str, str]) -> Prepared:
    def r(text: str) -> str:
        return resolve(text, variables)

    url = r(spec.url).strip()
    if not url:
        raise ValueError("URL is empty")
    if "://" not in url:
        url = "http://" + url

    query = [(r(p.key).strip(), r(p.value)) for p in spec.params if p.enabled and p.key.strip()]
    headers = [(r(h.key).strip(), r(h.value)) for h in spec.headers if h.enabled and h.key.strip()]

    auth = spec.auth
    if auth.type == "bearer" and not _has_header(headers, "authorization"):
        headers.append(("Authorization", f"Bearer {r(auth.token)}"))
    elif auth.type == "basic" and not _has_header(headers, "authorization"):
        creds = f"{r(auth.username)}:{r(auth.password)}".encode()
        headers.append(("Authorization", "Basic " + base64.b64encode(creds).decode("ascii")))
    elif auth.type == "api_key" and auth.key.strip():
        pair = (r(auth.key).strip(), r(auth.value))
        (headers if auth.location == "header" else query).append(pair)

    body: str | None = None
    mode = spec.body.mode
    if mode in ("json", "text", "xml"):
        body = r(spec.body.content)
    elif mode == "form":
        body = urlencode([(r(f.key), r(f.value)) for f in spec.body.form if f.enabled and f.key.strip()])
    if body is not None and not _has_header(headers, "content-type"):
        headers.append(("Content-Type", _CONTENT_TYPES[mode]))

    if query:
        base, hash_sign, fragment = url.partition("#")
        base += ("&" if "?" in base else "?") + urlencode(query)
        url = base + hash_sign + fragment
    return Prepared(spec.method, url, headers, body)


def _host_allowed(host: str, allowed: Iterable[str]) -> tuple[bool, bool]:
    """Return ``(allowed, explicitly_listed)``."""
    host = host.lower().strip("[]")
    wildcard = False
    for entry in allowed:
        e = entry.lower().strip()
        if e == "*":
            wildcard = True
        elif e.startswith("*.") and (host.endswith(e[1:]) or host == e[2:]):
            return True, True
        elif host == e:
            return True, True
    return wildcard, False


def _is_link_local(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            continue
        if ip.is_link_local:
            return True
    return False


def check_target(url: str, settings: Settings) -> None:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise ValueError(f"invalid URL: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise RequestBlocked(f"scheme {parsed.scheme!r} is not allowed; use http or https")
    host = parsed.host
    if not host:
        raise ValueError("URL has no host")
    ok, explicit = _host_allowed(host, settings.allowed_hosts)
    if not ok:
        raise RequestBlocked(f"host {host!r} is not in APIT_ALLOWED_HOSTS")
    if not explicit and _is_link_local(host):
        raise RequestBlocked(
            f"host {host!r} is a link-local (cloud metadata) address; "
            "list it explicitly in APIT_ALLOWED_HOSTS to allow it"
        )


def _is_binary(content_type: str, raw: bytes) -> bool:
    ctype = content_type.lower()
    if any(hint in ctype for hint in _TEXT_HINTS):
        return False
    return b"\x00" in raw[:1024]


def _decode(raw: bytes, encoding: str | None) -> str:
    try:
        return raw.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


@functools.lru_cache(maxsize=1)
def _verified_context() -> ssl.SSLContext:
    # Building a context loads the CA bundle (~0.5 s), so it is shared across requests.
    return ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())


def send(
    prepared: Prepared,
    options: RequestSettings,
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
) -> ResponseData:
    content = prepared.body.encode("utf-8") if prepared.body is not None else None
    limit = settings.max_response_bytes
    with httpx.Client(
        timeout=options.timeout_ms / 1000,
        follow_redirects=options.follow_redirects,
        verify=_verified_context() if options.verify_tls else False,
        transport=transport,
    ) as client:
        start = time.perf_counter()
        with client.stream(
            prepared.method, prepared.url, headers=prepared.headers, content=content
        ) as resp:
            chunks: list[bytes] = []
            size = 0
            truncated = False
            for chunk in resp.iter_bytes():
                if size + len(chunk) > limit:
                    chunks.append(chunk[: limit - size])
                    truncated = True
                    break
                chunks.append(chunk)
                size += len(chunk)
            elapsed = (time.perf_counter() - start) * 1000
    raw = b"".join(chunks)
    ctype = resp.headers.get("content-type", "")
    binary = _is_binary(ctype, raw)
    return ResponseData(
        status=resp.status_code,
        reason=resp.reason_phrase,
        http_version=resp.http_version,
        headers=list(resp.headers.multi_items()),
        body="" if binary else _decode(raw, resp.charset_encoding),
        body_truncated=truncated,
        is_binary=binary,
        size_bytes=len(raw),
        elapsed_ms=round(elapsed, 2),
        content_type=ctype,
    )


def redact(prepared: Prepared, secrets: Iterable[str]) -> ResolvedRequest:
    values: set[str] = set()
    for secret in secrets:
        if len(secret) >= 3:
            values.update({secret, quote(secret, safe=""), quote_plus(secret)})
    ordered = sorted(values, key=len, reverse=True)

    def mask(text: str) -> str:
        for value in ordered:
            text = text.replace(value, MASK)
        return text

    headers: list[tuple[str, str]] = []
    for key, value in prepared.headers:
        if key.lower() in SENSITIVE_HEADERS:
            scheme, _, rest = value.partition(" ")
            value = f"{scheme} {MASK}" if rest and scheme.lower() in ("bearer", "basic", "token") else MASK
        headers.append((key, mask(value)))
    return ResolvedRequest(
        method=prepared.method,
        url=mask(prepared.url),
        headers=headers,
        body=mask(prepared.body) if prepared.body is not None else None,
    )


def _missing_variables(spec: RequestSpec, variables: Mapping[str, str]) -> list[str]:
    texts = [spec.url, spec.body.content if spec.body.mode in ("json", "text", "xml") else ""]
    for kv in (*spec.params, *spec.headers, *(spec.body.form if spec.body.mode == "form" else [])):
        if kv.enabled:
            texts += [kv.key, kv.value]
    a = spec.auth
    texts += {"bearer": [a.token], "basic": [a.username, a.password], "api_key": [a.key, a.value]}.get(
        a.type, []
    )
    names = {name for text in texts for name in unresolved(resolve(text, variables))}
    return sorted(names)


def execute(
    spec: RequestSpec,
    variables: Mapping[str, str],
    settings: Settings,
    *,
    secrets: Iterable[str] = (),
    transport: httpx.BaseTransport | None = None,
) -> ExecutionResult:
    scope = dict(variables)
    missing = _missing_variables(spec, scope)
    response: ResponseData | None = None
    error: str | None = None

    try:
        prepared = prepare(spec, scope)
    except ValueError as exc:
        prepared = Prepared(spec.method, resolve(spec.url, scope), [], None)
        error = str(exc)

    url_missing = unresolved(resolve(spec.url, scope))
    if error is None and url_missing:
        error = f"unresolved variables in URL: {', '.join(url_missing)}"

    if error is None:
        try:
            check_target(prepared.url, settings)
            response = send(prepared, spec.settings, settings, transport)
        except RequestBlocked as exc:
            error = f"blocked: {exc}"
        except httpx.TimeoutException:
            error = f"request timed out after {spec.settings.timeout_ms} ms"
        except httpx.ConnectError as exc:
            error = f"could not connect: {exc}"
        except httpx.TooManyRedirects:
            error = "too many redirects"
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            error = str(exc) or exc.__class__.__name__
    if error and missing and not url_missing:
        error += f" (unresolved variables: {', '.join(missing)})"

    assertions = [a for a in spec.assertions if a.enabled]
    extractions = [e for e in spec.extractions if e.enabled and e.variable.strip()]
    extracted: dict[str, str] = {}
    if response is not None:
        view = ResponseView(response)
        extraction_results = [extract(e, view, scope) for e in extractions]
        for res in extraction_results:
            if res.ok and res.value is not None:
                extracted[res.variable] = res.value
        # Assertions may reference values extracted from this same response.
        assertion_results = [evaluate(a, view, {**scope, **extracted}) for a in assertions]
    else:
        assertion_results = [AssertionResult(assertion=a, passed=False, message="no response") for a in assertions]
        extraction_results = [
            ExtractionResult(variable=e.variable.strip(), ok=False, message="no response") for e in extractions
        ]

    return ExecutionResult(
        request=redact(prepared, secrets),
        response=response,
        error=error,
        assertions=assertion_results,
        extractions=extraction_results,
        extracted=extracted,
        unresolved=missing,
        passed=response is not None and all(r.passed for r in assertion_results),
    )
