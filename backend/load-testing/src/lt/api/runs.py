"""Run lifecycle (one active worker subprocess at a time) and run-artifact access."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, cast

import yaml

from lt.api.schemas import (
    Artifact,
    LivePoint,
    Progress,
    RunDetail,
    RunListItem,
    RunStatus,
    Timeseries,
)
from lt.api.worker import EXIT_INTERRUPTED
from lt.config import Config
from lt.metrics import read_csv
from lt.utils.time import new_run_id

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ARTIFACTS = (
    "summary.json",
    "metrics.json",
    "analysis.json",
    "config.json",
    "metrics.csv",
    "routes.csv",
    "fine.csv",
    "run.log",
    "events.jsonl",
)
STAGING_DIR = ".staging"
ERROR_FILE = "error.txt"
_LOG_TAIL_BYTES = 1024 * 1024
_SHUTDOWN_GRACE_S = 30.0


class RunNotFound(LookupError):
    pass


class RunConflict(RuntimeError):
    pass


@dataclass
class _Active:
    run_id: str
    proc: subprocess.Popen[bytes]
    staging: Path
    started: float
    planned_s: float
    stopping: bool = False
    killed: bool = False


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _num(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _tail_lines(path: Path, max_bytes: int = _LOG_TAIL_BYTES) -> list[str]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > max_bytes else lines


def _error_from_stderr(path: Path) -> str | None:
    """Keep plain-text lines and ERROR-level JSON log records; drop progress chatter."""
    kept: list[str] = []
    for line in _tail_lines(path, 64 * 1024):
        try:
            rec = json.loads(line)
        except ValueError:
            if line.strip():
                kept.append(line.rstrip())
            continue
        if isinstance(rec, dict) and rec.get("level") in {"ERROR", "CRITICAL"}:
            kept.append(str(rec.get("exc") or rec.get("msg")))
    return "\n".join(kept[-20:]) or None


class RunManager:
    def __init__(self, runs_dir: Path, *, python: str = sys.executable) -> None:
        self.runs_dir = runs_dir.resolve()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._python = python
        self._lock = threading.Lock()
        self._active: _Active | None = None
        self._errors: dict[str, str] = {}

    # -- lifecycle -----------------------------------------------------------------------

    @property
    def active_run_id(self) -> str | None:
        with self._lock:
            self._reap()
            return self._active.run_id if self._active else None

    def start(self, cfg: Config) -> str:
        with self._lock:
            self._reap()
            if self._active is not None:
                raise RunConflict(f"run {self._active.run_id} is already in progress")
            run_id = new_run_id()
            staging = self.runs_dir / STAGING_DIR / run_id
            staging.mkdir(parents=True)
            cfg_path = staging / "config.yaml"
            fd = os.open(cfg_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(cfg.model_dump(mode="json"), fh, sort_keys=False)
            args = [
                self._python, "-m", "lt.api.worker",
                "--config", str(cfg_path),
                "--output-dir", str(self.runs_dir),
                "--run-id", run_id,
            ]  # fmt: skip
            with (staging / "stderr.log").open("wb") as stderr:
                proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr,
                    # Isolate from the API's console so Ctrl-C there does not abort the run.
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    start_new_session=sys.platform != "win32",
                )
            self._active = _Active(
                run_id, proc, staging, time.monotonic(), cfg.model.total_duration
            )
            return run_id

    def stop(self, run_id: str, *, force: bool = False) -> None:
        with self._lock:
            self._reap()
            active = self._active
            if active is None or active.run_id != run_id:
                self.run_dir(run_id, must_exist=True)
                raise RunConflict(f"run {run_id} is not in progress")
            if force:
                active.killed = True
                active.proc.kill()
                return
            if active.stopping:
                return
            active.stopping = True
            try:
                stdin = cast(IO[bytes], active.proc.stdin)
                stdin.write(b"stop\n")
                stdin.flush()
            except OSError:
                active.killed = True
                active.proc.kill()

    def shutdown(self) -> None:
        with self._lock:
            active = self._active
        if active is None:
            return
        with contextlib.suppress(RunConflict):
            self.stop(active.run_id)
        try:
            active.proc.wait(timeout=_SHUTDOWN_GRACE_S)
        except subprocess.TimeoutExpired:
            active.proc.kill()
            active.proc.wait(timeout=10)
        with self._lock:
            self._reap()

    def _reap(self) -> None:
        active = self._active
        if active is None or active.proc.poll() is None:
            return
        code = active.proc.returncode
        run_dir = self.runs_dir / active.run_id
        if active.killed:
            error: str | None = "run was force-stopped; artifacts may be incomplete"
        elif code not in (0, EXIT_INTERRUPTED) or not (run_dir / "summary.json").is_file():
            error = _error_from_stderr(active.staging / "stderr.log") or f"worker exited ({code})"
        else:
            error = None
        if error is not None:
            self._errors[active.run_id] = error
            if run_dir.is_dir():
                with contextlib.suppress(OSError):
                    (run_dir / ERROR_FILE).write_text(error, encoding="utf-8")
        if active.proc.stdin is not None:
            with contextlib.suppress(OSError):
                active.proc.stdin.close()
        shutil.rmtree(active.staging, ignore_errors=True)
        self._active = None

    # -- queries -------------------------------------------------------------------------

    def run_dir(self, run_id: str, *, must_exist: bool = True) -> Path:
        if not RUN_ID_RE.fullmatch(run_id):
            raise RunNotFound(run_id)
        path = (self.runs_dir / run_id).resolve()
        if path.parent != self.runs_dir or (must_exist and not path.is_dir()):
            raise RunNotFound(run_id)
        return path

    def _known_dir(self, run_id: str) -> Path:
        # The active run's directory appears only once the worker has started up.
        with self._lock:
            self._reap()
            pending = (
                self._active is not None and self._active.run_id == run_id
            ) or run_id in self._errors
            return self.run_dir(run_id, must_exist=not pending)

    def _status(self, run_id: str, run_dir: Path) -> tuple[RunStatus, str | None]:
        active = self._active
        if active is not None and active.run_id == run_id:
            return ("stopping" if active.stopping else "running"), None
        summary = _read_json(run_dir / "summary.json")
        if summary is not None:
            return ("interrupted" if summary.get("interrupted") else "completed"), None
        error = self._errors.get(run_id)
        if error is None:
            try:
                error = (run_dir / ERROR_FILE).read_text(encoding="utf-8")
            except OSError:
                error = (
                    "run did not produce a summary (ended abnormally or still running elsewhere)"
                )
        return "failed", error

    def list_runs(self) -> list[RunListItem]:
        with self._lock:
            self._reap()
            dirs = [
                d
                for d in self.runs_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".") and RUN_ID_RE.fullmatch(d.name)
            ]
            dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
            items: list[RunListItem] = []
            for d in dirs:
                status, _ = self._status(d.name, d)
                summary = _read_json(d / "summary.json") or {}
                config = _read_json(d / "config.json") or {}
                analysis = _read_json(d / "analysis.json")
                items.append(
                    RunListItem(
                        run_id=d.name,
                        status=status,
                        name=summary.get("name", config.get("name")),
                        base_url=summary.get("base_url", config.get("base_url")),
                        started_at=summary.get("started_at"),
                        finished_at=summary.get("finished_at"),
                        duration_s=summary.get("duration_s"),
                        totals=summary.get("totals"),
                        means=summary.get("means"),
                        ratios=summary.get("ratios"),
                        latency_ms=summary.get("latency_ms"),
                        analysis_pass=analysis.get("pass") if analysis else None,
                    )
                )
            return items

    def detail(self, run_id: str) -> RunDetail:
        run_dir = self._known_dir(run_id)
        with self._lock:
            status, error = self._status(run_id, run_dir)
            active = self._active
            progress = (
                Progress(
                    elapsed_s=round(time.monotonic() - active.started, 3),
                    planned_duration_s=active.planned_s,
                )
                if active is not None and active.run_id == run_id
                else None
            )
        artifacts = [
            Artifact(name=name, size=(run_dir / name).stat().st_size)
            for name in ARTIFACTS
            if (run_dir / name).is_file()
        ]
        return RunDetail(
            run_id=run_id,
            status=status,
            error=error,
            progress=progress,
            config=_read_json(run_dir / "config.json"),
            summary=_read_json(run_dir / "summary.json"),
            metrics=_read_json(run_dir / "metrics.json"),
            analysis=_read_json(run_dir / "analysis.json"),
            artifacts=artifacts,
        )

    def timeseries(self, run_id: str) -> Timeseries:
        run_dir = self._known_dir(run_id)
        metrics: list[dict[str, float | None]] = []
        routes: list[dict[str, Any]] = []
        with contextlib.suppress(OSError, ValueError):
            metrics = [
                {k: _num(v) for k, v in row.items()} for row in read_csv(run_dir / "metrics.csv")
            ]
        with contextlib.suppress(OSError, ValueError):
            routes = [
                {k: (v if k == "route" else _num(v)) for k, v in row.items()}
                for row in read_csv(run_dir / "routes.csv")
            ]
        live: list[LivePoint] = []
        for rec in self._log_records(run_dir):
            if rec.get("msg") == "progress" and isinstance(rec.get("second"), int):
                with contextlib.suppress(TypeError, ValueError):
                    live.append(LivePoint.model_validate(rec))
        return Timeseries(metrics=metrics, live=live, routes=routes)

    def logs(self, run_id: str, tail: int) -> list[dict[str, Any]]:
        return self._log_records(self._known_dir(run_id))[-tail:]

    @staticmethod
    def _log_records(run_dir: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line in _tail_lines(run_dir / "run.log"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                records.append(rec)
        return records

    def artifact(self, run_id: str, name: str) -> Path:
        if name not in ARTIFACTS:
            raise RunNotFound(name)
        path = self.run_dir(run_id) / name
        if not path.is_file():
            raise RunNotFound(name)
        return path

    def ensure_idle(self, run_id: str) -> Path:
        with self._lock:
            self._reap()
            run_dir = self.run_dir(run_id)
            if self._active is not None and self._active.run_id == run_id:
                raise RunConflict(f"run {run_id} is still in progress")
            return run_dir

    def delete(self, run_id: str) -> None:
        run_dir = self.ensure_idle(run_id)
        shutil.rmtree(run_dir)
        self._errors.pop(run_id, None)
