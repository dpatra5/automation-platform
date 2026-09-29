from __future__ import annotations

import json
import ssl
from collections.abc import Callable

import httpx
import truststore

from lt.config import Config
from lt.http_client import (
    ClientPool,
    HostNotAllowedError,
    build_client,
    build_client_pool,
    prepare_routes,
    send,
    warmup,
)


def test_prepare_routes_bodies(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(
        routes=[
            {"name": "j", "path": "/j", "method": "POST", "body": {"a": 1}, "tenant": "t1"},
            {"name": "s", "path": "/s", "method": "PUT", "body": "raw"},
            {"name": "n", "path": "/n", "expect_status": [200]},
        ]
    )
    j, s, n = prepare_routes(cfg)
    assert json.loads(j.content or b"") == {"a": 1}
    assert j.headers["Content-Type"] == "application/json" and j.tenant == "t1"
    assert s.content == b"raw" and "Content-Type" not in s.headers
    assert n.content is None and n.expect_status == frozenset({200})


async def test_send_success_and_error(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory()
    route = prepare_routes(cfg)[0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/items":
            return httpx.Response(429, headers={"Retry-After": "1"})
        raise httpx.ConnectError("refused", request=request)

    async with build_client(cfg, httpx.MockTransport(handler)) as client:
        status, headers, err = await send(client, route)
        assert status == 429 and headers is not None and headers["retry-after"] == "1"
        bad = prepare_routes(config_factory(routes=[{"name": "b", "path": "/b"}]))[0]
        assert await send(client, bad) == (None, None, "ConnectError")


async def test_redirect_guard_blocks_non_allowlisted_host(
    config_factory: Callable[..., Config],
) -> None:
    cfg = config_factory(http={"follow_redirects": True})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://evil.example/steal"})

    async with build_client(cfg, httpx.MockTransport(handler)) as client:
        status, _, err = await send(client, prepare_routes(cfg)[0])
    assert status is None and err == HostNotAllowedError.__name__


async def test_client_pool_and_warmup(config_factory: Callable[..., Config]) -> None:
    cfg = config_factory(
        http={"max_connections": 8, "warmup_requests": 10, "warmup_path": "/healthz"}
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200)

    async with build_client_pool(cfg, httpx.MockTransport(handler)) as pool:
        assert isinstance(pool, ClientPool)
        assert len(pool.clients) == 2 and pool.connections_per_client == 4
        assert pool.for_worker(0) is pool.clients[0] and pool.for_worker(3) is pool.clients[1]
        assert await warmup(pool, cfg) == 10
    assert seen == ["/healthz"] * 10
    async with build_client_pool(config_factory()) as real:
        assert await warmup(real, config_factory()) == 0


async def test_client_pool_uses_native_trust_store(
    config_factory: Callable[..., Config], monkeypatch: object
) -> None:
    contexts: list[int] = []

    def native_context(protocol: int) -> ssl.SSLContext:
        contexts.append(protocol)
        return ssl.SSLContext(protocol)

    monkeypatch.setattr(truststore, "SSLContext", native_context)  # type: ignore[attr-defined]
    async with build_client_pool(config_factory()) as pool:
        assert pool.clients
    assert contexts == [ssl.PROTOCOL_TLS_CLIENT]
