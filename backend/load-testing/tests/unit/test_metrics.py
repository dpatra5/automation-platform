from __future__ import annotations

import json
from pathlib import Path

import pytest

from lt.metrics import (
    MAX_DISTINCT_HEADER_VALUES,
    OTHER_VALUES,
    EventSink,
    HeaderStat,
    LatencyHistogram,
    MetricsCollector,
    read_csv,
    status_family,
    write_csv,
    write_json,
)


def test_status_family() -> None:
    assert status_family(None) == "error"
    assert status_family(200) == "2xx"
    assert status_family(301) == "3xx"
    assert status_family(429) == "429"
    assert status_family(404) == "4xx"
    assert status_family(503) == "5xx"


def test_window_binning_uses_scheduled_offset() -> None:
    c = MetricsCollector()
    for off in (0.1, 0.99, 1.0, 1.5, 2.2):
        c.record_attempt(off, "r", 0.0)
    # Latency of 5 s must not move the sample out of its scheduled window.
    c.record_result(0.99, "r", 200, 5.0)
    c.record_result(1.0, "r", 429, 0.01)
    c.record_result(1.5, "r", 503, 0.01)
    c.record_result(2.2, "r", None, 0.01, error_type="ReadTimeout")
    assert c.windows[0].attempted == 2 and c.windows[0].accepted == 1
    assert c.windows[1].s429 == 1 and c.windows[1].errors == 1
    assert c.windows[2].errors == 1
    assert c.error_types["ReadTimeout"] == 1
    assert c.status_codes == {"200": 1, "429": 1, "503": 1}
    assert c.fine[9] == [1, 1, 0]
    assert c.totals() == {"attempted": 5, "accepted": 1, "429": 1, "errors": 2, "dropped": 0}


def test_3xx_counts_as_accepted_and_dropped_as_error() -> None:
    c = MetricsCollector()
    c.record_attempt(0.1, "r", 0.0)
    c.record_result(0.1, "r", 302, 0.01)
    c.record_attempt(0.2, "r", 0.0)
    c.record_dropped(0.2, "r")
    assert c.windows[0].accepted == 1
    assert c.windows[0].dropped == 1 and c.windows[0].errors == 1
    assert c.error_types["ClientQueueFull"] == 1


def test_histogram_percentiles_and_empty() -> None:
    h = LatencyHistogram()
    assert h.percentile_ms(50) is None
    assert h.summary_ms()["p99"] is None
    for ms in range(1, 101):
        h.record_s(ms / 1000)
    assert h.count == 100
    assert h.percentile_ms(50) == pytest.approx(50, rel=0.01)
    assert h.percentile_ms(99) == pytest.approx(99, rel=0.01)
    summary = h.summary_ms()
    assert summary["max"] == pytest.approx(100, rel=0.01)
    h.record_s(10_000)  # clamped, never raises
    h.record_s(-1)


def test_histogram_merge_roundtrip() -> None:
    a, b = LatencyHistogram(), LatencyHistogram()
    for ms in (1, 5, 10, 50, 250):
        a.record_s(ms / 1000)
    b.merge(a)
    b.merge(LatencyHistogram())
    assert b.count == a.count
    assert b.percentile_ms(50) == a.percentile_ms(50)
    assert b.summary_ms()["max"] == a.summary_ms()["max"]


def test_empty_windows_render_safely() -> None:
    c = MetricsCollector()
    rows = c.metric_rows(3.0)
    assert len(rows) == 3
    assert rows[0]["p50_ms"] is None and rows[0]["attempted_rps"] == 0


def test_partial_last_window_is_scaled() -> None:
    c = MetricsCollector()
    for i in range(5):
        c.record_attempt(1.0 + i * 0.1, "r", 0.0)
    rows = c.metric_rows(1.5)
    assert rows[1]["attempted_rps"] == pytest.approx(10.0)


def test_state_merge_preserves_totals_and_latency() -> None:
    src = MetricsCollector()
    for i in range(50):
        off = i * 0.05
        route = "a" if i % 2 else "b"
        src.record_attempt(off, route, 0.001)
        src.record_result(
            off,
            route,
            200 if i % 3 else 429,
            0.01 + i / 1000,
            headers={"RateLimit-Remaining": str(i), "Retry-After": "1"},
            expected=i % 5 != 0,
        )
    dst = MetricsCollector()
    dst.merge_state(src.to_state())
    dst.merge_state(MetricsCollector().to_state())
    assert dst.totals() == src.totals()
    assert dst.overall.percentile_ms(90) == src.overall.percentile_ms(90)
    assert dst.route_totals() == src.route_totals()
    assert dst.header_summary() == src.header_summary()
    assert dst.fine_rows() == src.fine_rows()
    assert dst.metric_rows(3) == src.metric_rows(3)


def test_finalize_then_late_samples() -> None:
    c = MetricsCollector()
    c.record_attempt(0.5, "r", 0.0)
    c.record_result(0.5, "r", 200, 0.02)
    c.finalize_before(1)
    assert c.windows[0].final is not None and c.windows[0].hist is None
    c.record_result(0.6, "r", 200, 0.03)
    assert c.late_samples == 1
    assert c.windows[0].accepted == 2
    state = MetricsCollector()
    state.record_result(0.7, "r", 200, 0.01)
    c.merge_state(state.to_state())
    assert c.late_samples == 2
    assert c.metric_rows(1)[0]["p50_ms"] == pytest.approx(20, rel=0.02)


def test_header_stat_numeric_dates_and_distinct_cap() -> None:
    s = HeaderStat()
    s.record("retry-after", "2", True)
    s.record("retry-after", "Wed, 21 Oct 2015 07:28:00 GMT", True)
    s.record("retry-after", "not-a-date", False)
    assert s.count == 3 and s.count_429 == 2
    assert s.numeric_count == 2 and s.numeric_min == 0.0 and s.numeric_max == 2.0
    other = HeaderStat()
    for i in range(MAX_DISTINCT_HEADER_VALUES + 5):
        other.record("ratelimit-policy", f"v{i}", False)
    assert other.values[OTHER_VALUES] == 5
    merged = HeaderStat()
    merged.merge_state(other.to_state())
    assert merged.count == other.count
    summary = s.summary(total_responses=6)
    assert summary["presence_ratio"] == 0.5
    assert HeaderStat().summary(0)["numeric"] is None


def test_event_sink_sampling_and_bounds(tmp_path: Path) -> None:
    sink = EventSink(tmp_path / "e.jsonl", sample_rate=1.0, max_buffer=3)
    assert sink.enabled
    for i in range(5):
        sink.offer({"i": i})
    sink.flush()
    sink.flush()
    lines = (tmp_path / "e.jsonl").read_text().splitlines()
    assert [json.loads(x)["i"] for x in lines] == [0, 1, 2]
    assert sink.dropped == 2 and sink.written == 3
    off = EventSink(tmp_path / "none.jsonl", sample_rate=0.0)
    off.offer({"x": 1})
    off.flush()
    assert not off.enabled and not (tmp_path / "none.jsonl").exists()


def test_csv_and_json_writers(tmp_path: Path) -> None:
    write_csv(tmp_path / "m.csv", ["a", "b"], [{"a": 1, "b": None}, {"a": 2, "b": 3.5}])
    assert read_csv(tmp_path / "m.csv") == [{"a": "1", "b": ""}, {"a": "2", "b": "3.5"}]
    write_json(tmp_path / "x.json", {"k": [1, 2]})
    assert json.loads((tmp_path / "x.json").read_text()) == {"k": [1, 2]}
    assert not list(tmp_path.glob("*.tmp"))
