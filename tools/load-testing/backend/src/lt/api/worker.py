"""Subprocess entry point for API-launched runs.

Reads a staged config (deleting it immediately, since it may hold credentials), executes
``run_load`` on the main thread so the engine's graceful-stop handling works, and turns a
``stop`` line on stdin (or stdin closing because the API died) into a SIGINT.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from lt.config import ConfigError, SafetyError, parse_config_text
from lt.logging import setup_logging

EXIT_INVALID = 2
EXIT_INTERRUPTED = 130


def _watch_stdin() -> None:
    for line in sys.stdin:
        if line.strip() == "stop":
            signal.raise_signal(signal.SIGINT)
    signal.raise_signal(signal.SIGINT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lt-api-worker")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    setup_logging(args.log_level)
    try:
        text = args.config.read_text(encoding="utf-8")
    finally:
        args.config.unlink(missing_ok=True)
    try:
        cfg = parse_config_text(text, expand_env=False)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID

    from lt.engine import run_load

    threading.Thread(target=_watch_stdin, name="lt-stop-watch", daemon=True).start()
    try:
        result = run_load(cfg, output_dir=args.output_dir, run_id=args.run_id)
    except SafetyError as exc:
        print(f"safety check failed: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    return EXIT_INTERRUPTED if result.interrupted else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
