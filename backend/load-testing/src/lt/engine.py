"""Run orchestration: scheduler + request workers + metrics + artifacts."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import signal
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from itertools import accumulate
from pathlib import Path
from types import FrameType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from lt.config import Config, SafetyReport, check_safety
from lt.http_client import (
    ClientPool,
    PreparedRoute,
    build_client_pool,
    prepare_routes,
    send_rendered,
    warmup,
)
from lt.logging import JsonFormatter, get_logger, redact
from lt.metrics import (
    AGGREGATE_CSV_COLUMNS,
    FINE_CSV_COLUMNS,
    METRICS_CSV_COLUMNS,
    ROUTES_CSV_COLUMNS,
    EventSink,
    MetricsCollector,
    write_csv,
    write_json,
)
from lt.scenario import Context, DataFeeder, ResponseView, check, safe_path
from lt.scheduler import ArrivalSchedule, run_shards
from lt.thresholds import evaluate as evaluate_thresholds
from lt.utils.time import (
    event_loop_factory,
    high_resolution_timers,
    new_run_id,
    perf_counter,
    utc_now_iso,
)

log = get_logger("engine")

START_DELAY_S = 0.05
# Conservative sustained RPS per client process (httpx is CPU-bound; Windows is slower).
PER_PROCESS_RPS_GUIDE = 700 if sys.platform == "win32" else 1500


@dataclass(slots=True)
class _Job:
    shard: int
    offset: float
    target: float
    fire_time: float
    route: PreparedRoute


@dataclass
class RunnerStats:
    fired: int = 0
    completed: int = 0
    cancelled: int = 0
    iterations: int = 0
    interrupted: bool = False


def collector_for(cfg: Config) -> MetricsCollector:
    t = cfg.thresholds
    return MetricsCollector(apdex_ms=(t.apdex_satisfied_ms, t.apdex_tolerated_ms))


class Runner:
    """Executes a subset of schedule shards inside one event loop."""

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
        self.schedule = ArrivalSchedule(cfg.model.profile)
        self.routes = prepare_routes(cfg)
        self._cum_weights = list(accumulate(r.weight for r in self.routes))
        self._rngs: dict[int, random.Random] = {}
        self._queue: asyncio.Queue[_Job] = asyncio.Queue(maxsize=cfg.http.queue_size)
        self.start = 0.0
        self.stats = RunnerStats()
        self.drain_timeout = cfg.http.connect_timeout + cfg.http.read_timeout + 1.0
        self.feeder = DataFeeder.for_config(cfg)
        self._static_ctx = Context(cfg.variables)

    def _pick_route(self, shard: int) -> PreparedRoute:
        if len(self.routes) == 1:
            return self.routes[0]
        return self._rngs[shard].choices(self.routes, cum_weights=self._cum_weights)[0]

    def _on_fire(self, shard: int, k: int, offset: float, fire_time: float) -> None:
        route = self._pick_route(shard)
        target = self.start + offset
        self.stats.fired += 1
        self.collector.record_attempt(offset, route.name, fire_time - target)
        try:
            self._queue.put_nowait(_Job(shard, offset, target, fire_time, route))
        except asyncio.QueueFull:
            self.collector.record_dropped(offset, route.name)

    def _record_cancelled(self, job: _Job) -> None:
        self.stats.cancelled += 1
        self.collector.record_result(
            job.offset,
            job.route.name,
            None,
            max(self.clock() - job.target, 0.0),
            error_type="Cancelled",
        )

    async def _execute(self, client: httpx.AsyncClient, job: _Job) -> None:
        route = job.route
        ctx = self._static_ctx
        if route.templated:
            ctx = Context(self.cfg.variables, rng=self._rngs.get(job.shard))
            ctx.vars.update(self.feeder.next() or {})
        path, headers, content = route.render(ctx)
        if not safe_path(path):
            self.collector.record_result(
                job.offset, route.name, None, 0.0, error_type="UnsafePath"
            )
            self.stats.completed += 1
            return
        try:
            resp, error = await send_rendered(client, route.method, path, headers, content)
        except asyncio.CancelledError:
            self._record_cancelled(job)
            raise
        # CO-safe: measure from the scheduled time; if fired early, from the actual send.
        latency = self.clock() - min(job.target, job.fire_time)
        status = resp.status_code if resp is not None else None
        expected = status is None or not route.expect_status or status in route.expect_status
        if resp is None:
            self.collector.record_result(
                job.offset, route.name, None, latency, error_type=error, expected=expected
            )
        else:
            view = ResponseView(resp.content, resp.headers) if route.needs_body else None
            self.collector.record_result(
                job.offset,
                route.name,
                status,
                latency,
                headers=resp.headers,
                expected=expected,
                failure=check(route, resp.status_code, latency, view, ctx),
                nbytes=len(resp.content),
            )
        self.stats.completed += 1
        if self.events is not None:
            self.events.offer(
                {
                    "t": round(job.offset, 6),
                    "shard": job.shard,
                    "route": route.name,
                    "status": status,
                    "latency_ms": round(latency * 1000, 3),
                    "error": error,
                }
            )

    async def _worker(self, client: httpx.AsyncClient) -> None:
        queue = self._queue
        while True:
            job = await queue.get()
            try:
                await self._execute(client, job)
            finally:
                queue.task_done()

    async def run(
        self,
        pool: ClientPool,
        *,
        start: float,
        shard_ids: Iterable[int],
        n_shards: int,
        stop: asyncio.Event,
    ) -> RunnerStats:
        self.start = start
        shard_list = list(shard_ids)
        for s in shard_list:
            self._rngs[s] = random.Random(self.cfg.model.seed * 1_000_003 + s)
        workers = [
            asyncio.create_task(self._worker(pool.for_worker(i)))
            for i in range(self.cfg.http.effective_concurrency)
        ]
        sched = asyncio.create_task(
            run_shards(
                self.schedule,
                shard_ids=shard_list,
                n_shards=n_shards,
                start=start,
                on_fire=self._on_fire,
                stop=stop,
                clock=self.clock,
            )
        )
        stop_wait = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait({sched, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
            if stop.is_set():
                self.stats.interrupted = True
            else:
                drain = asyncio.create_task(self._queue.join())
                await asyncio.wait(
                    {drain, stop_wait},
                    timeout=self.drain_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                drain.cancel()
                self.stats.interrupted = stop.is_set()
        finally:
            for task in (sched, stop_wait, *workers):
                task.cancel()
            await asyncio.gather(sched, stop_wait, *workers, return_exceptions=True)
            while not self._queue.empty():
                self._record_cancelled(self._queue.get_nowait())
        return self.stats


def install_stop_handlers(on_stop: Callable[[], None]) -> Callable[[], None]:
    """First SIGINT/SIGTERM requests a graceful stop; a second one aborts immediately."""
    presses = 0

    def handler(signum: int, frame: FrameType | None) -> None:
        nonlocal presses
        presses += 1
        if presses > 1:
            raise KeyboardInterrupt
        log.warning("stop requested; finishing up (press Ctrl-C again to abort)")
        on_stop()

    previous: dict[int, Any] = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError):  # not main thread / unsupported
            previous[sig] = signal.signal(sig, handler)

    def restore() -> None:
        for sig, prev in previous.items():
            signal.signal(sig, prev)

    return restore


@dataclass
class RunInfo:
    started_at: str
    finished_at: str = ""
    elapsed_s: float = 0.0
    interrupted: bool = False
    fired: int = 0
    completed: int = 0
    cancelled: int = 0
    events_written: int = 0
    events_dropped: int = 0
    processes: int = 1
    snapshot_backpressure: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _strip_userinfo(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password:
        netloc = parts.hostname or ""
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit(parts._replace(netloc=netloc))
    return url


def redacted_config(cfg: Config) -> dict[str, Any]:
    data = cfg.model_dump(mode="json")
    data["base_url"] = _strip_userinfo(data["base_url"])
    result: dict[str, Any] = redact(data)
    return result


class ArtifactWriter:
    """Writes per-second snapshots during the run and the final artifact set."""

    def __init__(self, cfg: Config, run_dir: Path, run_id: str) -> None:
        self.cfg = cfg
        self.run_dir = run_dir
        self.run_id = run_id
        self.schedule = ArrivalSchedule(cfg.model.profile)
        self.planned_s = cfg.model.total_duration
        self.grace_s = cfg.http.connect_timeout + cfg.http.read_timeout + 2.0
        self._last_logged = -1

    def snapshot(self, collector: MetricsCollector, elapsed: float) -> None:
        collector.finalize_before(max(int(elapsed - self.grace_s), 0))
        done = collector.finalized_until
        rows = collector.metric_rows(self.planned_s)[:done]
        write_csv(self.run_dir / "metrics.csv", METRICS_CSV_COLUMNS, rows)
        sec = int(elapsed) - 1
        if sec > self._last_logged and sec in collector.windows:
            self._last_logged = sec
            w = collector.windows[sec]
            log.info(
                "progress",
                extra={
                    "second": sec,
                    "attempted": w.attempted,
                    "accepted": w.accepted,
                    "rate_limited": w.s429,
                    "errors": w.errors,
                    "failed": w.failed,
                    "vus": w.vus,
                },
            )

    def finalize(self, collector: MetricsCollector, info: RunInfo) -> dict[str, Any]:
        closed = self.cfg.model.is_closed
        planned = self.planned_s
        collector.finalize_before(collector.n_seconds(planned) + 1)
        # Closed runs may finish early (loop counts or data exhausted).
        early = info.interrupted or closed
        duration = min(info.elapsed_s, planned) if early else planned
        duration = max(duration, 1e-9)
        rows = collector.metric_rows(duration)
        write_csv(self.run_dir / "metrics.csv", METRICS_CSV_COLUMNS, rows)
        write_csv(self.run_dir / "routes.csv", ROUTES_CSV_COLUMNS, collector.route_rows())
        write_csv(self.run_dir / "fine.csv", FINE_CSV_COLUMNS, collector.fine_rows())
        aggregate = collector.aggregate_rows(duration)
        write_csv(self.run_dir / "aggregate.csv", AGGREGATE_CSV_COLUMNS, aggregate)
        thresholds = evaluate_thresholds(self.cfg.thresholds, aggregate)
        vus_peak = max((r["vus"] for r in rows), default=0)
        totals = collector.totals()
        means = {
            "attempted_rps": round(totals["attempted"] / duration, 3),
            "accepted_rps": round(totals["accepted"] / duration, 3),
            "429_rps": round(totals["429"] / duration, 3),
            "error_rps": round(totals["errors"] / duration, 3),
        }
        accuracy = self._scheduler_accuracy(collector, duration)
        latency = collector.overall.summary_ms()
        by_family = {k: v.summary_ms() for k, v in sorted(collector.families.items())}
        profile = [
            {
                "index": s.index,
                "start_s": s.start,
                "duration_s": s.duration,
                "rate": s.rate_start,
                "end_rate": s.rate_end,
                "expected_events": round(s.count, 3),
            }
            for s in self.schedule.segments
        ]
        h = self.cfg.http
        metrics = {
            "run_id": self.run_id,
            "name": self.cfg.name,
            "started_at": info.started_at,
            "finished_at": info.finished_at,
            "interrupted": info.interrupted,
            "duration_s": round(duration, 3),
            "planned_duration_s": planned,
            "planned_events": round(self.schedule.total_events, 3),
            "profile": profile,
            "totals": totals,
            "means": means,
            "latency_ms": latency,
            "latency_by_family_ms": by_family,
            "status_codes": dict(sorted(collector.status_codes.items())),
            "error_types": dict(collector.error_types.most_common()),
            "routes": collector.route_totals(),
            "headers": collector.header_summary(),
            "scheduler": accuracy,
            "model": self._model_info(vus_peak, info),
            "aggregate": aggregate,
            "failures": collector.failure_summary(),
            "thresholds": thresholds,
            "client": {
                "processes": info.processes,
                "shards": self.cfg.model.workers,
                "concurrency_per_process": h.effective_concurrency,
                "http2": h.http2,
                "max_connections": h.max_connections,
                "max_streams": h.max_streams,
            },
            "execution": {
                "fired": info.fired,
                "completed": info.completed,
                "cancelled": info.cancelled,
                "late_latency_samples": collector.late_samples,
                "snapshot_backpressure": info.snapshot_backpressure,
                **info.extra,
            },
            "events": {
                "sample_rate": self.cfg.output.events_sample_rate,
                "written": info.events_written,
                "dropped": info.events_dropped,
            },
        }
        write_json(self.run_dir / "metrics.json", metrics)
        attempted = totals["attempted"] or 1
        summary = {
            "run_id": self.run_id,
            "name": self.cfg.name,
            "base_url": _strip_userinfo(self.cfg.base_url),
            "started_at": info.started_at,
            "finished_at": info.finished_at,
            "interrupted": info.interrupted,
            "duration_s": round(duration, 3),
            "totals": totals,
            "means": means,
            "ratios": {
                "accepted": round(totals["accepted"] / attempted, 4),
                "429": round(totals["429"] / attempted, 4),
                "errors": round(totals["errors"] / attempted, 4),
            },
            "latency_ms": {k: latency[k] for k in ("p50", "p90", "p95", "p99", "max", "mean")},
            "scheduler": {
                "rate_error_pct": accuracy["rate_error_pct"],
                "mean_abs_window_error_pct": accuracy["mean_abs_window_error_pct"],
                "lag_p99_ms": accuracy["lag_ms"]["p99"],
            },
            "status_codes": metrics["status_codes"],
            "model": metrics["model"],
            "aggregate_total": aggregate[-1],
            "thresholds": thresholds,
        }
        write_json(self.run_dir / "summary.json", summary)
        return summary

    def _model_info(self, vus_peak: int, info: RunInfo) -> dict[str, Any]:
        m = self.cfg.model
        if not m.is_closed:
            return {"type": "open", "peak_rps": m.peak_rate}
        return {
            "type": "closed",
            "peak_users": m.peak_users,
            "vus_peak": vus_peak,
            "stages": [{"duration_s": s.duration, "users": s.users} for s in m.stages],
            "iterations_per_user": m.iterations,
            "iterations_completed": info.extra.get("iterations", 0),
            "max_rps": m.max_rps,
            "think_time": m.think_time,
        }

    def _scheduler_accuracy(self, collector: MetricsCollector, duration: float) -> dict[str, Any]:
        errors: list[float] = []
        for sec in range(int(duration)):
            expected = self.schedule.expected_between(sec, sec + 1)
            if expected >= 1:
                w = collector.windows.get(sec)
                actual = w.attempted if w else 0
                errors.append((actual - expected) / expected * 100)
        expected_total = self.schedule.expected_between(0, duration)
        attempted = collector.totals()["attempted"]
        rate_error = (attempted - expected_total) / expected_total * 100 if expected_total else 0.0
        return {
            "expected_attempts": round(expected_total, 3),
            "actual_attempts": attempted,
            "rate_error_pct": round(rate_error, 3),
            "mean_abs_window_error_pct": (
                round(sum(abs(e) for e in errors) / len(errors), 3) if errors else 0.0
            ),
            "max_abs_window_error_pct": round(max((abs(e) for e in errors), default=0.0), 3),
            "lag_ms": collector.lag.summary_ms(),
        }


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    summary: dict[str, Any]
    interrupted: bool


async def _flush_loop(
    writer: ArtifactWriter,
    get_collector: Callable[[], MetricsCollector],
    start: float,
    events: EventSink | None,
    interval: float,
) -> None:
    while True:
        await asyncio.sleep(interval)
        writer.snapshot(get_collector(), perf_counter() - start)
        if events is not None:
            events.flush()


async def _run_in_process(
    cfg: Config,
    writer: ArtifactWriter,
    info: RunInfo,
    transport: httpx.AsyncBaseTransport | None,
) -> MetricsCollector:
    collector = collector_for(cfg)
    events = (
        EventSink(writer.run_dir / "events.jsonl", cfg.output.events_sample_rate, cfg.model.seed)
        if cfg.output.events_sample_rate > 0
        else None
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        loop.call_soon_threadsafe(stop.set)

    restore = install_stop_handlers(request_stop)
    try:
        async with build_client_pool(cfg, transport) as pool:
            warmed = await warmup(pool, cfg)
            if warmed:
                log.info("warmup complete", extra={"responses": warmed})
            runner = make_runner(cfg, collector, events=events)
            start = perf_counter() + START_DELAY_S
            flusher = asyncio.create_task(
                _flush_loop(writer, lambda: collector, start, events, cfg.output.flush_interval)
            )
            shards = cfg.model.workers if not cfg.model.is_closed else 1
            try:
                stats = await runner.run(
                    pool,
                    start=start,
                    shard_ids=range(shards),
                    n_shards=shards,
                    stop=stop,
                )
            finally:
                flusher.cancel()
                await asyncio.gather(flusher, return_exceptions=True)
            info.elapsed_s = perf_counter() - start
    finally:
        restore()
    if events is not None:
        events.flush()
        info.events_written, info.events_dropped = events.written, events.dropped
    info.fired, info.completed, info.cancelled = stats.fired, stats.completed, stats.cancelled
    info.interrupted = stats.interrupted
    if cfg.model.is_closed:
        info.extra["iterations"] = stats.iterations
    return collector


def make_runner(
    cfg: Config, collector: MetricsCollector, *, events: EventSink | None = None
) -> Any:
    """``Runner`` (open model) or ``VuRunner`` (closed model); both share one interface."""
    if cfg.model.is_closed:
        from lt.vu import VuRunner

        return VuRunner(cfg, collector, events=events)
    return Runner(cfg, collector, events=events)


def run_load(
    cfg: Config,
    *,
    output_dir: Path = Path("runs"),
    run_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RunResult:
    """Validate guardrails, execute the profile, and write all run artifacts."""
    report = check_safety(cfg)
    for warning in report.warnings:
        log.warning(warning)
    per_process = cfg.model.peak_rate / cfg.model.processes
    if not cfg.model.is_closed and per_process > PER_PROCESS_RPS_GUIDE:
        log.warning(
            "per-process rate exceeds typical single-process httpx capacity; "
            "if scheduler lag or latency grows, add processes (see docs/SCALING.md)",
            extra={
                "per_process_rps": per_process,
                "guide_rps": PER_PROCESS_RPS_GUIDE,
                "suggested_processes": math.ceil(cfg.model.peak_rate / PER_PROCESS_RPS_GUIDE),
            },
        )
    run_id = run_id or new_run_id()
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    root = logging.getLogger("lt")
    root.addHandler(file_handler)
    try:
        return _run(cfg, report, run_id, run_dir, transport)
    finally:
        root.removeHandler(file_handler)
        file_handler.close()


def _run(
    cfg: Config,
    report: SafetyReport,
    run_id: str,
    run_dir: Path,
    transport: httpx.AsyncBaseTransport | None,
) -> RunResult:
    write_json(run_dir / "config.json", redacted_config(cfg))
    writer = ArtifactWriter(cfg, run_dir, run_id)
    info = RunInfo(started_at=utc_now_iso(), processes=cfg.model.processes)
    log.info(
        "run starting",
        extra={
            "run_id": run_id,
            "run_dir": str(run_dir),
            "host": report.host,
            "peak_rps": report.peak_rate,
            "rps_cap": report.effective_cap,
            "duration_s": cfg.model.total_duration,
            "shards": cfg.model.workers,
            "processes": cfg.model.processes,
            "http2": cfg.http.http2,
        },
    )
    if cfg.model.processes > 1:
        from lt.mp import run_multiprocess

        collector = run_multiprocess(cfg, writer, info)
    else:
        with (
            high_resolution_timers(),
            asyncio.Runner(loop_factory=event_loop_factory(cfg.model.use_uvloop)) as loop_runner,
        ):
            collector = loop_runner.run(_run_in_process(cfg, writer, info, transport))
    info.finished_at = utc_now_iso()
    summary = writer.finalize(collector, info)
    log.info("run finished", extra={"run_id": run_id, **asdict(info)})
    return RunResult(run_id, run_dir, summary, info.interrupted)
