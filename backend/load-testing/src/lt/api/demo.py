"""Lifecycle of a single local demo server (always bound to loopback)."""

from __future__ import annotations

import threading
from typing import Any

import httpx

from lt.api.schemas import DemoServerRequest, DemoServerState
from lt.demo_server import DemoServerProcess, DemoSettings
from lt.utils.time import parse_duration

DEMO_HOST = "127.0.0.1"


class DemoConflict(RuntimeError):
    pass


class DemoManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: DemoServerProcess | None = None
        self._request: DemoServerRequest | None = None

    def _alive(self) -> DemoServerProcess | None:
        if self._server is not None and not self._server.running:
            self._server, self._request = None, None
        return self._server

    def state(self) -> DemoServerState:
        with self._lock:
            server = self._alive()
            if server is None:
                return DemoServerState(running=False)
            return DemoServerState(running=True, base_url=server.base_url, settings=self._request)

    def start(self, req: DemoServerRequest) -> DemoServerState:
        settings = DemoSettings(
            rate=req.rate,
            burst=req.burst,
            window_s=parse_duration(req.window),
            algo=req.algo,
            scope=req.scope,
            key_header=req.key_header,
            latency_ms=req.latency_ms,
        )
        with self._lock:
            if self._alive() is not None:
                raise DemoConflict("demo server is already running")
            server = DemoServerProcess(settings, DEMO_HOST, req.port)
            try:
                server.start()
            except RuntimeError as exc:
                raise DemoConflict(f"{exc} (is port {req.port} already in use?)") from exc
            self._server, self._request = server, req.model_copy(update={"port": server.port})
            return DemoServerState(running=True, base_url=server.base_url, settings=self._request)

    def stop(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.stop()
            self._server, self._request = None, None

    async def stats(self) -> dict[str, Any]:
        with self._lock:
            server = self._alive()
            base_url = server.base_url if server else None
        if base_url is None:
            raise DemoConflict("demo server is not running")
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            resp = await client.get("/__stats")
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data
