from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from fastapi.testclient import TestClient

from apitest.config import Settings
from apitest.main import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(db_url="sqlite://", seed_demo=False))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def live_server(tmp_path) -> Iterator[tuple[str, TestClient]]:
    """A real server so the tool can call its own /demo target over HTTP."""
    port = _free_port()
    app = create_app(Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", port=port))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        with TestClient(app, base_url=base) as c:
            yield base, c
    finally:
        server.should_exit = True
        thread.join(timeout=5)
