from __future__ import annotations

import asyncio
import time
from itertools import pairwise

import pytest

from lt.config import ProfileStep
from lt.scheduler import ArrivalSchedule, run_shard, run_shards


def steps(*specs: tuple[float, float] | tuple[float, float, float]) -> list[ProfileStep]:
    out = []
    for spec in specs:
        end = spec[2] if len(spec) == 3 else None
        out.append(ProfileStep(duration=spec[0], rate=spec[1], end_rate=end))
    return out


def test_constant_schedule_is_evenly_spaced() -> None:
    sched = ArrivalSchedule(steps((1.0, 100.0)))
    offsets = [t for _, t in sched.iter_offsets()]
    assert len(offsets) == 100
    assert offsets[0] == 0.0
    gaps = {round(b - a, 9) for a, b in pairwise(offsets)}
    assert gaps == {0.01}
    assert sched.total_events == pytest.approx(100)


def test_ramp_schedule_counts_and_monotonic() -> None:
    sched = ArrivalSchedule(steps((10.0, 0.0, 100.0)))
    offsets = [t for _, t in sched.iter_offsets()]
    assert len(offsets) == 500
    assert all(b > a for a, b in pairwise(offsets))
    assert offsets[-1] < 10.0
    # Rate grows linearly: the second half holds ~3x the events of the first half.
    first_half = sum(1 for t in offsets if t < 5)
    assert first_half == pytest.approx(125, abs=1)


def test_ramp_down_schedule() -> None:
    sched = ArrivalSchedule(steps((2.0, 100.0, 0.0)))
    offsets = [t for _, t in sched.iter_offsets()]
    assert len(offsets) == 100
    assert sum(1 for t in offsets if t < 1) == pytest.approx(75, abs=1)


def test_idle_segment_produces_no_events() -> None:
    sched = ArrivalSchedule(steps((2.0, 0.0), (1.0, 10.0)))
    offsets = [t for _, t in sched.iter_offsets()]
    assert len(offsets) == 10
    assert offsets[0] == pytest.approx(2.0)
    assert sched.segment_at(0.5) is not None and sched.segment_at(0.5).is_idle  # type: ignore[union-attr]
    assert sched.segment_at(99) is None


def test_shards_interleave_to_global_schedule() -> None:
    sched = ArrivalSchedule(steps((1.0, 200.0), (1.0, 50.0, 300.0)))
    single = sorted(t for _, t in sched.iter_offsets())
    merged = sorted(t for s in range(3) for _, t in sched.iter_offsets(s, 3))
    assert merged == single
    shard0 = [k for k, _ in sched.iter_offsets(0, 3)]
    assert all(k % 3 == 0 for k in shard0)


def test_time_of_and_expected_between() -> None:
    sched = ArrivalSchedule(steps((1.0, 100.0), (1.0, 200.0)))
    assert sched.time_of(50) == pytest.approx(0.5)
    assert sched.time_of(200) == pytest.approx(1.5)
    assert sched.time_of(10_000) == sched.total_duration
    assert sched.expected_between(0, 1) == pytest.approx(100)
    assert sched.expected_between(0.5, 1.5) == pytest.approx(150)


def test_invalid_shard_rejected() -> None:
    sched = ArrivalSchedule(steps((1.0, 10.0)))
    with pytest.raises(ValueError):
        list(sched.iter_offsets(3, 2))


async def test_scheduler_fires_expected_count_in_real_time() -> None:
    sched = ArrivalSchedule(steps((1.0, 100.0)))
    fired: list[float] = []
    start = time.perf_counter() + 0.02
    n = await run_shards(
        sched,
        shard_ids=[0, 1],
        n_shards=2,
        start=start,
        on_fire=lambda s, k, off, ft: fired.append(ft - (start + off)),
        stop=asyncio.Event(),
    )
    assert n == len(fired) >= 95
    assert time.perf_counter() - start >= 0.95


async def test_behind_schedule_fires_all_without_skipping() -> None:
    sched = ArrivalSchedule(steps((1.0, 1000.0)))
    fired = 0

    def on_fire(shard: int, k: int, offset: float, fire_time: float) -> None:
        nonlocal fired
        fired += 1

    # Clock is 10 s past the start: every event is late and must still fire.
    n = await run_shard(
        sched,
        shard=0,
        n_shards=1,
        start=0.0,
        on_fire=on_fire,
        stop=asyncio.Event(),
        clock=lambda: 10.0,
    )
    assert n == fired == 1000


async def test_stop_event_halts_scheduling() -> None:
    sched = ArrivalSchedule(steps((10.0, 10.0)))
    stop = asyncio.Event()
    start = time.perf_counter()
    task = asyncio.create_task(
        run_shard(sched, shard=0, n_shards=1, start=start, on_fire=lambda *a: None, stop=stop)
    )
    await asyncio.sleep(0.25)
    stop.set()
    fired = await asyncio.wait_for(task, 1.0)
    assert 1 <= fired <= 5


async def test_stop_before_fire() -> None:
    sched = ArrivalSchedule(steps((1.0, 10.0)))
    stop = asyncio.Event()
    stop.set()
    fired = await run_shard(
        sched, shard=0, n_shards=1, start=0.0, on_fire=lambda *a: None, stop=stop, clock=lambda: 5
    )
    assert fired == 0
