"""Multiprocessing sharding: N worker processes, one aggregator (the parent).

Each child owns a disjoint subset of scheduler shards, runs its own event loop and HTTP
client, and ships *delta* metric snapshots to the parent over a bounded queue. When the
queue is full the child keeps accumulating locally and retries on the next flush, so
backpressure never loses data and never blocks the child's scheduler.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import queue as queue_mod
import signal
import time
import traceback
from dataclasses import asdict
from multiprocessing.queues import Queue
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import Any

from lt.config import Config
from lt.engine import ArtifactWriter, RunInfo, Runner, install_stop_handlers
from lt.http_client import build_client_pool, warmup
from lt.logging import get_logger
from lt.metrics import EventSink, MetricsCollector
from lt.utils.time import event_loop_factory, high_resolution_timers, perf_counter

log = get_logger("mp")

START_LEAD_S = 0.5
READY_TIMEOUT_S = 120.0
POLL_S = 0.1

Message = tuple[str, int, Any]


def shard_sets(n_shards: int, processes: int) -> list[list[int]]:
    return [list(range(i, n_shards, processes)) for i in range(processes)]


async def _child_async(
    idx: int,
    cfg: Config,
    shard_ids: list[int],
    q: Queue[Message],
    stop_ev: Event,
    go_ev: Event,
    start_wall: Synchronized[float],
    run_dir: Path,
) -> None:
    sample_rate = cfg.output.events_sample_rate
    events = (
        EventSink(run_dir / f"events-p{idx}.jsonl", sample_rate, cfg.model.seed + idx)
        if sample_rate > 0
        else None
    )
    runner = Runner(cfg, MetricsCollector(), events=events)
    stop = asyncio.Event()
    backpressure = 0
    loop = asyncio.get_running_loop()

    async def pump() -> None:
        nonlocal backpressure
        last = perf_counter()
        while True:
            await asyncio.sleep(POLL_S)
            if stop_ev.is_set():
                stop.set()
            if perf_counter() - last < cfg.output.flush_interval:
                continue
            last = perf_counter()
            try:
                q.put_nowait(("delta", idx, runner.collector.to_state()))
                runner.collector = MetricsCollector()
            except queue_mod.Full:
                backpressure += 1
            if events is not None:
                events.flush()

    async with build_client_pool(cfg) as pool:
        await warmup(pool, cfg)
        q.put(("ready", idx, None))
        await loop.run_in_executor(None, go_ev.wait)
        start = perf_counter() + (start_wall.value - time.time())
        pump_task = asyncio.create_task(pump())
        try:
            stats = await runner.run(
                pool, start=start, shard_ids=shard_ids, n_shards=cfg.model.workers, stop=stop
            )
        finally:
            pump_task.cancel()
            await asyncio.gather(pump_task, return_exceptions=True)
    if events is not None:
        events.flush()
    payload = {
        "state": runner.collector.to_state(),
        "stats": asdict(stats),
        "backpressure": backpressure,
        "events_written": events.written if events else 0,
        "events_dropped": events.dropped if events else 0,
    }
    q.put(("done", idx, payload), timeout=60)


def _child_main(
    idx: int,
    cfg_data: dict[str, Any],
    shard_ids: list[int],
    q: Queue[Message],
    stop_ev: Event,
    go_ev: Event,
    start_wall: Synchronized[float],
    run_dir: str,
) -> None:
    # The parent owns Ctrl-C handling and forwards it through stop_ev.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        cfg = Config.model_validate(cfg_data)
        with (
            high_resolution_timers(),
            asyncio.Runner(loop_factory=event_loop_factory(cfg.model.use_uvloop)) as runner,
        ):
            runner.run(
                _child_async(idx, cfg, shard_ids, q, stop_ev, go_ev, start_wall, Path(run_dir))
            )
    except BaseException:
        q.put(("error", idx, traceback.format_exc()), timeout=10)
        raise


def run_multiprocess(cfg: Config, writer: ArtifactWriter, info: RunInfo) -> MetricsCollector:
    ctx = mp.get_context("spawn")
    n_proc = cfg.model.processes
    q: Queue[Message] = ctx.Queue(maxsize=n_proc * 16)
    stop_ev = ctx.Event()
    go_ev = ctx.Event()
    start_wall: Synchronized[float] = ctx.Value("d", 0.0)
    cfg_data = cfg.model_dump(mode="python")
    procs = [
        ctx.Process(
            target=_child_main,
            args=(i, cfg_data, shards, q, stop_ev, go_ev, start_wall, str(writer.run_dir)),
            name=f"lt-worker-{i}",
            daemon=True,
        )
        for i, shards in enumerate(shard_sets(cfg.model.workers, n_proc))
    ]
    collector = MetricsCollector()
    finished: set[int] = set()
    restore = install_stop_handlers(stop_ev.set)
    start_perf = perf_counter()
    try:
        for p in procs:
            p.start()
        ready: set[int] = set()
        deadline = time.monotonic() + READY_TIMEOUT_S
        while len(ready) < n_proc:
            if time.monotonic() > deadline:
                raise RuntimeError("timed out waiting for worker processes to start")
            if stop_ev.is_set():
                break
            try:
                kind, idx, payload = q.get(timeout=POLL_S)
            except queue_mod.Empty:
                dead = [p.name for p in procs if not p.is_alive()]
                if dead:
                    raise RuntimeError(
                        f"worker process(es) exited during startup: {dead}"
                    ) from None
                continue
            if kind == "ready":
                ready.add(idx)
            elif kind == "error":
                raise RuntimeError(f"worker {idx} failed during startup:\n{payload}")
        start_wall.value = time.time() + START_LEAD_S
        start_perf = perf_counter() + START_LEAD_S
        go_ev.set()
        log.info("workers started", extra={"processes": n_proc})
        drain_s = cfg.http.connect_timeout + cfg.http.read_timeout
        hard_deadline = start_perf + cfg.model.total_duration + drain_s + 30.0
        last_snapshot = perf_counter()
        while len(finished) < n_proc:
            try:
                kind, idx, payload = q.get(timeout=POLL_S)
            except queue_mod.Empty:
                kind = ""
                for i, p in enumerate(procs):
                    if i not in finished and not p.is_alive():
                        log.error("worker exited unexpectedly", extra={"worker": i})
                        finished.add(i)
            if kind == "delta":
                collector.merge_state(payload)
            elif kind == "done":
                collector.merge_state(payload["state"])
                stats = payload["stats"]
                info.fired += stats["fired"]
                info.completed += stats["completed"]
                info.cancelled += stats["cancelled"]
                info.interrupted = info.interrupted or stats["interrupted"]
                info.snapshot_backpressure += payload["backpressure"]
                info.events_written += payload["events_written"]
                info.events_dropped += payload["events_dropped"]
                finished.add(idx)
            elif kind == "error":
                log.error("worker failed", extra={"worker": idx, "traceback": payload})
                finished.add(idx)
            now = perf_counter()
            if now - last_snapshot >= cfg.output.flush_interval:
                last_snapshot = now
                writer.snapshot(collector, now - start_perf)
            if now > hard_deadline and not stop_ev.is_set():
                log.error("workers exceeded the hard deadline; stopping")
                stop_ev.set()
            if now > hard_deadline + 15:
                break
    finally:
        restore()
        stop_ev.set()
        go_ev.set()
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
    info.elapsed_s = perf_counter() - start_perf
    info.interrupted = info.interrupted or len(finished) < n_proc
    info.extra["workers_finished"] = len(finished)
    return collector
