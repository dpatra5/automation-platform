"""Pass/fail thresholds (SLA) evaluated against the aggregate report."""

from __future__ import annotations

from typing import Any

from lt.config import ThresholdSet, ThresholdsConfig
from lt.metrics import TOTAL_LABEL

# threshold field -> (aggregate column, comparison, scale applied to the limit)
_CHECKS: dict[str, tuple[str, str, float]] = {
    "avg_ms": ("avg_ms", "<=", 1.0),
    "p50_ms": ("median_ms", "<=", 1.0),
    "p90_ms": ("p90_ms", "<=", 1.0),
    "p95_ms": ("p95_ms", "<=", 1.0),
    "p99_ms": ("p99_ms", "<=", 1.0),
    "max_ms": ("max_ms", "<=", 1.0),
    "error_rate": ("error_pct", "<=", 100.0),
    "min_rps": ("throughput_rps", ">=", 1.0),
    "min_apdex": ("apdex", ">=", 1.0),
}


def _checks(scope: str, limits: ThresholdSet, row: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, (column, op, scale) in _CHECKS.items():
        limit = getattr(limits, name)
        if limit is None:
            continue
        actual = row.get(column) if row else None
        bound = limit * scale
        if actual is None:
            ok = False
        else:
            ok = actual <= bound if op == "<=" else actual >= bound
        out.append(
            {
                "scope": scope,
                "metric": name,
                "op": op,
                "limit": limit,
                "actual": actual / scale if actual is not None else None,
                "pass": ok,
            }
        )
    return out


def evaluate(thresholds: ThresholdsConfig, aggregate: list[dict[str, Any]]) -> dict[str, Any]:
    """``{"pass": bool | None, "checks": [...]}``; ``pass`` is None when nothing is configured."""
    rows = {r["label"]: r for r in aggregate}
    checks = _checks(TOTAL_LABEL, thresholds, rows.get(TOTAL_LABEL))
    for route, limits in thresholds.routes.items():
        checks += _checks(route, limits, rows.get(route))
    return {"pass": all(c["pass"] for c in checks) if checks else None, "checks": checks}
