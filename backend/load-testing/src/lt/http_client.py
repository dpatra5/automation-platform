"""httpx client factory, route preparation, and request execution."""

from __future__ import annotations

import asyncio
import json
import math
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import truststore

from lt import __version__
from lt.config import Config, host_allowed


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


def prepare_routes(cfg: Config) -> list[PreparedRoute]:
    routes: list[PreparedRoute] = []
    for r in cfg.routes:
        headers = dict(r.headers)
        content: bytes | None = None
        if isinstance(r.body, dict | list):
            content = json.dumps(r.body, separators=(",", ":")).encode()
            if not any(k.lower() == "content-type" for k in {**cfg.default_headers, **headers}):
                headers["Content-Type"] = "application/json"
        elif isinstance(r.body, str):
            content = r.body.encode()
        routes.append(
            PreparedRoute(
                name=r.name,
                tenant=r.tenant_key,
                method=r.method,
                path=r.path,
                headers=headers,
                content=content,
                expect_status=frozenset(r.expect_status),
                weight=r.weight,
            )
        )
    return routes


class HostNotAllowedError(httpx.HTTPError):
    """A request (e.g. a followed redirect) targeted a host outside the allowlist."""


def build_client(
    cfg: Config,
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    max_connections: int | None = None,
    verify: ssl.SSLContext | bool | None = None,
) -> httpx.AsyncClient:
    h = cfg.http
    conns = max_connections or h.max_connections
    limits = httpx.Limits(
        max_connections=conns,
        max_keepalive_connections=min(h.max_keepalive, conns),
        keepalive_expiry=h.keepalive_expiry,
    )
    timeout = httpx.Timeout(
        connect=h.connect_timeout,
        read=h.read_timeout,
        write=h.read_timeout,
        pool=h.connect_timeout + h.read_timeout,
    )
    headers = {"User-Agent": f"lt-python/{__version__}", **cfg.default_headers}
    hooks: dict[str, list[Callable[..., Any]]] = {}
    if h.follow_redirects and cfg.safety.require_allowlist:
        allowlist = list(cfg.safety.allowlist)

        async def guard(request: httpx.Request) -> None:
            if not host_allowed(request.url.host, allowlist):
                raise HostNotAllowedError(f"redirect to non-allowlisted host {request.url.host}")

        hooks["request"] = [guard]
    return httpx.AsyncClient(
        base_url=cfg.base_url,
        headers=headers,
        http2=h.http2,
        limits=limits,
        timeout=timeout,
        verify=h.verify_tls if verify is None else verify,
        follow_redirects=h.follow_redirects,
        trust_env=h.trust_env,
        transport=transport,
        event_hooks=hooks,
    )


class ClientPool:
    """Several small ``AsyncClient`` pools; request workers are pinned round-robin.

    httpcore's pool assignment is O(connections x waiters) per request, so one large pool
    collapses under high concurrency. Many small pools keep per-request cost flat.
    """

    def __init__(self, clients: list[httpx.AsyncClient], connections_per_client: int) -> None:
        if not clients:
            raise ValueError("ClientPool requires at least one client")
        self.clients = clients
        self.connections_per_client = connections_per_client

    def for_worker(self, index: int) -> httpx.AsyncClient:
        return self.clients[index % len(self.clients)]

    async def aclose(self) -> None:
        await asyncio.gather(*(c.aclose() for c in self.clients), return_exceptions=True)

    async def __aenter__(self) -> ClientPool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


def build_client_pool(cfg: Config, transport: httpx.AsyncBaseTransport | None = None) -> ClientPool:
    h = cfg.http
    shards = h.effective_client_shards
    per_client = max(1, math.ceil(h.max_connections / shards))
    # httpx loads CA certificates per client (~0.1-0.5 s each) even for http:// targets;
    # share one context across all clients.
    verify: ssl.SSLContext | bool = h.verify_tls
    if transport is None:
        if h.verify_tls and not h.trust_env:
            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        else:
            verify = httpx.create_ssl_context(
                verify=h.verify_tls, http2=h.http2, trust_env=h.trust_env
            )
    clients = [
        build_client(cfg, transport, max_connections=per_client, verify=verify)
        for _ in range(shards)
    ]
    return ClientPool(clients, per_client)


async def send(
    client: httpx.AsyncClient, route: PreparedRoute
) -> tuple[int | None, httpx.Headers | None, str | None]:
    """Send one request and fully read the body; returns ``(status, headers, error_type)``."""
    try:
        resp = await client.request(
            route.method, route.path, headers=route.headers or None, content=route.content
        )
    except (httpx.HTTPError, OSError) as exc:
        return None, None, type(exc).__name__
    return resp.status_code, resp.headers, None


async def warmup(pool: ClientPool, cfg: Config) -> int:
    """Open pooled connections before the measured run; returns successful responses."""
    remaining = cfg.http.warmup_requests
    if remaining <= 0:
        return 0
    path = cfg.http.warmup_path or cfg.routes[0].path
    ok = 0
    while remaining > 0:
        batch = []
        for client in pool.clients:
            n = min(pool.connections_per_client, remaining)
            batch += [client.get(path) for _ in range(n)]
            remaining -= n
            if remaining <= 0:
                break
        results = await asyncio.gather(*batch, return_exceptions=True)
        ok += sum(1 for r in results if isinstance(r, httpx.Response))
    return ok
