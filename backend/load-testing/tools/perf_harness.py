"""Local accuracy harness: runs limiter scenarios against the in-process demo server.

Usage: python tools/perf_harness.py [--scale 1.0]
Scale multiplies all rates (e.g. --scale 5 for a 1000 RPS token-bucket check).
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path
from typing import Any

from lt.analyze import analyze_run
from lt.config import parse_config
from lt.demo_server import Algo, DemoServerProcess, DemoSettings
from lt.engine import run_load
from lt.logging import setup_logging
from lt.report import format_analysis, format_summary


def scenario(
    name: str, settings: DemoSettings, profile: list[dict[str, Any]], analysis: dict[str, Any]
) -> None:
    out = Path(tempfile.mkdtemp(prefix="lt-harness-"))
    try:
        with DemoServerProcess(settings) as srv:
            cfg = parse_config(
                {
                    "name": name,
                    "base_url": srv.base_url,
                    "safety": {"allowlist": ["127.0.0.1"], "max_rps_cap": 20_000},
                    "model": {"workers": 4, "profile": profile},
                    "http": {"warmup_requests": 32, "warmup_path": "/healthz"},
                    "routes": [{"name": "items", "path": "/api/items"}],
                    "analysis": analysis,
                }
            )
            result = run_load(cfg, output_dir=out)
        print(f"\n=== {name} ===")
        print(format_summary(result.summary))
        print(format_analysis(analyze_run(result.run_dir)))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--seconds", type=int, default=6)
    args = parser.parse_args()
    s, n = args.scale, args.seconds
    setup_logging("WARNING")
    scenario(
        "token-bucket burst",
        DemoSettings(rate=100 * s, burst=int(200 * s)),
        [{"duration": "1s", "rate": 0}, {"duration": f"{n}s", "rate": 600 * s}],
        {"expected_limit_rps": 100 * s, "expected_burst": 200 * s},
    )
    for algo in ("fixed-window", "sliding-window"):
        algo_t: Algo = algo  # type: ignore[assignment]
        scenario(
            algo,
            DemoSettings(rate=200 * s, algo=algo_t),
            [{"duration": f"{n}s", "rate": 400 * s}],
            {"expected_limit_rps": 200 * s},
        )


if __name__ == "__main__":
    main()
