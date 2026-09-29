"""Human-readable rendering of run summaries and analysis results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReportError(RuntimeError):
    """Raised when a run directory has no summary."""


def load_summary(run_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    d = Path(run_dir)
    path = d / "summary.json"
    if not path.is_file():
        raise ReportError(f"{path} not found; is {d} a run directory?")
    summary = json.loads(path.read_text(encoding="utf-8"))
    analysis_path = d / "analysis.json"
    analysis = (
        json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.is_file() else None
    )
    return summary, analysis


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}{unit}"
    return f"{v}{unit}"


def _verdict(passed: bool | None) -> str:
    return "info" if passed is None else ("PASS" if passed else "FAIL")


def format_summary(summary: dict[str, Any], analysis: dict[str, Any] | None = None) -> str:
    t, m, lat = summary["totals"], summary["means"], summary["latency_ms"]
    name = f"  ({summary['name']})" if summary.get("name") else ""
    lines = [
        f"run        {summary['run_id']}{name}",
        f"target     {summary['base_url']}",
        f"duration   {_fmt(summary['duration_s'], 's')}"
        + ("  [INTERRUPTED]" if summary.get("interrupted") else ""),
        "",
        f"{'':12}{'total':>12}{'mean rps':>12}",
        f"{'attempted':12}{t['attempted']:>12,}{m['attempted_rps']:>12,.1f}",
        f"{'accepted':12}{t['accepted']:>12,}{m['accepted_rps']:>12,.1f}",
        f"{'429':12}{t['429']:>12,}{m['429_rps']:>12,.1f}",
        f"{'errors':12}{t['errors']:>12,}{m['error_rps']:>12,.1f}",
        "",
        "latency ms (from scheduled time, CO-safe)",
        "  " + "  ".join(f"{k}={_fmt(lat.get(k))}" for k in ("p50", "p90", "p95", "p99", "max")),
        "",
        f"scheduler  rate error {_fmt(summary['scheduler']['rate_error_pct'], '%')}, "
        f"mean |window error| {_fmt(summary['scheduler']['mean_abs_window_error_pct'], '%')}, "
        f"lag p99 {_fmt(summary['scheduler']['lag_p99_ms'], 'ms')}",
        "status     " + ", ".join(f"{k}: {v:,}" for k, v in summary["status_codes"].items()),
    ]
    aggregate = summary.get("aggregate")
    if aggregate:
        lines += ["", format_aggregate(aggregate)]
    thresholds = summary.get("thresholds") or {}
    if thresholds.get("checks"):
        lines += ["", format_thresholds(thresholds)]
    if analysis:
        lines += ["", format_analysis(analysis)]
    return "\n".join(lines)


_AGG_COLS = (
    ("samples", "samples", 9), ("avg_ms", "avg", 9), ("median_ms", "median", 9),
    ("p90_ms", "p90", 9), ("p95_ms", "p95", 9), ("p99_ms", "p99", 9), ("max_ms", "max", 9),
    ("error_pct", "error%", 8), ("throughput_rps", "req/s", 10), ("apdex", "apdex", 7),
)  # fmt: skip


def format_aggregate(rows: list[dict[str, Any]]) -> str:
    """JMeter-style Aggregate Report table."""
    width = min(max((len(r["label"]) for r in rows), default=5), 40)
    out = ["aggregate report", f"  {'label':<{width}}" + "".join(f"{h:>{w}}" for _, h, w in _AGG_COLS)]
    for r in rows:
        cells = ""
        for key, _, w in _AGG_COLS:
            v = r.get(key)
            text = "-" if v is None else (f"{v:,.1f}" if isinstance(v, float) else f"{v:,}")
            cells += f"{text:>{w}}"
        out.append(f"  {r['label'][:width]:<{width}}{cells}")
    return "\n".join(out)


def format_thresholds(result: dict[str, Any]) -> str:
    lines = [f"thresholds [{_verdict(result.get('pass'))}]"]
    for c in result["checks"]:
        actual = "n/a" if c["actual"] is None else f"{c['actual']:,.4g}"
        mark = "ok  " if c["pass"] else "FAIL"
        lines.append(f"  {mark} {c['scope']}: {c['metric']} {actual} {c['op']} {c['limit']:g}")
    return "\n".join(lines)


def format_analysis(a: dict[str, Any]) -> str:
    lines = ["analysis"]
    v = a.get("validity")
    if v:
        lines.append(f"  validity   [{_verdict(v['pass'])}]")
        lines += [f"             {reason}" for reason in v["reasons"]]
    s = a["sustained"]
    if s.get("applicable"):
        lines.append(
            f"  sustained  [{_verdict(s.get('pass'))}] accepted {s['mean_accepted_rps']:,.1f} rps "
            f"vs target {s['target_rps']:,.1f} ({s['deviation_pct']:+.2f}%, "
            f"tol +/-{s['tolerance_pct']:g}%), 429 {s['mean_429_rps']:,.1f} rps"
        )
    b = a["burst"]
    if b.get("triggered"):
        lines.append(
            f"  burst      [{_verdict(b.get('pass'))}] inferred b={b['inferred_burst_b']:,.1f}, "
            f"refill~{b['refill_rate_estimate']:,.1f}/s, first window "
            f"{b['first_window_acceptances']:,}"
        )
    st = a["step"]
    if st.get("applicable"):
        knee = st.get("knee_point")
        knee_s = f"knee at {knee['asked']:g} rps ({knee['reason']})" if knee else "no knee"
        lines.append(
            f"  step       [{_verdict(st.get('pass'))}] {knee_s}, capacity~"
            f"{_fmt(st.get('estimated_capacity_rps'))} rps"
        )
        for c in st["capacity_curve"]:
            lines.append(
                f"               asked {c['asked']:>9,.0f}  accepted {c['accepted']:>9,.1f}  "
                f"429 {c['429_rate'] * 100:5.1f}%"
            )
    f = a["fairness"]
    if f.get("applicable"):
        split = ", ".join(f"{k}={v['accepted_rps']:,.1f}" for k, v in f["tenants"].items())
        lines.append(
            f"  fairness   [{_verdict(f.get('pass'))}] accepted ratio "
            f"{_fmt(f.get('fairness_ratio'))}, fair-share ratio {_fmt(f.get('fair_share_ratio'))} "
            f"(threshold {f['threshold']}); {split}"
        )
    h = a["headers"]
    lines.append(
        f"  headers    style={h['style']}, Retry-After on 429s "
        f"{h['retry_after_on_429_ratio'] * 100:.1f}%"
    )
    w = a["window_semantics"]
    lines.append(f"  semantics  {w['classification']} (confidence {w['confidence']:.2f})")
    lines.append(f"             {w['rationale']}")
    lines.append(f"  overall    {'PASS' if a.get('pass') else 'FAIL'}")
    return "\n".join(lines)
