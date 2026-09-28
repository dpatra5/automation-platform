from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from lt.config import Config, parse_config
from lt.demo_server import DemoServerProcess, DemoSettings, ThreadedDemoServer


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-slow", action="store_true", help="run slow performance tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow") or os.environ.get("LT_RUN_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="slow test; use --run-slow or LT_RUN_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def make_config(base_url: str = "http://127.0.0.1:9", **overrides: Any) -> Config:
    data: dict[str, Any] = {
        "base_url": base_url,
        "safety": {"allowlist": ["127.0.0.1", "localhost"], "max_rps_cap": 5000},
        "model": {"workers": 2, "profile": [{"duration": "1s", "rate": 50}]},
        "http": {"max_connections": 8, "concurrency": 32, "read_timeout": "5s"},
        "routes": [{"name": "items", "path": "/api/items"}],
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return parse_config(data)


@pytest.fixture
def config_factory() -> Callable[..., Config]:
    return make_config


@pytest.fixture
def demo_server() -> Iterator[Callable[[DemoSettings], ThreadedDemoServer]]:
    """Start demo servers on ephemeral ports (in-thread by default; LT_IT_SERVER=process)."""
    servers: list[ThreadedDemoServer] = []
    cls = DemoServerProcess if os.environ.get("LT_IT_SERVER") == "process" else ThreadedDemoServer

    def start(settings: DemoSettings) -> ThreadedDemoServer:
        server = cls(settings).start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.stop()
