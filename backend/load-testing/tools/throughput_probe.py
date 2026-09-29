"""Closed-loop throughput probe: how many req/s can this host's client + demo server do?

Usage: python tools/throughput_probe.py [--concurrency 64] [--seconds 3] [--url URL]
Without --url a demo server is started in a child process.
"""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx

from lt.demo_server import DemoServerProcess, DemoSettings


async def probe(url: str, concurrency: int, seconds: float, http2: bool) -> None:
    done = 0
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(base_url=url, limits=limits, http2=http2) as client:
        deadline = time.perf_counter() + seconds

        async def worker() -> None:
            nonlocal done
            while time.perf_counter() < deadline:
                await client.get("/api/items")
                done += 1

        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        elapsed = time.perf_counter() - t0
    print(f"{done} requests in {elapsed:.2f}s -> {done / elapsed:,.0f} req/s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--concurrency", type=int, default=64)
    p.add_argument("--seconds", type=float, default=3.0)
    p.add_argument("--url")
    p.add_argument("--http2", action="store_true")
    a = p.parse_args()
    if a.url:
        asyncio.run(probe(a.url, a.concurrency, a.seconds, a.http2))
        return
    with DemoServerProcess(DemoSettings(rate=1e9, burst=10**9)) as srv:
        asyncio.run(probe(srv.base_url, a.concurrency, a.seconds, a.http2))


if __name__ == "__main__":
    main()
