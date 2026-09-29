"""Offline rate-limit analysis of a run directory.

Produces sustained-capacity verification, burst inference, step capacity curve and knee,
multi-tenant fairness, rate-limit header statistics, and limiter window-semantics
classification. Inputs are the artifacts written by ``lt run``.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from lt.config import AnalysisConfig
from lt.metrics import FINE_BINS_PER_SECOND, read_csv, write_json

FOLD_PERIODS_S = (1, 2, 5, 10)
FIXED_WINDOW_CV = 0.5
TOKEN_BUCKET_EXCESS = 0.15
TOKEN_BUCKET_BURST_RATIO = 0.05
TOKEN_BUCKET_MIN_BURST = 5
MIN_429_RATIO = 0.01
MAX_VALID_LAG_P99_MS = 50.0
MAX_VALID_LATENCY_P99_MS = 1000.0


class AnalysisError(RuntimeError):
    """Raised when a run directory is missing required artifacts."""


@dataclass(frozen=True)
class Seg:
    index: int
    start: float
    duration: float
    rate: float
    end_rate: float

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def constant(self) -> bool:
        return self.rate > 0 and self.rate == self.end_rate

    @property
    def idle(self) -> bool:
        return self.rate == 0 and self.end_rate == 0


def _num(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


@dataclass
class RunData:
    run_dir: Path
    metrics: dict[str, Any]
    config: dict[str, Any]
    rows: list[dict[str, float | None]]
    routes: list[dict[str, Any]]
    fine: dict[int, tuple[int, int, int]]
    segments: list[Seg]

    def row(self, sec: int) -> dict[str, float | None] | None:
        return self.rows[sec] if 0 <= sec < len(self.rows) else None

    def steady_rows(self, seg: Seg, warmup: int) -> list[dict[str, float | None]]:
        first = int(seg.start) + warmup
        last = int(seg.end)  # exclusive; only full windows inside the segment
        return [r for s in range(first, last) if (r := self.row(s)) is not None]


def load_run(run_dir: str | Path) -> RunData:
    d = Path(run_dir)
    required = ["metrics.json", "metrics.csv", "config.json"]
    missing = [name for name in required if not (d / name).is_file()]
    if missing:
        raise AnalysisError(f"{d} is not a complete run directory (missing {', '.join(missing)})")
    metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    rows = [{k: _num(v) for k, v in r.items()} for r in read_csv(d / "metrics.csv")]
    routes: list[dict[str, Any]] = []
    if (d / "routes.csv").is_file():
        for r in read_csv(d / "routes.csv"):
            routes.append(
                {
                    "second": int(r["second"]),
                    "route": r["route"],
                    "attempted": int(r["attempted"]),
                    "accepted": int(r["accepted"]),
                    "429": int(r["429"]),
                }
            )
    fine: dict[int, tuple[int, int, int]] = {}
    if (d / "fine.csv").is_file():
        for r in read_csv(d / "fine.csv"):
            fine[int(r["bin"])] = (int(r["attempted"]), int(r["accepted"]), int(r["429"]))
    segments = [
        Seg(p["index"], p["start_s"], p["duration_s"], p["rate"], p["end_rate"])
        for p in metrics["profile"]
    ]
    return RunData(d, metrics, config, rows, routes, fine, segments)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _col(rows: list[dict[str, float | None]], key: str) -> list[float]:
    return [v for r in rows if (v := r.get(key)) is not None]


def _round(v: float | None, n: int = 3) -> float | None:
    return None if v is None else round(v, n)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares ``y = slope·x + intercept``."""
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    return slope, my - slope * mx


# -- sustained ---------------------------------------------------------------------------


def analyze_sustained(run: RunData, cfg: AnalysisConfig) -> dict[str, Any]:
    candidates = [s for s in run.segments if s.constant]
    if not candidates:
        return {"applicable": False, "reason": "no constant-rate segment"}
    seg = max(candidates, key=lambda s: s.duration)
    rows = run.steady_rows(seg, cfg.warmup_windows)
    if not rows:
        return {"applicable": False, "reason": "segment too short after warmup windows"}
    accepted = _col(rows, "accepted_rps")
    mean_acc = statistics.fmean(accepted)
    target = min(seg.rate, cfg.expected_limit_rps) if cfg.expected_limit_rps else seg.rate
    deviation = (mean_acc - target) / target
    mean_429 = _mean(_col(rows, "429_rps")) or 0.0
    return {
        "applicable": True,
        "segment": seg.index,
        "windows": len(rows),
        "asked_rps": seg.rate,
        "target_rps": target,
        "mean_attempted_rps": _round(_mean(_col(rows, "attempted_rps"))),
        "mean_accepted_rps": round(mean_acc, 3),
        "stdev_accepted_rps": round(statistics.pstdev(accepted), 3),
        "mean_429_rps": round(mean_429, 3),
        "mean_error_rps": _round(_mean(_col(rows, "error_rps"))),
        "expected_overflow_rps": round(max(seg.rate - target, 0.0), 3),
        "deviation_pct": round(deviation * 100, 3),
        "tolerance_pct": round(cfg.tolerance * 100, 3),
        "pass": abs(deviation) <= cfg.tolerance,
    }


# -- burst -------------------------------------------------------------------------------


def analyze_burst(run: RunData, cfg: AnalysisConfig) -> dict[str, Any]:
    candidates = [
        s for i, s in enumerate(run.segments) if s.rate > 0 and (i == 0 or run.segments[i - 1].idle)
    ]
    chosen: Seg | None = None
    for seg in candidates:
        if any((r.get("429_rps") or 0) > 0 for r in run.steady_rows(seg, 0)):
            chosen = seg
            break
    if chosen is None:
        return {
            "applicable": bool(candidates),
            "triggered": False,
            "reason": "no 429s after an idle period; offered load never exceeded the burst",
        }
    seg = chosen
    first = run.row(int(seg.start))
    first_acc = int(first["accepted_rps"] or 0) if first else 0
    result: dict[str, Any] = {
        "applicable": True,
        "triggered": True,
        "segment": seg.index,
        "first_window_acceptances": first_acc,
    }
    # Cumulative acceptances after the bucket drains follow C(t) = b + r·t.
    b0 = int(round(seg.start * FINE_BINS_PER_SECOND))
    b1 = int(round(seg.end * FINE_BINS_PER_SECOND))
    first_429_bin = next((b for b in range(b0, b1) if run.fine.get(b, (0, 0, 0))[2] > 0), None)
    xs: list[float] = []
    ys: list[float] = []
    if first_429_bin is not None:
        cumulative = 0
        fit_from = max(b0 + FINE_BINS_PER_SECOND, first_429_bin + FINE_BINS_PER_SECOND // 2)
        for b in range(b0, b1):
            cumulative += run.fine.get(b, (0, 0, 0))[1]
            if b >= fit_from:
                xs.append((b + 1 - b0) / FINE_BINS_PER_SECOND)
                ys.append(float(cumulative))
    if len(xs) >= 5:
        refill, burst = _linfit(xs, ys)
        method = "fine-bin regression of cumulative acceptances (C(t) = b + r*t)"
    else:
        later = _col(run.steady_rows(seg, 1), "accepted_rps")
        refill = statistics.fmean(later) if later else 0.0
        burst = first_acc - refill
        method = "first window minus steady refill rate"
    result.update(
        {
            "inferred_burst_b": round(burst, 2),
            "refill_rate_estimate": round(refill, 3),
            "method": method,
        }
    )
    if cfg.expected_burst:
        err = (burst - cfg.expected_burst) / cfg.expected_burst
        result.update(
            {
                "expected_burst": cfg.expected_burst,
                "error_pct": round(err * 100, 3),
                "tolerance_pct": round(cfg.burst_tolerance * 100, 3),
                "pass": abs(err) <= cfg.burst_tolerance,
            }
        )
    return result


# -- step --------------------------------------------------------------------------------


def analyze_step(run: RunData, cfg: AnalysisConfig) -> dict[str, Any]:
    steps = [s for s in run.segments if s.constant]
    if len(steps) < 2:
        return {"applicable": False, "reason": "fewer than two constant-rate steps"}
    curve: list[dict[str, Any]] = []
    for seg in steps:
        rows = run.steady_rows(seg, cfg.warmup_windows) or run.steady_rows(seg, 0)
        acc = _mean(_col(rows, "accepted_rps")) or 0.0
        att = _mean(_col(rows, "attempted_rps")) or seg.rate
        r429 = _mean(_col(rows, "429_rps")) or 0.0
        err = _mean(_col(rows, "error_rps")) or 0.0
        curve.append(
            {
                "segment": seg.index,
                "asked": seg.rate,
                "attempted": round(att, 3),
                "accepted": round(acc, 3),
                "429_rate": round(r429 / att, 4) if att else 0.0,
                "error_rate": round(err / att, 4) if att else 0.0,
            }
        )
    knee: dict[str, Any] | None = None
    thr = cfg.knee_429_threshold
    if curve[0]["429_rate"] > thr:
        knee = {**curve[0], "reason": "429s already present at the first step"}
    for prev, cur in pairwise(curve):
        if knee is not None:
            break
        d_asked = cur["asked"] - prev["asked"]
        marginal = (cur["accepted"] - prev["accepted"]) / d_asked if d_asked > 0 else 1.0
        if cur["429_rate"] > thr >= prev["429_rate"]:
            knee = {**cur, "marginal_gain": round(marginal, 4), "reason": "429 onset"}
        elif d_asked > 0 and marginal < cfg.knee_marginal_threshold:
            knee = {**cur, "marginal_gain": round(marginal, 4), "reason": "marginal gain drop"}
    capacity = None
    if knee is not None:
        plateau = [c["accepted"] for c in curve if c["asked"] >= knee["asked"]]
        capacity = round(statistics.fmean(plateau), 3)
    result: dict[str, Any] = {
        "applicable": True,
        "capacity_curve": curve,
        "knee_point": knee,
        "estimated_capacity_rps": capacity,
        "max_accepted_rps": max(c["accepted"] for c in curve),
    }
    if cfg.expected_limit_rps and capacity is not None:
        err = (capacity - cfg.expected_limit_rps) / cfg.expected_limit_rps
        result["capacity_error_pct"] = round(err * 100, 3)
        result["pass"] = abs(err) <= max(cfg.tolerance, 0.10)
    return result


# -- fairness ----------------------------------------------------------------------------


def analyze_fairness(run: RunData, cfg: AnalysisConfig) -> dict[str, Any]:
    tenant_of = {r["name"]: (r.get("tenant") or r["name"]) for r in run.config.get("routes", [])}
    tenants = sorted(set(tenant_of.values()))
    if len(tenants) < 2 or not run.routes:
        return {"applicable": False, "reason": "fewer than two tenants/keys configured"}
    steady: set[int] = set()
    for seg in run.segments:
        if seg.rate > 0 or seg.end_rate > 0:
            first, last = int(seg.start) + cfg.warmup_windows, int(seg.end)
            steady.update(range(first, last))
    per: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for r in run.routes:
        if r["second"] in steady:
            bucket = per[tenant_of.get(r["route"], r["route"])][r["second"]]
            bucket[0] += r["attempted"]
            bucket[1] += r["accepted"]
            bucket[2] += r["429"]
    n = len(steady) or 1
    stats: dict[str, dict[str, float]] = {}
    for t in tenants:
        secs = per.get(t, {})
        att = sum(v[0] for v in secs.values()) / n
        acc = sum(v[1] for v in secs.values()) / n
        stats[t] = {
            "attempted_rps": round(att, 3),
            "accepted_rps": round(acc, 3),
            "429_rps": round(sum(v[2] for v in secs.values()) / n, 3),
            "acceptance_rate": round(acc / att, 4) if att else 0.0,
        }
    shares = max_min_shares(
        {t: s["attempted_rps"] for t, s in stats.items()},
        sum(s["accepted_rps"] for s in stats.values()),
    )
    for t, share in shares.items():
        stats[t]["fair_share_rps"] = round(share, 3)
    accepted = [s["accepted_rps"] for s in stats.values()]
    ratio = max(accepted) / min(accepted) if min(accepted) > 0 else None
    normalised = [
        s["accepted_rps"] / s["fair_share_rps"] for s in stats.values() if s["fair_share_rps"] > 0
    ]
    share_ratio = (
        max(normalised) / min(normalised)
        if len(normalised) == len(stats) and min(normalised) > 0
        else None
    )
    return {
        "applicable": True,
        "windows": len(steady),
        "tenants": stats,
        "fairness_ratio": _round(ratio, 4),
        "fair_share_ratio": _round(share_ratio, 4),
        "basis": "max-min fair share (equals accepted_rps ratio under equal demand)",
        "threshold": cfg.fairness_threshold,
        "pass": share_ratio is not None and share_ratio <= cfg.fairness_threshold,
    }


def max_min_shares(demands: dict[str, float], capacity: float) -> dict[str, float]:
    """Water-filling allocation of ``capacity`` across tenants with the given demands."""
    shares: dict[str, float] = {}
    remaining = capacity
    order = sorted(demands, key=lambda t: demands[t])
    for i, tenant in enumerate(order):
        give = min(demands[tenant], remaining / (len(order) - i))
        shares[tenant] = give
        remaining -= give
    return shares


# -- headers -----------------------------------------------------------------------------


def analyze_headers(run: RunData) -> dict[str, Any]:
    headers: dict[str, Any] = run.metrics.get("headers", {})
    codes: dict[str, int] = run.metrics.get("status_codes", {})
    total = sum(codes.values())
    n429 = codes.get("429", 0)
    ietf = any(k.startswith("ratelimit") for k in headers)
    legacy = any(k.startswith("x-ratelimit") for k in headers)
    style = {(True, True): "both", (True, False): "ietf", (False, True): "x-ratelimit"}.get(
        (ietf, legacy), "none"
    )
    retry = headers.get("retry-after")
    return {
        "total_responses": total,
        "responses_429": n429,
        "style": style,
        "retry_after_on_429_ratio": (
            round(retry["count_on_429"] / n429, 4) if retry and n429 else 0.0
        ),
        "headers": headers,
    }


# -- window semantics --------------------------------------------------------------------


def _burst_excess(run: RunData, onset: Seg) -> float | None:
    first = run.row(int(onset.start))
    later = _col(run.steady_rows(onset, 2), "accepted_rps")
    if not first or not later:
        return None
    steady = statistics.fmean(later)
    return (first["accepted_rps"] or 0.0) / steady - 1.0 if steady > 0 else None


def analyze_window_semantics(
    run: RunData, headers: dict[str, Any], burst: dict[str, Any] | None = None
) -> dict[str, Any]:
    totals = run.metrics.get("totals", {})
    attempted = totals.get("attempted", 0)
    if not attempted or totals.get("429", 0) / attempted < MIN_429_RATIO:
        return {
            "classification": "not-triggered",
            "confidence": 0.0,
            "rationale": "fewer than 1% of requests were rate limited; limiter not exercised",
        }
    first_429 = min((b for b, v in run.fine.items() if v[2] > 0), default=None)
    onset = None
    if first_429 is not None:
        t429 = first_429 / FINE_BINS_PER_SECOND
        onset = next((s for s in run.segments if s.start <= t429 < s.end), None)
    if first_429 is None or onset is None:
        return {"classification": "unknown", "confidence": 0.0, "rationale": "no fine-bin data"}
    b_onset = int(round(onset.start * FINE_BINS_PER_SECOND))
    b_end = int(round(onset.end * FINE_BINS_PER_SECOND))
    steady_from = first_429 + FINE_BINS_PER_SECOND
    best: tuple[float, int, list[float]] = (0.0, 0, [])
    for period in FOLD_PERIODS_S:
        n = period * FINE_BINS_PER_SECOND
        if (b_end - steady_from) < 3 * n:
            continue
        att = [0] * n
        acc = [0] * n
        for b in range(steady_from, b_end):
            v = run.fine.get(b)
            if v:
                att[(b - b_onset) % n] += v[0]
                acc[(b - b_onset) % n] += v[1]
        if min(att) == 0:
            continue
        frac = [a / t for a, t in zip(acc, att, strict=True)]
        mean = statistics.fmean(frac)
        cv = statistics.pstdev(frac) / mean if mean > 0 else 0.0
        if cv > best[0]:
            best = (cv, period, frac)
    cv, period, frac = best
    excess = _burst_excess(run, onset)
    burst = burst or {}
    inferred_b = burst.get("inferred_burst_b") if burst.get("triggered") else None
    refill = burst.get("refill_rate_estimate") or 0.0
    burst_ratio = inferred_b / refill if inferred_b is not None and refill > 0 else None
    big_excess = excess is not None and excess >= TOKEN_BUCKET_EXCESS
    big_intercept = (
        burst_ratio is not None
        and inferred_b is not None
        and burst_ratio >= TOKEN_BUCKET_BURST_RATIO
        and inferred_b >= TOKEN_BUCKET_MIN_BURST
    )
    has_burst = big_excess or big_intercept
    reset = (headers.get("headers", {}).get("ratelimit-reset") or {}).get("numeric")
    notes: list[str] = []
    if reset:
        notes.append(f"RateLimit-Reset observed in [{reset['min']}, {reset['max']}]s")
    evidence = {
        "phase_cv": round(cv, 4),
        "period_s": period or None,
        "burst_excess": _round(excess, 4),
        "inferred_burst_to_refill": _round(burst_ratio, 4),
        "phase_acceptance": [round(f, 3) for f in frac],
    }
    if cv >= FIXED_WINDOW_CV and frac:
        n = len(frac)
        rise = max(range(n), key=lambda i: frac[i] - frac[i - 1])
        # A sliding log replays the first window, so acceptances resume exactly at onset.
        aligned_to_onset = rise == 0
        confidence = round(min(1.0, cv), 3)
        if aligned_to_onset:
            cls = "sliding-window"
            why = (
                f"acceptances repeat every {period}s in phase with traffic onset "
                "(sliding-log replays the initial window as old entries expire)"
            )
            confidence = round(confidence * 0.8, 3)
        else:
            cls = "fixed-window"
            why = (
                f"acceptances cluster at a fixed clock phase ({rise / FINE_BINS_PER_SECOND:.1f}s "
                f"into each {period}s period, independent of traffic onset); phase CV {cv:.2f}"
            )
    elif has_burst:
        cls = "token-bucket"
        why = (
            f"burst allowance detected (first window {_pct(excess)} above steady rate, "
            f"inferred b={inferred_b}), then 429s were spread evenly (phase CV {cv:.2f})"
        )
        confidence = round(min(1.0, 0.5 + max(excess or 0.0, burst_ratio or 0.0)), 3)
    else:
        cls = "sliding-window"
        why = (
            "no burst allowance above the steady rate and no periodic clustering; consistent "
            "with a sliding-window counter (or a token bucket/GCRA with a very small burst)"
        )
        confidence = 0.5
    return {
        "classification": cls,
        "confidence": confidence,
        "rationale": "; ".join([why, *notes]),
        "evidence": evidence,
    }


# -- entry point -------------------------------------------------------------------------


def analyze_validity(run: RunData) -> dict[str, Any]:
    """Flag runs whose offered load did not reach the target as scheduled."""
    m = run.metrics
    reasons: list[str] = []
    lag_p99 = (m.get("scheduler", {}).get("lag_ms") or {}).get("p99")
    if lag_p99 is not None and lag_p99 > MAX_VALID_LAG_P99_MS:
        reasons.append(f"scheduler lag p99 {lag_p99:.1f} ms: the client host is CPU-saturated")
    dropped = m.get("totals", {}).get("dropped", 0)
    if dropped:
        reasons.append(f"{dropped} requests dropped by the client queue")
    p99 = (m.get("latency_ms") or {}).get("p99")
    if p99 is not None and p99 > MAX_VALID_LATENCY_P99_MS:
        reasons.append(
            f"latency p99 {p99:.0f} ms: requests reach the server well after their scheduled "
            "second, so per-window limiter checks are unreliable"
        )
    return {"pass": not reasons, "reasons": reasons, "scheduler_lag_p99_ms": lag_p99}


def analyze_run(run_dir: str | Path, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    run = load_run(run_dir)
    given = {k: v for k, v in (overrides or {}).items() if v is not None}
    settings = AnalysisConfig.model_validate({**run.config.get("analysis", {}), **given})
    headers = analyze_headers(run)
    burst = analyze_burst(run, settings)
    analysis: dict[str, Any] = {
        "run_id": run.metrics.get("run_id"),
        "settings": settings.model_dump(),
        "validity": analyze_validity(run),
        "sustained": analyze_sustained(run, settings),
        "burst": burst,
        "step": analyze_step(run, settings),
        "fairness": analyze_fairness(run, settings),
        "headers": headers,
        "window_semantics": analyze_window_semantics(run, headers, burst),
    }
    checks = {
        name: section["pass"]
        for name, section in analysis.items()
        if isinstance(section, dict) and "pass" in section
    }
    analysis["checks"] = checks
    analysis["pass"] = all(checks.values())
    write_json(run.run_dir / "analysis.json", analysis)
    return analysis
