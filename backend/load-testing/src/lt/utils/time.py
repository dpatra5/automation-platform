"""Time helpers: duration parsing, run identifiers, and timer resolution."""

from __future__ import annotations

import asyncio
import contextlib
import re
import secrets
import sys
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

perf_counter = time.perf_counter

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)?\s*$", re.IGNORECASE)
_UNITS: dict[str, float] = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(value: str | float | int) -> float:
    """Parse ``"500ms"``, ``"60s"``, ``"5m"``, ``"1h"`` or a bare number of seconds."""
    if isinstance(value, bool):
        raise ValueError(f"invalid duration: {value!r}")
    if isinstance(value, int | float):
        seconds = float(value)
    else:
        match = _DURATION_RE.match(value)
        if not match:
            raise ValueError(
                f"invalid duration: {value!r} (expected e.g. '500ms', '60s', '5m', '1h')"
            )
        unit = (match.group(2) or "s").lower()
        seconds = float(match.group(1)) * _UNITS[unit]
    if seconds < 0:
        raise ValueError(f"duration must be >= 0, got {value!r}")
    return seconds


def parse_think_time(value: str | float | int) -> tuple[float, float]:
    """``"1s"`` (constant) or ``"500ms-2s"`` (uniform random) -> ``(low, high)`` seconds."""
    if isinstance(value, str) and "-" in value.strip().lstrip("-"):
        low_text, _, high_text = value.partition("-")
        low, high = parse_duration(low_text), parse_duration(high_text)
        if high < low:
            raise ValueError(f"think time range must be low-high, got {value!r}")
        return low, high
    seconds = parse_duration(value)
    return seconds, seconds


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:g}ms"
    return f"{seconds:g}s"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def new_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


def event_loop_factory(use_uvloop: bool = True) -> Callable[[], asyncio.AbstractEventLoop]:
    """Pick the most precise event loop available for the platform."""
    if sys.platform == "win32":

        class PreciseProactorEventLoop(asyncio.ProactorEventLoop):
            # GetTickCount64-based monotonic() has ~15.6 ms resolution before Python 3.13.
            def __init__(self) -> None:
                super().__init__()
                self._clock_resolution = time.get_clock_info("perf_counter").resolution

            def time(self) -> float:
                return time.perf_counter()

        return PreciseProactorEventLoop
    if use_uvloop:
        try:
            import uvloop

            factory: Callable[[], asyncio.AbstractEventLoop] = uvloop.new_event_loop
            return factory
        except ImportError:
            pass
    return asyncio.new_event_loop


@contextlib.contextmanager
def high_resolution_timers() -> Iterator[None]:
    """Request 1 ms timer granularity on Windows (default is ~15.6 ms); no-op elsewhere."""
    if sys.platform == "win32":
        import ctypes

        try:
            winmm = ctypes.WinDLL("winmm")
            winmm.timeBeginPeriod(1)
        except (OSError, AttributeError):
            yield
            return
        try:
            yield
        finally:
            winmm.timeEndPeriod(1)
    else:
        yield
