"""Per-second window metrics, HDR latency histograms, header statistics, and writers."""

from __future__ import annotations

import csv
import json
import math
import os
import random
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from hdrh.histogram import HdrHistogram

LAT_LOW_US = 1
LAT_HIGH_US = 600_000_000
WINDOW_SIG_FIGS = 2
AGGREGATE_SIG_FIGS = 3
FINE_BINS_PER_SECOND = 10
PERCENTILES = (50.0, 90.0, 95.0, 99.0)

RATE_LIMIT_HEADERS: tuple[str, ...] = (
    "retry-after",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "ratelimit-policy",
    "ratelimit",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
)
_RATE_LIMIT_HEADER_SET = frozenset(RATE_LIMIT_HEADERS)
MAX_DISTINCT_HEADER_VALUES = 20
OTHER_VALUES = "__other__"

METRICS_CSV_COLUMNS = (
    "second",
    "attempted_rps",
    "accepted_rps",
    "429_rps",
    "error_rps",
    "p50_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "dropped",
)
ROUTES_CSV_COLUMNS = ("second", "route", "attempted", "accepted", "429", "errors")
FINE_CSV_COLUMNS = ("bin", "t_start_s", "attempted", "accepted", "429")


def status_family(status: int | None) -> str:
    if status is None:
        return "error"
    if status == 429:
        return "429"
    return f"{status // 100}xx"


class LatencyHistogram:
    """HdrHistogram wrapper storing microseconds; merge is portable (no C addressing)."""

    __slots__ = ("_h", "sig_figs")

    def __init__(self, sig_figs: int = AGGREGATE_SIG_FIGS) -> None:
        self.sig_figs = sig_figs
        self._h = HdrHistogram(LAT_LOW_US, LAT_HIGH_US, sig_figs)

    @property
    def count(self) -> int:
        return int(self._h.get_total_count())

    def record_s(self, seconds: float) -> None:
        self.record_us(int(seconds * 1_000_000))

    def record_us(self, micros: int, count: int = 1) -> None:
        self._h.record_value(min(max(micros, LAT_LOW_US), LAT_HIGH_US), count)

    def percentile_ms(self, pct: float) -> float | None:
        if self.count == 0:
            return None
        return float(self._h.get_value_at_percentile(pct)) / 1000.0

    def summary_ms(self) -> dict[str, float | int | None]:
        if self.count == 0:
            empty: dict[str, float | int | None] = {"count": 0}
            empty.update({f"p{pct:g}": None for pct in PERCENTILES})
            empty.update({"max": None, "mean": None})
            return empty
        out: dict[str, float | int | None] = {"count": self.count}
        for pct in PERCENTILES:
            out[f"p{pct:g}"] = self.percentile_ms(pct)
        out["max"] = float(self._h.get_max_value()) / 1000.0
        out["mean"] = round(float(self._h.get_mean_value()) / 1000.0, 3)
        return out

    def to_pairs(self) -> list[tuple[int, int]]:
        """Sparse ``(counts_index, count)`` pairs; only valid for same-precision merges."""
        h = self._h
        if h.total_count == 0:
            return []
        lo = h._counts_index_for(h.min_value)
        hi = h._counts_index_for(h.max_value)
        window = h.counts[lo : hi + 1]
        return [(lo + i, int(c)) for i, c in enumerate(window) if c]

    def merge_pairs(self, pairs: Iterable[Iterable[int]]) -> None:
        h = self._h
        counts = h.counts
        lo = hi = -1
        added = 0
        for index, count in pairs:
            counts[index] += count
            added += count
            if lo < 0 or index < lo:
                lo = index
            hi = max(hi, index)
        if added:
            h.total_count += added
            h.min_value = min(h.min_value, h.get_value_from_index(lo))
            h.max_value = max(
                h.max_value, h.get_highest_equivalent_value(h.get_value_from_index(hi))
            )

    def merge(self, other: LatencyHistogram) -> None:
        self.merge_pairs(other.to_pairs())


def _parse_numeric(name: str, value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        pass
    if name == "retry-after":
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max((when - datetime.now(UTC)).total_seconds(), 0.0)
    return None


@dataclass
class HeaderStat:
    count: int = 0
    count_429: int = 0
    numeric_count: int = 0
    numeric_sum: float = 0.0
    numeric_min: float | None = None
    numeric_max: float | None = None
    values: dict[str, int] = field(default_factory=dict)

    def record(self, name: str, value: str, is_429: bool) -> None:
        self.count += 1
        if is_429:
            self.count_429 += 1
        num = _parse_numeric(name, value)
        if num is not None:
            self._add_numeric(1, num, num, num)
        self._add_value(value, 1)

    def _add_numeric(self, n: int, total: float, lo: float, hi: float) -> None:
        self.numeric_count += n
        self.numeric_sum += total
        self.numeric_min = lo if self.numeric_min is None else min(self.numeric_min, lo)
        self.numeric_max = hi if self.numeric_max is None else max(self.numeric_max, hi)

    def _add_value(self, value: str, n: int) -> None:
        if value in self.values or len(self.values) < MAX_DISTINCT_HEADER_VALUES:
            self.values[value] = self.values.get(value, 0) + n
        else:
            self.values[OTHER_VALUES] = self.values.get(OTHER_VALUES, 0) + n

    def to_state(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "count_429": self.count_429,
            "numeric_count": self.numeric_count,
            "numeric_sum": self.numeric_sum,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "values": dict(self.values),
        }

    def merge_state(self, state: Mapping[str, Any]) -> None:
        self.count += int(state["count"])
        self.count_429 += int(state["count_429"])
        if state["numeric_count"]:
            self._add_numeric(
                int(state["numeric_count"]),
                float(state["numeric_sum"]),
                float(state["numeric_min"]),
                float(state["numeric_max"]),
            )
        for value, n in state["values"].items():
            self._add_value(value, int(n))

    def summary(self, total_responses: int) -> dict[str, Any]:
        mean = self.numeric_sum / self.numeric_count if self.numeric_count else None
        top = sorted(self.values.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
        return {
            "count": self.count,
            "presence_ratio": round(self.count / total_responses, 4) if total_responses else 0.0,
            "count_on_429": self.count_429,
            "numeric": (
                {"min": self.numeric_min, "max": self.numeric_max, "mean": mean}
                if self.numeric_count
                else None
            ),
            "top_values": dict(top),
        }


class Window:
    __slots__ = ("accepted", "attempted", "dropped", "errors", "final", "hist", "s429")

    def __init__(self) -> None:
        self.attempted = 0
        self.accepted = 0
        self.s429 = 0
        self.errors = 0
        self.dropped = 0
        self.hist: LatencyHistogram | None = None
        self.final: dict[str, float | None] | None = None

    def latency(self) -> dict[str, float | None]:
        if self.final is not None:
            return self.final
        if self.hist is None:
            return {f"p{p:g}": None for p in PERCENTILES}
        return {f"p{p:g}": self.hist.percentile_ms(p) for p in PERCENTILES}


class MetricsCollector:
    """Accumulates run metrics keyed by *scheduled* time (CO-safe binning)."""

    def __init__(self) -> None:
        self.windows: dict[int, Window] = {}
        self.routes: dict[tuple[int, str], list[int]] = {}
        self.fine: dict[int, list[int]] = {}
        self.families: dict[str, LatencyHistogram] = {}
        self.overall = LatencyHistogram()
        self.lag = LatencyHistogram()
        self.status_codes: Counter[str] = Counter()
        self.error_types: Counter[str] = Counter()
        self.unexpected_status: Counter[str] = Counter()
        self.headers: dict[str, HeaderStat] = {}
        self.late_samples = 0
        self.finalized_until = 0

    # -- recording -------------------------------------------------------------------------

    def _window(self, sec: int) -> Window:
        w = self.windows.get(sec)
        if w is None:
            w = self.windows[sec] = Window()
        return w

    def _route(self, sec: int, route: str) -> list[int]:
        key = (sec, route)
        r = self.routes.get(key)
        if r is None:
            r = self.routes[key] = [0, 0, 0, 0]
        return r

    def _fine(self, offset: float) -> list[int]:
        idx = int(offset * FINE_BINS_PER_SECOND)
        f = self.fine.get(idx)
        if f is None:
            f = self.fine[idx] = [0, 0, 0]
        return f

    def record_attempt(self, offset: float, route: str, lag_s: float) -> None:
        sec = int(offset)
        self._window(sec).attempted += 1
        self._route(sec, route)[0] += 1
        self._fine(offset)[0] += 1
        self.lag.record_s(max(lag_s, 0.0))

    def record_dropped(self, offset: float, route: str) -> None:
        w = self._window(int(offset))
        w.dropped += 1
        w.errors += 1
        self._route(int(offset), route)[3] += 1
        self.error_types["ClientQueueFull"] += 1

    def record_result(
        self,
        offset: float,
        route: str,
        status: int | None,
        latency_s: float,
        *,
        error_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        expected: bool = True,
    ) -> None:
        sec = int(offset)
        w = self._window(sec)
        r = self._route(sec, route)
        if status is None:
            w.errors += 1
            r[3] += 1
            self.error_types[error_type or "UnknownError"] += 1
        else:
            self.status_codes[str(status)] += 1
            if 200 <= status < 400:
                w.accepted += 1
                r[1] += 1
                self._fine(offset)[1] += 1
            elif status == 429:
                w.s429 += 1
                r[2] += 1
                self._fine(offset)[2] += 1
            else:
                w.errors += 1
                r[3] += 1
            if w.final is None:
                if w.hist is None:
                    w.hist = LatencyHistogram(WINDOW_SIG_FIGS)
                w.hist.record_s(latency_s)
            else:
                self.late_samples += 1
            self.overall.record_s(latency_s)
            if headers is not None:
                is_429 = status == 429
                for raw_name, value in headers.items():
                    name = raw_name.lower()
                    if name in _RATE_LIMIT_HEADER_SET:
                        stat = self.headers.get(name)
                        if stat is None:
                            stat = self.headers[name] = HeaderStat()
                        stat.record(name, value, is_429)
        fam = status_family(status)
        hist = self.families.get(fam)
        if hist is None:
            hist = self.families[fam] = LatencyHistogram()
        hist.record_s(latency_s)
        if not expected:
            self.unexpected_status[route] += 1

    # -- lifecycle -------------------------------------------------------------------------

    def finalize_before(self, sec: int) -> None:
        """Freeze percentiles for windows ``< sec`` and release their histograms."""
        for s in sorted(k for k in self.windows if self.finalized_until <= k < sec):
            w = self.windows[s]
            if w.final is None:
                w.final = w.latency()
                w.hist = None
        self.finalized_until = max(self.finalized_until, sec)

    def to_state(self) -> dict[str, Any]:
        return {
            "windows": {
                s: [
                    w.attempted,
                    w.accepted,
                    w.s429,
                    w.errors,
                    w.dropped,
                    w.hist.to_pairs() if w.hist else [],
                ]
                for s, w in self.windows.items()
            },
            "routes": [[s, name, *vals] for (s, name), vals in self.routes.items()],
            "fine": {i: list(v) for i, v in self.fine.items()},
            "families": {k: h.to_pairs() for k, h in self.families.items()},
            "overall": self.overall.to_pairs(),
            "lag": self.lag.to_pairs(),
            "status_codes": dict(self.status_codes),
            "error_types": dict(self.error_types),
            "unexpected_status": dict(self.unexpected_status),
            "headers": {k: v.to_state() for k, v in self.headers.items()},
            "late_samples": self.late_samples,
        }

    def merge_state(self, state: Mapping[str, Any]) -> None:
        for s, (att, acc, s429, err, drop, pairs) in state["windows"].items():
            w = self._window(int(s))
            w.attempted += att
            w.accepted += acc
            w.s429 += s429
            w.errors += err
            w.dropped += drop
            if pairs:
                if w.final is None:
                    if w.hist is None:
                        w.hist = LatencyHistogram(WINDOW_SIG_FIGS)
                    w.hist.merge_pairs(pairs)
                else:
                    self.late_samples += sum(c for _, c in pairs)
        for s, name, *vals in state["routes"]:
            r = self._route(int(s), name)
            for i, v in enumerate(vals):
                r[i] += v
        for i, vals in state["fine"].items():
            f = self.fine.setdefault(int(i), [0, 0, 0])
            for j, v in enumerate(vals):
                f[j] += v
        for fam, pairs in state["families"].items():
            self.families.setdefault(fam, LatencyHistogram()).merge_pairs(pairs)
        self.overall.merge_pairs(state["overall"])
        self.lag.merge_pairs(state["lag"])
        self.status_codes.update(state["status_codes"])
        self.error_types.update(state["error_types"])
        self.unexpected_status.update(state["unexpected_status"])
        for name, hs in state["headers"].items():
            self.headers.setdefault(name, HeaderStat()).merge_state(hs)
        self.late_samples += int(state["late_samples"])

    # -- views -----------------------------------------------------------------------------

    def n_seconds(self, duration: float) -> int:
        last = max(self.windows) + 1 if self.windows else 0
        return max(math.ceil(duration), last)

    def metric_rows(self, duration: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        empty = Window()
        for sec in range(self.n_seconds(duration)):
            w = self.windows.get(sec, empty)
            span = duration - sec
            width = span if 0 < span < 1 else 1.0
            lat = w.latency()
            rows.append(
                {
                    "second": sec,
                    "attempted_rps": round(w.attempted / width, 3),
                    "accepted_rps": round(w.accepted / width, 3),
                    "429_rps": round(w.s429 / width, 3),
                    "error_rps": round(w.errors / width, 3),
                    "p50_ms": lat["p50"],
                    "p90_ms": lat["p90"],
                    "p95_ms": lat["p95"],
                    "p99_ms": lat["p99"],
                    "dropped": w.dropped,
                }
            )
        return rows

    def route_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "second": s,
                "route": name,
                "attempted": v[0],
                "accepted": v[1],
                "429": v[2],
                "errors": v[3],
            }
            for (s, name), v in sorted(self.routes.items())
        ]

    def fine_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "bin": i,
                "t_start_s": round(i / FINE_BINS_PER_SECOND, 3),
                "attempted": v[0],
                "accepted": v[1],
                "429": v[2],
            }
            for i, v in sorted(self.fine.items())
        ]

    def totals(self) -> dict[str, int]:
        ws = self.windows.values()
        return {
            "attempted": sum(w.attempted for w in ws),
            "accepted": sum(w.accepted for w in ws),
            "429": sum(w.s429 for w in ws),
            "errors": sum(w.errors for w in ws),
            "dropped": sum(w.dropped for w in ws),
        }

    def header_summary(self) -> dict[str, Any]:
        total = sum(self.status_codes.values())
        return {name: stat.summary(total) for name, stat in sorted(self.headers.items())}

    def route_totals(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for (_, name), v in self.routes.items():
            t = out.setdefault(name, {"attempted": 0, "accepted": 0, "429": 0, "errors": 0})
            t["attempted"] += v[0]
            t["accepted"] += v[1]
            t["429"] += v[2]
            t["errors"] += v[3]
        for name, t in out.items():
            t["unexpected_status"] = self.unexpected_status.get(name, 0)
        return out


class EventSink:
    """Sampled raw-event writer (JSONL) with a bounded buffer; overflow is counted, not queued."""

    def __init__(self, path: Path, sample_rate: float, seed: int = 0, max_buffer: int = 50_000):
        self.path = path
        self.sample_rate = sample_rate
        self.max_buffer = max_buffer
        self.dropped = 0
        self.written = 0
        self._rng = random.Random(seed)
        self._buf: list[str] = []

    @property
    def enabled(self) -> bool:
        return self.sample_rate > 0

    def offer(self, event: Mapping[str, Any]) -> None:
        if self._rng.random() >= self.sample_rate:
            return
        if len(self._buf) >= self.max_buffer:
            self.dropped += 1
            return
        self._buf.append(json.dumps(event, separators=(",", ":")))

    def flush(self) -> None:
        if not self._buf:
            return
        lines, self._buf = self._buf, []
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        self.written += len(lines)


def _atomic_replace(tmp: Path, dest: Path) -> None:
    try:
        os.replace(tmp, dest)
    except PermissionError:
        # Windows: destination may be open in another program; fall back to direct write.
        dest.write_bytes(tmp.read_bytes())
        tmp.unlink(missing_ok=True)


def write_csv(path: Path, columns: Iterable[str], rows: Iterable[Mapping[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    _atomic_replace(tmp, path)


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=False, default=str), encoding="utf-8")
    _atomic_replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
