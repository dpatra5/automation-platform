from __future__ import annotations

import time

import httpx
import pytest

from lt.demo_server import (
    DemoServerProcess,
    DemoSettings,
    FixedWindow,
    SlidingWindowLog,
    ThreadedDemoServer,
    TokenBucket,
    create_app,
)


def test_token_bucket_burst_then_refill() -> None:
    tb = TokenBucket(rate=10, burst=5, now=0.0)
    assert [tb.acquire(0.0).allowed for _ in range(6)] == [True] * 5 + [False]
    denied = tb.acquire(0.0)
    assert denied.retry_after_s == pytest.approx(0.1)
    assert tb.acquire(0.1).allowed
    assert not tb.acquire(0.1).allowed
    full = tb.acquire(100.0)
    assert full.allowed and full.remaining == 4 and full.limit == 5
    with pytest.raises(ValueError):
        TokenBucket(0, 1, 0)


def test_fixed_window_resets_at_boundary() -> None:
    fw = FixedWindow(limit=2, window_s=1.0)
    assert [fw.acquire(0.1).allowed for _ in range(3)] == [True, True, False]
    d = fw.acquire(0.75)
    assert not d.allowed and d.retry_after_s == pytest.approx(0.25)
    assert fw.acquire(1.0).allowed
    with pytest.raises(ValueError):
        FixedWindow(0, 1)


def test_sliding_window_log() -> None:
    sw = SlidingWindowLog(limit=2, window_s=1.0)
    assert sw.acquire(0.0).allowed and sw.acquire(0.5).allowed
    d = sw.acquire(0.9)
    assert not d.allowed and d.retry_after_s == pytest.approx(0.1)
    assert sw.acquire(1.0).allowed  # first entry expired
    assert not sw.acquire(1.2).allowed
    with pytest.raises(ValueError):
        SlidingWindowLog(1, 0)


def test_settings_factory() -> None:
    assert isinstance(DemoSettings(algo="fixed-window").make_limiter(0), FixedWindow)
    assert isinstance(DemoSettings(algo="sliding-window").make_limiter(0), SlidingWindowLog)
    tb = DemoSettings(rate=100, window_s=2).make_limiter(0)
    assert isinstance(tb, TokenBucket) and tb.rate == 50 and tb.capacity == 100
    with pytest.raises(ValueError):
        DemoSettings(algo="nope").make_limiter(0)  # type: ignore[arg-type]


async def test_app_limits_and_emits_headers() -> None:
    now = [0.0]
    app = create_app(DemoSettings(rate=2, burst=2, latency_ms=1), clock=lambda: now[0])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as c:
        r1 = await c.get("/api/items")
        await c.post("/api/items", json={"a": 1})
        r3 = await c.get("/api/items")
        assert r1.status_code == 200 and r1.json() == {"ok": True}
        assert r1.headers["RateLimit-Limit"] == "2"
        assert r1.headers["X-RateLimit-Remaining"] == "1"
        assert r3.status_code == 429 and r3.headers["Retry-After"] == "1"
        assert (await c.get("/healthz")).json() == {"status": "ok"}
        assert (await c.get("/__stats")).json() == {"global": {"allowed": 2, "denied": 1}}


async def test_app_per_key_scope() -> None:
    app = create_app(DemoSettings(rate=1, burst=1, scope="per-key"), clock=lambda: 0.0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://d") as c:
        assert (await c.get("/", headers={"X-API-Key": "a"})).status_code == 200
        assert (await c.get("/", headers={"X-API-Key": "b"})).status_code == 200
        assert (await c.get("/", headers={"X-API-Key": "a"})).status_code == 429
        assert (await c.get("/")).status_code == 200  # anonymous bucket
        stats = (await c.get("/__stats")).json()
        assert set(stats) == {"a", "b", "anonymous"}


def test_threaded_server_serves_requests() -> None:
    with (
        ThreadedDemoServer(DemoSettings(rate=5, burst=1)) as srv,
        httpx.Client(base_url=srv.base_url) as c,
    ):
        codes = [c.get("/x").status_code for _ in range(3)]
    assert codes[0] == 200 and 429 in codes


def test_server_process_serves_requests() -> None:
    srv = DemoServerProcess(DemoSettings(rate=5, burst=1, algo="fixed-window"))
    with srv, httpx.Client(base_url=srv.base_url) as c:
        deadline = time.monotonic() + 5
        while True:
            try:
                assert c.get("/healthz").status_code == 200
                break
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert c.get("/x").status_code in (200, 429)
    srv.stop()  # idempotent
