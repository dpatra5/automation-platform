"""Deterministic local rate-limited API for examples and integration tests."""

from __future__ import annotations

import asyncio
import math
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Receive, Send
from starlette.types import Scope as ASGIScope

Algo = Literal["token-bucket", "fixed-window", "sliding-window"]
Scope = Literal["global", "per-key"]
ALGOS: tuple[Algo, ...] = ("token-bucket", "fixed-window", "sliding-window")

_OK_BODY = b'{"ok":true}'
_LIMITED_BODY = b'{"error":"rate_limited"}'
_MANAGEMENT_PATHS = frozenset({"/healthz", "/__stats"})
# Not rate limited: a small shop API for virtual-user (closed model) scenarios.
_APP_PREFIX = "/app/"
DEMO_PASSWORD = "demo"  # noqa: S105 - public demo credential
_MAX_SESSIONS = 10_000
_PRODUCTS = [
    {"id": i, "name": name, "price": price}
    for i, (name, price) in enumerate(
        [
            ("Desk lamp", 24.5), ("Office chair", 149.0), ("Standing desk", 399.0),
            ("Monitor arm", 79.9), ("Keyboard", 59.0), ("Mouse", 25.0), ("Headset", 89.0),
            ("Webcam", 69.0), ("USB hub", 19.9), ("Notebook", 4.5), ("Desk lamp XL", 34.0),
            ("Cable tray", 15.0),
        ],
        start=1,
    )
]  # fmt: skip


class _Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str


class _CartItem(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=100)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    reset_s: float
    retry_after_s: float


class Limiter(Protocol):
    def acquire(self, now: float) -> Decision: ...


class TokenBucket:
    """Capacity ``burst`` tokens, refilled continuously at ``rate`` tokens/second."""

    def __init__(self, rate: float, burst: float, now: float) -> None:
        if rate <= 0 or burst < 1:
            raise ValueError("token bucket requires rate > 0 and burst >= 1")
        self.rate = rate
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.last = now

    def acquire(self, now: float) -> Decision:
        elapsed = max(now - self.last, 0.0)
        self.last = max(now, self.last)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        # Epsilon absorbs float drift when arrivals align exactly with refill boundaries.
        allowed = self.tokens >= 1.0 - 1e-9
        if allowed:
            self.tokens = max(self.tokens - 1.0, 0.0)
        retry = 0.0 if allowed else (1.0 - self.tokens) / self.rate
        return Decision(
            allowed,
            int(self.capacity),
            int(self.tokens),
            (self.capacity - self.tokens) / self.rate,
            retry,
        )


class FixedWindow:
    """At most ``limit`` requests per aligned window of ``window_s`` seconds."""

    def __init__(self, limit: int, window_s: float) -> None:
        if limit < 1 or window_s <= 0:
            raise ValueError("fixed window requires limit >= 1 and window > 0")
        self.limit = limit
        self.window = window_s
        self.index: int | None = None
        self.count = 0

    def acquire(self, now: float) -> Decision:
        idx = int(now // self.window)
        if idx != self.index:
            self.index = idx
            self.count = 0
        reset = (idx + 1) * self.window - now
        allowed = self.count < self.limit
        if allowed:
            self.count += 1
        remaining = self.limit - self.count
        return Decision(allowed, self.limit, remaining, reset, 0.0 if allowed else reset)


class SlidingWindowLog:
    """At most ``limit`` requests in any trailing ``window_s`` interval."""

    def __init__(self, limit: int, window_s: float) -> None:
        if limit < 1 or window_s <= 0:
            raise ValueError("sliding window requires limit >= 1 and window > 0")
        self.limit = limit
        self.window = window_s
        self.log: deque[float] = deque()

    def acquire(self, now: float) -> Decision:
        cutoff = now - self.window
        log = self.log
        while log and log[0] <= cutoff:
            log.popleft()
        allowed = len(log) < self.limit
        if allowed:
            log.append(now)
        reset = log[0] + self.window - now if log else self.window
        return Decision(
            allowed, self.limit, self.limit - len(log), reset, 0.0 if allowed else reset
        )


@dataclass(frozen=True)
class DemoSettings:
    rate: float = 1000.0
    burst: int | None = None
    window_s: float = 1.0
    algo: Algo = "token-bucket"
    scope: Scope = "global"
    key_header: str = "X-API-Key"
    latency_ms: float = 0.0

    def make_limiter(self, now: float) -> Limiter:
        if self.algo == "token-bucket":
            burst = self.burst if self.burst is not None else max(int(self.rate), 1)
            return TokenBucket(self.rate / self.window_s, burst, now)
        if self.algo == "fixed-window":
            return FixedWindow(max(int(self.rate), 1), self.window_s)
        if self.algo == "sliding-window":
            return SlidingWindowLog(max(int(self.rate), 1), self.window_s)
        raise ValueError(f"unknown algorithm {self.algo!r}")


def create_app(settings: DemoSettings, clock: Callable[[], float] = time.perf_counter) -> ASGIApp:
    """FastAPI serves management endpoints; limited routes use a lean ASGI fast path."""
    api = FastAPI(title="lt demo server", docs_url=None, redoc_url=None, openapi_url=None)
    limiters: dict[str, Limiter] = {}
    stats: dict[str, list[int]] = {}
    delay = settings.latency_ms / 1000.0
    key_header = settings.key_header.lower().encode("latin-1")
    per_key = settings.scope == "per-key"

    @api.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/__stats")
    async def get_stats() -> dict[str, dict[str, int]]:
        return {k: {"allowed": v[0], "denied": v[1]} for k, v in stats.items()}

    sessions: dict[str, str] = {}
    carts: dict[str, list[dict[str, int]]] = {}

    def user_for(authorization: str | None) -> str:
        token = (authorization or "").removeprefix("Bearer ").strip()
        user = sessions.get(token)
        if user is None:
            raise HTTPException(401, "missing or invalid bearer token")
        return user

    async def app_delay() -> None:
        if delay > 0:
            await asyncio.sleep(delay)

    @api.post("/app/login")
    async def app_login(body: _Login, response: Response) -> dict[str, str]:
        await app_delay()
        if body.password != DEMO_PASSWORD:
            raise HTTPException(401, "invalid credentials")
        if len(sessions) >= _MAX_SESSIONS:
            sessions.clear()
            carts.clear()
        token = secrets.token_hex(12)
        sessions[token] = body.username
        response.set_cookie("session", token, httponly=True, samesite="lax")
        return {"token": token, "username": body.username}

    @api.get("/app/products")
    async def app_products(
        q: str = "", page: int = 1, authorization: str | None = Header(default=None)
    ) -> dict[str, object]:
        user_for(authorization)
        await app_delay()
        words = [w for w in q.lower().split() if w]
        items = [p for p in _PRODUCTS if all(w in str(p["name"]).lower() for w in words)]
        start = (max(page, 1) - 1) * 5
        return {"items": items[start : start + 5], "count": len(items), "page": page}

    @api.get("/app/products/{product_id}")
    async def app_product(
        product_id: int, authorization: str | None = Header(default=None)
    ) -> dict[str, object]:
        user_for(authorization)
        await app_delay()
        for product in _PRODUCTS:
            if product["id"] == product_id:
                return {**product, "in_stock": product_id % 4 != 0}
        raise HTTPException(404, "product not found")

    @api.post("/app/cart", status_code=201)
    async def app_cart(
        body: _CartItem, authorization: str | None = Header(default=None)
    ) -> dict[str, object]:
        user = user_for(authorization)
        await app_delay()
        if not any(p["id"] == body.product_id for p in _PRODUCTS):
            raise HTTPException(404, "product not found")
        cart = carts.setdefault(user, [])[-49:]
        cart.append({"product_id": body.product_id, "quantity": body.quantity})
        carts[user] = cart
        return {"items": len(cart), "user": user}

    @api.get("/app/profile")
    async def app_profile(request: Request) -> dict[str, str]:
        await app_delay()
        user = sessions.get(request.cookies.get("session", ""))
        if user is None:
            raise HTTPException(401, "no session cookie")
        return {"username": user}

    async def app(scope: ASGIScope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"] in _MANAGEMENT_PATHS
            or scope["path"].startswith(_APP_PREFIX)
        ):
            await api(scope, receive, send)
            return
        key = "global"
        if per_key:
            key = "anonymous"
            for name, value in scope["headers"]:
                if name == key_header:
                    key = value.decode("latin-1")
                    break
        now = clock()
        limiter = limiters.get(key)
        if limiter is None:
            limiter = limiters[key] = settings.make_limiter(now)
        d = limiter.acquire(now)
        counter = stats.setdefault(key, [0, 0])
        counter[0 if d.allowed else 1] += 1
        limit = str(d.limit).encode()
        remaining = str(max(d.remaining, 0)).encode()
        reset = str(math.ceil(d.reset_s)).encode()
        body = _OK_BODY if d.allowed else _LIMITED_BODY
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"ratelimit-limit", limit),
            (b"ratelimit-remaining", remaining),
            (b"ratelimit-reset", reset),
            (b"x-ratelimit-limit", limit),
            (b"x-ratelimit-remaining", remaining),
            (b"x-ratelimit-reset", reset),
        ]
        if not d.allowed:
            headers.append((b"retry-after", str(max(1, math.ceil(d.retry_after_s))).encode()))
        if delay > 0:
            await asyncio.sleep(delay)
        status = 200 if d.allowed else 429
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    return app


def run_demo_server(settings: DemoSettings, host: str = "127.0.0.1", port: int = 8080) -> None:
    uvicorn.run(create_app(settings), host=host, port=port, log_level="warning", access_log=False)


class ThreadedDemoServer:
    """Run the demo server on a background thread (ephemeral port by default)."""

    def __init__(self, settings: DemoSettings, host: str = "127.0.0.1", port: int = 0) -> None:
        self.settings = settings
        self.host = host
        self.port = port
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> ThreadedDemoServer:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self.host, self.port))
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(
            create_app(self.settings), log_level="warning", access_log=False, lifespan="off"
        )
        server = uvicorn.Server(config)
        self._server = server
        self._thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, name="lt-demo-server", daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline or not self._thread.is_alive():
                raise RuntimeError("demo server failed to start")
            time.sleep(0.01)
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)

    def __enter__(self) -> ThreadedDemoServer:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        port: int = s.getsockname()[1]
        return port


class DemoServerProcess(ThreadedDemoServer):
    """Run the demo server in a child process so it does not share the client's GIL."""

    def __init__(self, settings: DemoSettings, host: str = "127.0.0.1", port: int = 0) -> None:
        super().__init__(settings, host, port)
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> DemoServerProcess:
        if self.port == 0:
            self.port = _free_port(self.host)
        s = self.settings
        # fmt: off
        args: list[str] = [
            sys.executable, "-m", "lt", "--log-level", "WARNING", "demo-server",
            "--host", self.host, "--port", str(self.port), "--rate", repr(s.rate),
            "--window", f"{s.window_s}s", "--algo", s.algo, "--scope", s.scope,
            "--key-header", s.key_header, "--latency-ms", repr(s.latency_ms),
        ]
        # fmt: on
        if s.burst is not None:
            args += ["--burst", str(s.burst)]
        self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 20
        while True:
            if self._proc.poll() is not None:
                raise RuntimeError("demo server process exited during startup")
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2):
                    return self
            except OSError:
                if time.monotonic() > deadline:
                    self.stop()
                    raise RuntimeError("demo server did not start listening") from None
                time.sleep(0.05)

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)

    def __enter__(self) -> DemoServerProcess:
        return self.start()
