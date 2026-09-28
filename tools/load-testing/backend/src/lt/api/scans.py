"""Scans: discover a web app's APIs with Playwright, then load-test each one in sequence."""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml

from lt.analyze import AnalysisError, analyze_run
from lt.api.runs import RunConflict, RunManager
from lt.api.schemas import (
    DiscoveredEndpoint,
    ScanDetail,
    ScanItem,
    ScanOptionsOut,
    ScanRequest,
    ScanSummary,
)
from lt.config import Config, ConfigError, SafetyError
from lt.discover import DiscoveryOptions, DiscoveryResult, Endpoint, LoadPlan, build_configs
from lt.utils.time import new_run_id, utc_now_iso

SCANS_DIR = ".scans"
SCAN_ID_RE = re.compile(r"^scan-[A-Za-z0-9._-]{1,120}$")
_POLL_S = 1.0
_ACTIVE = frozenset({"discovering", "running"})
_FINISHED_ITEMS = frozenset({"completed", "interrupted", "failed", "skipped", "cancelled"})

Prepare = Callable[[str], Config]


class ScanNotFound(LookupError):
    pass


class ScanConflict(RuntimeError):
    pass


@dataclass
class _Scan:
    id: str
    url: str
    created_at: str
    options: DiscoveryOptions
    status: str = "discovering"
    error: str | None = None
    result: DiscoveryResult | None = None
    plan: LoadPlan | None = None
    items: list[ScanItem] = field(default_factory=list)
    # Runtime-only state; never persisted (headers may hold credentials).
    cancel: threading.Event = field(default_factory=threading.Event)
    proc: subprocess.Popen[bytes] | None = None

    def endpoint_out(self, ep: Endpoint) -> DiscoveredEndpoint:
        return DiscoveredEndpoint(
            id=ep.id,
            method=ep.method,
            base_url=ep.base_url,
            path=ep.path,
            template=ep.template,
            resource_type=ep.resource_type,
            in_scope=ep.in_scope,
            sensitive=ep.sensitive,
            safe=ep.safe,
            count=ep.count,
            status=ep.status,
            content_type=ep.content_type,
            has_body=ep.body is not None,
            pages=ep.pages,
        )

    def summary(self) -> ScanSummary:
        return ScanSummary(
            id=self.id,
            url=self.url,
            status=self.status,
            created_at=self.created_at,
            error=self.error,
            endpoints_found=len(self.result.endpoints) if self.result else 0,
            items_total=len(self.items),
            items_done=sum(1 for i in self.items if i.status in _FINISHED_ITEMS),
        )

    def detail(self) -> ScanDetail:
        o = self.options
        r = self.result
        return ScanDetail(
            **self.summary().model_dump(),
            options=ScanOptionsOut(
                max_pages=o.max_pages,
                max_depth=o.max_depth,
                wait_ms=o.wait_ms,
                scope=o.scope_patterns(),
                header_names=sorted(o.headers),
            ),
            pages=r.pages if r else [],
            discovery_errors=r.errors if r else [],
            out_of_scope_hosts=r.out_of_scope_hosts if r else {},
            endpoints=[self.endpoint_out(e) for e in r.endpoints] if r else [],
            plan=self.plan,
            items=[i.model_copy() for i in self.items],
        )

    def to_disk(self) -> dict[str, Any]:
        opts = self.options.model_dump()
        opts["headers"] = {}
        return {
            "id": self.id,
            "url": self.url,
            "created_at": self.created_at,
            "options": opts,
            "status": self.status,
            "error": self.error,
            "result": self.result.to_dict() if self.result else None,
            "plan": self.plan.model_dump() if self.plan else None,
            "items": [i.model_dump() for i in self.items],
        }

    @classmethod
    def from_disk(cls, data: dict[str, Any]) -> _Scan:
        scan = cls(
            id=data["id"],
            url=data["url"],
            created_at=data["created_at"],
            options=DiscoveryOptions.model_validate(data["options"]),
            status=data["status"],
            error=data.get("error"),
            result=DiscoveryResult.from_dict(data["result"]) if data.get("result") else None,
            plan=LoadPlan.model_validate(data["plan"]) if data.get("plan") else None,
            items=[ScanItem.model_validate(i) for i in data.get("items", [])],
        )
        if scan.status in _ACTIVE:
            scan.status, scan.error = "failed", "interrupted by an API server restart"
            for item in scan.items:
                if item.status in {"pending", "running"}:
                    item.status = "cancelled"
        return scan


def _discovery_timeout(opts: DiscoveryOptions) -> float:
    per_page = (2 * opts.nav_timeout_ms + opts.wait_ms) / 1000
    return min(60 + opts.max_pages * per_page, 30 * 60)


class ScanManager:
    def __init__(self, runs: RunManager, prepare: Prepare, *, python: str = sys.executable):
        self.runs = runs
        self.prepare = prepare
        self.dir = runs.runs_dir / SCANS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._python = python
        self._lock = threading.Lock()
        self._scans: dict[str, _Scan] = {}
        self._configs: dict[str, list[Config | None]] = {}
        self._threads: list[threading.Thread] = []
        for path in self.dir.glob("scan-*.json"):
            with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
                scan = _Scan.from_disk(json.loads(path.read_text(encoding="utf-8")))
                self._scans[scan.id] = scan

    # -- persistence ---------------------------------------------------------------------

    def _save(self, scan: _Scan) -> None:
        tmp = self.dir / f"{scan.id}.json.tmp"
        tmp.write_text(json.dumps(scan.to_disk(), default=str), encoding="utf-8")
        tmp.replace(self.dir / f"{scan.id}.json")

    def _get(self, scan_id: str) -> _Scan:
        scan = self._scans.get(scan_id) if SCAN_ID_RE.fullmatch(scan_id) else None
        if scan is None:
            raise ScanNotFound(scan_id)
        return scan

    def _spawn(self, target: Callable[..., None], *args: Any) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True, name="lt-scan")
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    # -- queries -------------------------------------------------------------------------

    def list_scans(self) -> list[ScanSummary]:
        with self._lock:
            scans = sorted(self._scans.values(), key=lambda s: s.created_at, reverse=True)
            return [s.summary() for s in scans]

    def get(self, scan_id: str) -> ScanDetail:
        with self._lock:
            return self._get(scan_id).detail()

    # -- lifecycle -----------------------------------------------------------------------

    def start(self, req: ScanRequest) -> ScanDetail:
        scan = _Scan(
            id=f"scan-{new_run_id()}",
            url=req.discovery.url,
            created_at=utc_now_iso(),
            options=req.discovery,
            plan=req.plan if req.auto_run else None,
        )
        with self._lock:
            self._scans[scan.id] = scan
            self._save(scan)
        self._spawn(self._discover, scan, req)
        return self.get(scan.id)

    def run(self, scan_id: str, endpoint_ids: list[str], plan: LoadPlan) -> ScanDetail:
        with self._lock:
            scan = self._get(scan_id)
            if scan.status in _ACTIVE:
                raise ScanConflict(f"scan is {scan.status}")
            if scan.result is None:
                raise ScanConflict("scan has no discovered endpoints")
            self._plan(scan, endpoint_ids, plan)
        self._spawn(self._execute, scan)
        return self.get(scan_id)

    def cancel(self, scan_id: str) -> ScanDetail:
        with self._lock:
            scan = self._get(scan_id)
            if scan.status not in _ACTIVE:
                raise ScanConflict(f"scan is {scan.status}")
            scan.cancel.set()
            if scan.proc is not None and scan.proc.poll() is None:
                scan.proc.kill()
        return self.get(scan_id)

    def delete(self, scan_id: str) -> None:
        with self._lock:
            scan = self._get(scan_id)
            if scan.status in _ACTIVE:
                raise ScanConflict("cancel the scan before deleting it")
            del self._scans[scan_id]
            (self.dir / f"{scan_id}.json").unlink(missing_ok=True)

    def shutdown(self) -> None:
        with self._lock:
            for scan in self._scans.values():
                if scan.status in _ACTIVE:
                    scan.cancel.set()
                    if scan.proc is not None and scan.proc.poll() is None:
                        scan.proc.kill()
        for thread in self._threads:
            thread.join(timeout=60)

    # -- workers -------------------------------------------------------------------------

    def _discover(self, scan: _Scan, req: ScanRequest) -> None:
        try:
            result = self._run_discovery(scan)
        except Exception as exc:  # surface any failure on the scan
            with self._lock:
                cancelled = scan.cancel.is_set()
                scan.status = "cancelled" if cancelled else "failed"
                scan.error = None if cancelled else str(exc)
                self._save(scan)
            return
        with self._lock:
            scan.result = result
            scan.status = "discovered"
            selected = [
                e.id
                for e in result.endpoints
                if e.in_scope and not e.sensitive and (e.safe or req.include_unsafe_methods)
            ]
            auto = req.auto_run and bool(selected)
            if auto:
                self._plan(scan, selected, req.plan)
            self._save(scan)
        if auto:
            self._execute(scan)

    def _run_discovery(self, scan: _Scan) -> DiscoveryResult:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [self._python, "-m", "lt.discover"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with self._lock:
            scan.proc = proc
        try:
            out, err = proc.communicate(
                scan.options.model_dump_json().encode(), timeout=_discovery_timeout(scan.options)
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RuntimeError("discovery timed out") from None
        finally:
            with self._lock:
                scan.proc = None
        if scan.cancel.is_set():
            raise RuntimeError("cancelled")
        if proc.returncode != 0:
            lines = err.decode(errors="replace").strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"discovery exited ({proc.returncode})")
        return DiscoveryResult.from_dict(json.loads(out))

    def _plan(self, scan: _Scan, endpoint_ids: list[str], plan: LoadPlan) -> None:
        assert scan.result is not None
        by_id = {e.id: e for e in scan.result.endpoints}
        chosen = [by_id[i] for i in endpoint_ids if i in by_id]
        if not chosen:
            raise ScanConflict("none of the selected endpoints belong to this scan")
        items: list[ScanItem] = []
        configs: list[Config | None] = []
        for ids, data in build_configs(
            chosen,
            plan,
            scan.options.headers,
            verify_tls=not scan.options.ignore_https_errors,
        ):
            item = ScanItem(name=str(data["name"]), endpoint_ids=ids)
            try:
                configs.append(self.prepare(yaml.safe_dump(data, sort_keys=False)))
            except (ConfigError, SafetyError) as exc:
                item.status, item.error = "skipped", str(exc)
                configs.append(None)
            items.append(item)
        scan.plan, scan.items, scan.status, scan.error = plan, items, "running", None
        scan.cancel.clear()
        self._configs[scan.id] = configs

    def _execute(self, scan: _Scan) -> None:
        configs: list[Config | None] = self._configs.pop(scan.id, [])
        for item, cfg in zip(scan.items, configs, strict=True):
            if item.status == "skipped" or cfg is None:
                continue
            if scan.cancel.is_set():
                with self._lock:
                    item.status = "cancelled"
                continue
            self._run_item(scan, item, cfg)
        with self._lock:
            scan.status = "cancelled" if scan.cancel.is_set() else "completed"
            self._save(scan)

    def _run_item(self, scan: _Scan, item: ScanItem, cfg: Config) -> None:
        run_id: str | None = None
        while run_id is None:
            if scan.cancel.is_set():
                with self._lock:
                    item.status = "cancelled"
                return
            try:
                run_id = self.runs.start(cfg)
            except RunConflict:
                scan.cancel.wait(_POLL_S)  # another run is active; queue behind it
        with self._lock:
            item.status, item.run_id = "running", run_id
            self._save(scan)
        stopped = False
        while True:
            detail = self.runs.detail(run_id)
            if detail.status not in ("running", "stopping"):
                break
            if scan.cancel.is_set() and not stopped:
                with contextlib.suppress(RunConflict):
                    self.runs.stop(run_id)
                stopped = True
            time.sleep(_POLL_S)
        analysis_pass: bool | None = None
        if detail.status in ("completed", "interrupted"):
            with contextlib.suppress(AnalysisError, ValueError, OSError):
                analysis_pass = bool(analyze_run(self.runs.run_dir(run_id))["pass"])
        s = detail.summary or {}
        with self._lock:
            item.status = detail.status  # type: ignore[assignment]
            item.error = detail.error
            item.accepted_rps = (s.get("means") or {}).get("accepted_rps")
            item.ratio_429 = (s.get("ratios") or {}).get("429")
            item.p99_ms = (s.get("latency_ms") or {}).get("p99")
            item.analysis_pass = analysis_pass
            self._save(scan)
