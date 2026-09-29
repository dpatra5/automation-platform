"""Coordinated-omission-safe open-model arrival scheduler.

Arrival times are a pure function of the load profile: event ``k`` (0-based, global across
all shards) is fired at ``t`` where the cumulative arrival function ``Λ(t) = k``. Shard ``s``
of ``N`` owns events ``k ≡ s (mod N)``, so shards interleave perfectly instead of bursting in
lock-step. Scheduling never waits for responses and never skips events when running late.
"""

from __future__ import annotations

import asyncio
import bisect
import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from lt.config import ProfileStep
from lt.utils.time import perf_counter

# Waking this close to the target is treated as on-time (avoids sub-timer-resolution spins).
FIRE_TOLERANCE_S = 0.0002
MAX_SLEEP_S = 0.1
YIELD_EVERY = 64

FireCallback = Callable[[int, int, float, float], None]
"""Invoked as ``on_fire(shard, k, offset_s, fire_time)``."""


@dataclass(frozen=True, slots=True)
class Segment:
    index: int
    start: float
    duration: float
    rate_start: float
    rate_end: float
    count_start: float

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def count(self) -> float:
        return (self.rate_start + self.rate_end) / 2.0 * self.duration

    @property
    def count_end(self) -> float:
        return self.count_start + self.count

    @property
    def is_idle(self) -> bool:
        return self.rate_start == 0 and self.rate_end == 0

    def offset_of(self, k: float) -> float:
        """Solve ``r0·τ + a·τ² = k - count_start`` for τ (numerically stable form)."""
        m = k - self.count_start
        if m <= 0:
            return self.start
        a = (self.rate_end - self.rate_start) / (2.0 * self.duration)
        b = self.rate_start
        denom = b + math.sqrt(max(b * b + 4.0 * a * m, 0.0))
        tau = 2.0 * m / denom if denom > 0 else 0.0
        return self.start + min(tau, self.duration)

    def cumulative(self, t: float) -> float:
        """Expected events from segment start up to absolute offset ``t``."""
        tau = min(max(t - self.start, 0.0), self.duration)
        a = (self.rate_end - self.rate_start) / (2.0 * self.duration)
        return self.rate_start * tau + a * tau * tau


class ArrivalSchedule:
    """Deterministic arrival offsets (seconds from run start) for a load profile."""

    def __init__(self, steps: Sequence[ProfileStep]) -> None:
        segments: list[Segment] = []
        t = 0.0
        count = 0.0
        for i, step in enumerate(steps):
            seg = Segment(i, t, step.duration, step.rate, step.final_rate, count)
            segments.append(seg)
            t += step.duration
            count += seg.count
        self.segments: tuple[Segment, ...] = tuple(segments)
        self.total_duration = t
        self.total_events = count
        self._count_ends = [s.count_end for s in self.segments]

    def time_of(self, k: float) -> float:
        i = bisect.bisect_right(self._count_ends, k)
        if i >= len(self.segments):
            return self.total_duration
        return self.segments[i].offset_of(k)

    def expected_between(self, t0: float, t1: float) -> float:
        total = 0.0
        for seg in self.segments:
            if seg.end <= t0 or seg.start >= t1:
                continue
            total += seg.cumulative(t1) - seg.cumulative(t0)
        return total

    def segment_at(self, t: float) -> Segment | None:
        for seg in self.segments:
            if seg.start <= t < seg.end:
                return seg
        return None

    def iter_offsets(self, shard: int = 0, n_shards: int = 1) -> Iterator[tuple[int, float]]:
        if not 0 <= shard < n_shards:
            raise ValueError("shard must be in [0, n_shards)")
        segments = self.segments
        last = len(segments) - 1
        total = self.total_events
        i = 0
        k = shard
        while k < total:
            while i < last and k >= segments[i].count_end:
                i += 1
            yield k, segments[i].offset_of(k)
            k += n_shards


async def run_shard(
    schedule: ArrivalSchedule,
    *,
    shard: int,
    n_shards: int,
    start: float,
    on_fire: FireCallback,
    stop: asyncio.Event,
    clock: Callable[[], float] = perf_counter,
) -> int:
    """Fire every event owned by ``shard`` at ``start + offset``; returns events fired."""
    fired = 0
    burst = 0
    sleep = asyncio.sleep
    for k, offset in schedule.iter_offsets(shard, n_shards):
        target = start + offset
        delay = target - clock()
        while delay > FIRE_TOLERANCE_S:
            burst = 0
            await sleep(min(delay, MAX_SLEEP_S))
            if stop.is_set():
                return fired
            delay = target - clock()
        if stop.is_set():
            return fired
        on_fire(shard, k, offset, clock())
        fired += 1
        burst += 1
        if burst >= YIELD_EVERY:
            # Catching up after a stall: fire immediately, but let workers run.
            burst = 0
            await sleep(0)
    return fired


async def run_shards(
    schedule: ArrivalSchedule,
    *,
    shard_ids: Sequence[int],
    n_shards: int,
    start: float,
    on_fire: FireCallback,
    stop: asyncio.Event,
    clock: Callable[[], float] = perf_counter,
) -> int:
    results = await asyncio.gather(
        *(
            run_shard(
                schedule,
                shard=s,
                n_shards=n_shards,
                start=start,
                on_fire=on_fire,
                stop=stop,
                clock=clock,
            )
            for s in shard_ids
        )
    )
    return sum(results)
