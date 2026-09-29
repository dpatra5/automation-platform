"""Closed-model runner: virtual users run the route list in order (a JMeter Thread Group).

Process ``part`` of ``parts`` owns virtual users ``part, part + parts, ...`` so ramps stay
exact when the load is spread over several processes. Users are started and retired to
follow the stage targets; a retired user finishes its current iteration first, while the
end of the test (or a stop) lets each user finish only its in-flight request.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Callable, Iterable

import httpx

from lt.config import Config
from lt.engine import RunnerStats
from lt.http_client import ClientPool, send_rendered
from lt.metrics import EventSink, MetricsCollector
from lt.scenario import (
    Context,
    DataFeeder,
    Pacer,
    PreparedRoute,
    ResponseView,
    check,
    extract,
    prepare_routes,
    safe_path,
    think_seconds,
)
from lt.utils.time import perf_counter

CONTROL_INTERVAL_S = 0.1


class VuRunner:
    def __init__(
        self,
        cfg: Config,
        collector: MetricsCollector,
        *,
        events: EventSink | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self.cfg = cfg
        self.collector = collector
        self.events = events
        self.clock = clock
        self.routes = prepare_routes(cfg)
        self.stats = RunnerStats()
        self.start = 0.0
        self.drain_timeout = cfg.http.connect_timeout + cfg.http.read_timeout + 1.0
        self._ending = asyncio.Event()
        self._data_exhausted = False

    async def _pause(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._ending.wait(), timeout=seconds)

    async def _request(
        self,
        client: httpx.AsyncClient,
        route: PreparedRoute,
        ctx: Context,
        cookies: httpx.Cookies | None,
    ) -> None:
        path, headers, content = route.render(ctx)
        offset = self.clock() - self.start
        self.collector.record_attempt(offset, route.name, 0.0)
        self.stats.fired += 1
        if not safe_path(path):
            self.collector.record_result(
                offset, route.name, None, 0.0, error_type="UnsafePath",
                failure="rendered path is not relative to base_url",
            )  # fmt: skip
            self.stats.completed += 1
            return
        sent = self.clock()
        try:
            resp, error = await send_rendered(client, route.method, path, headers, content, cookies)
        except asyncio.CancelledError:
            self.stats.cancelled += 1
            self.collector.record_result(
                offset, route.name, None, max(self.clock() - sent, 0.0), error_type="Cancelled"
            )
            raise
        latency = self.clock() - sent
        self.stats.completed += 1
        if resp is None:
            self.collector.record_result(offset, route.name, None, latency, error_type=error)
            self._event(offset, route.name, None, latency, error, ctx)
            return
        view = ResponseView(resp.content, resp.headers)
        failure = check(route, resp.status_code, latency, view, ctx)
        if route.extractors:
            values, missing = extract(route, view)
            ctx.vars.update(values)
            if missing and failure is None:
                failure = f"extractor matched nothing: {', '.join(missing)}"
        self.collector.record_result(
            offset,
            route.name,
            resp.status_code,
            latency,
            headers=resp.headers,
            expected=not route.expect_status or resp.status_code in route.expect_status,
            failure=failure,
            nbytes=len(resp.content),
        )
        self._event(offset, route.name, resp.status_code, latency, failure, ctx)

    def _event(
        self,
        offset: float,
        route: str,
        status: int | None,
        latency: float,
        error: str | None,
        ctx: Context,
    ) -> None:
        if self.events is not None:
            self.events.offer(
                {
                    "t": round(offset, 6),
                    "vu": ctx.vu,
                    "iteration": ctx.iteration,
                    "route": route,
                    "status": status,
                    "latency_ms": round(latency * 1000, 3),
                    "error": error,
                }
            )

    async def _user(
        self,
        number: int,
        client: httpx.AsyncClient,
        retire: asyncio.Event,
        pacer: Pacer,
        feeder: DataFeeder,
    ) -> bool:
        """Run iterations until retired; True when the user is used up (loops or data)."""
        cfg = self.cfg
        rng = random.Random(cfg.model.seed * 1_000_003 + number)
        ctx = Context(cfg.variables, vu=number, rng=rng)
        cookies = httpx.Cookies() if cfg.http.cookies else None
        limit = cfg.model.iterations
        while not retire.is_set() and not self._ending.is_set():
            if limit is not None and ctx.iteration >= limit:
                return True
            row = feeder.next()
            if row is None:
                self._data_exhausted = True
                return True
            ctx.vars.update(row)
            ctx.iteration += 1
            for route in self.routes:
                await pacer.wait()
                if self._ending.is_set():
                    return False
                await self._request(client, route, ctx, cookies)
                pause = think_seconds(route.think, rng)
                if pause > 0:
                    await self._pause(pause)
                if self._ending.is_set():
                    return False
            self.stats.iterations += 1
        return False

    async def run(
        self,
        pool: ClientPool,
        *,
        start: float,
        shard_ids: Iterable[int],
        n_shards: int,
        stop: asyncio.Event,
    ) -> RunnerStats:
        model = self.cfg.model
        part, parts = next(iter(shard_ids), 0), max(n_shards, 1)
        self.start = start
        cap = float(self.cfg.safety.max_rps_cap)
        rate = min(model.max_rps, cap) if model.max_rps else cap
        pacer = Pacer(rate / parts, self.clock)
        feeder = DataFeeder.for_config(self.cfg, part, parts)
        end = start + model.total_duration

        def local(target: int) -> int:
            return 0 if target <= part else (target - part + parts - 1) // parts

        users: dict[int, tuple[asyncio.Task[bool], asyncio.Event]] = {}
        used_up: set[int] = set()
        peak = local(model.peak_users)

        def reap() -> None:
            for k, (task, _) in list(users.items()):
                if task.done():
                    if not task.cancelled() and task.exception() is None and task.result():
                        used_up.add(k)
                    del users[k]

        delay = start - self.clock()
        if delay > 0:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
        try:
            while not stop.is_set():
                now = self.clock()
                if now >= end:
                    break
                reap()
                # Local user k exists while k < target; finished users are not replaced.
                target = local(model.users_at(now - start))
                for k in range(target):
                    if k in used_up or self._data_exhausted:
                        continue
                    if k in users:
                        users[k][1].clear()
                        continue
                    retire = asyncio.Event()
                    number = part + k * parts + 1
                    task = asyncio.create_task(
                        self._user(number, pool.for_worker(k), retire, pacer, feeder)
                    )
                    users[k] = (task, retire)
                for k, (_, retire) in users.items():
                    if k >= target:
                        retire.set()
                self.collector.record_vus(int(now - start), len(users))
                if not users and (self._data_exhausted or len(used_up) >= peak):
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=CONTROL_INTERVAL_S)
        finally:
            self.stats.interrupted = stop.is_set()
            self._ending.set()
            tasks = [task for task, _ in users.values()]
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=self.drain_timeout)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        return self.stats
