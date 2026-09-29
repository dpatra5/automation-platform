"""FastAPI application exposing validation, run control, analysis, and the demo server."""

from __future__ import annotations

import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lt import __version__
from lt.analyze import AnalysisError, analyze_run
from lt.api.demo import DemoConflict, DemoManager
from lt.api.runs import RunConflict, RunManager, RunNotFound
from lt.api.scans import ScanConflict, ScanManager, ScanNotFound
from lt.api.schemas import (
    AnalyzeRequest,
    ConfigRequest,
    ConfigSummary,
    DemoServerRequest,
    DemoServerState,
    Example,
    Health,
    ProfileStepOut,
    RouteOut,
    RunDetail,
    RunListItem,
    ScanDetail,
    ScanRequest,
    ScanRunRequest,
    ScanSummary,
    StopRequest,
    Timeseries,
    ValidationResult,
)
from lt.api.settings import ApiSettings
from lt.config import (
    Config,
    ConfigError,
    SafetyError,
    SafetyReport,
    apply_overrides,
    check_safety,
    host_allowed,
    parse_config_text,
)

_ENV_REF_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}")
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def _error_lines(exc: Exception) -> list[str]:
    lines = [ln.strip() for ln in str(exc).splitlines()]
    return [ln for ln in lines if ln and ln != "invalid configuration:"]


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    runs = RunManager(settings.runs_dir)
    demo = DemoManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await run_in_threadpool(scans.shutdown)
        await run_in_threadpool(runs.shutdown)
        await run_in_threadpool(demo.stop)

    app = FastAPI(
        title="lt API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.runs = runs
    app.state.demo = demo

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if not path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", _CSP)
        return response

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.token is None:
            return
        scheme, _, value = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
            value.encode(), settings.token.encode()
        ):
            raise HTTPException(
                401, "missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"}
            )

    def build_config(req: ConfigRequest) -> tuple[Config, SafetyReport]:
        if len(req.yaml.encode()) > settings.max_config_bytes:
            raise ConfigError(f"config exceeds {settings.max_config_bytes // 1024} KiB")
        if _ENV_REF_RE.search(req.yaml):
            raise ConfigError(
                "environment variable references (${...}) are not allowed via the API"
            )
        cfg = parse_config_text(req.yaml, expand_env=False)
        overrides = req.overrides.model_dump(exclude_none=True)
        if overrides:
            try:
                cfg = apply_overrides(cfg, **overrides)
            except ValueError as exc:
                raise ConfigError(str(exc)) from exc
        if not settings.any_host and not host_allowed(cfg.host, settings.allowed_hosts):
            raise SafetyError(
                f"host {cfg.host!r} is not permitted by this server "
                f"(allowed: {', '.join(settings.allowed_hosts)})"
            )
        return cfg, check_safety(cfg, settings.max_rps_cap)

    scans = ScanManager(runs, lambda text: build_config(ConfigRequest(yaml=text))[0])
    app.state.scans = scans

    def summarize(cfg: Config, report: SafetyReport) -> ConfigSummary:
        return ConfigSummary(
            name=cfg.name,
            base_url=cfg.base_url,
            host=report.host,
            peak_rps=report.peak_rate,
            effective_cap=report.effective_cap,
            duration_s=cfg.model.total_duration,
            expected_requests=round(cfg.model.expected_events),
            processes=cfg.model.processes,
            workers=cfg.model.workers,
            concurrency_per_process=cfg.http.effective_concurrency,
            http2=cfg.http.http2,
            profile=[
                ProfileStepOut(duration_s=s.duration, rate=s.rate, end_rate=s.end_rate, name=s.name)
                for s in cfg.model.profile
            ],
            routes=[
                RouteOut(
                    name=r.name, method=r.method, path=r.path, weight=r.weight, tenant=r.tenant
                )
                for r in cfg.routes
            ],
        )

    public = APIRouter(prefix="/api/v1", tags=["meta"])
    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

    @public.get("/health")
    def health() -> Health:
        return Health(version=__version__, auth_required=settings.token is not None)

    @api.get("/examples", tags=["configs"])
    def list_examples() -> list[Example]:
        if not settings.examples_dir.is_dir():
            return []
        return [
            Example(name=p.stem, filename=p.name, yaml=p.read_text(encoding="utf-8"))
            for p in sorted(settings.examples_dir.glob("*.yaml"))
        ]

    @api.post("/configs/validate", tags=["configs"])
    def validate_config(req: ConfigRequest) -> ValidationResult:
        try:
            cfg, report = build_config(req)
        except (ConfigError, SafetyError) as exc:
            return ValidationResult(valid=False, errors=_error_lines(exc))
        return ValidationResult(
            valid=True, warnings=report.warnings, summary=summarize(cfg, report)
        )

    @api.get("/runs", tags=["runs"])
    def list_runs() -> list[RunListItem]:
        return runs.list_runs()

    @api.post("/runs", status_code=201, tags=["runs"])
    def start_run(req: ConfigRequest) -> RunDetail:
        try:
            cfg, _ = build_config(req)
        except (ConfigError, SafetyError) as exc:
            raise HTTPException(422, "\n".join(_error_lines(exc))) from exc
        try:
            run_id = runs.start(cfg)
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return runs.detail(run_id)

    @api.get("/runs/{run_id}", tags=["runs"])
    def get_run(run_id: str) -> RunDetail:
        try:
            return runs.detail(run_id)
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc

    @api.get("/runs/{run_id}/timeseries", tags=["runs"])
    def get_timeseries(run_id: str) -> Timeseries:
        try:
            return runs.timeseries(run_id)
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc

    @api.get("/runs/{run_id}/logs", tags=["runs"])
    def get_logs(
        run_id: str, tail: Annotated[int, Query(ge=1, le=5000)] = 200
    ) -> list[dict[str, object]]:
        try:
            return runs.logs(run_id, tail)
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc

    @api.post("/runs/{run_id}/stop", status_code=202, tags=["runs"])
    def stop_run(run_id: str, req: StopRequest | None = None) -> RunDetail:
        try:
            runs.stop(run_id, force=bool(req and req.force))
            return runs.detail(run_id)
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.post("/runs/{run_id}/analyze", tags=["runs"])
    def analyze(run_id: str, req: AnalyzeRequest) -> dict[str, object]:
        try:
            run_dir = runs.ensure_idle(run_id)
            return analyze_run(run_dir, req.model_dump())
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (AnalysisError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.get("/runs/{run_id}/artifacts/{name}", tags=["runs"])
    def get_artifact(run_id: str, name: str) -> FileResponse:
        try:
            path = runs.artifact(run_id, name)
        except RunNotFound as exc:
            raise HTTPException(404, "artifact not found") from exc
        return FileResponse(path, filename=f"{run_id}-{name}")

    @api.delete("/runs/{run_id}", status_code=204, tags=["runs"])
    def delete_run(run_id: str) -> Response:
        try:
            runs.delete(run_id)
        except RunNotFound as exc:
            raise HTTPException(404, "run not found") from exc
        except RunConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(status_code=204)

    @api.get("/scans", tags=["scans"])
    def list_scans() -> list[ScanSummary]:
        return scans.list_scans()

    @api.post("/scans", status_code=201, tags=["scans"])
    def start_scan(req: ScanRequest) -> ScanDetail:
        host = req.discovery.host
        # The server's browser fetches this URL, so it is held to the same target allowlist.
        if not settings.any_host and not host_allowed(host, settings.allowed_hosts):
            raise HTTPException(
                422,
                f"host {host!r} is not permitted by this server "
                f"(allowed: {', '.join(settings.allowed_hosts)})",
            )
        return scans.start(req)

    @api.get("/scans/{scan_id}", tags=["scans"])
    def get_scan(scan_id: str) -> ScanDetail:
        try:
            return scans.get(scan_id)
        except ScanNotFound as exc:
            raise HTTPException(404, "scan not found") from exc

    @api.post("/scans/{scan_id}/run", status_code=202, tags=["scans"])
    def run_scan(scan_id: str, req: ScanRunRequest) -> ScanDetail:
        try:
            return scans.run(scan_id, req.endpoint_ids, req.plan)
        except ScanNotFound as exc:
            raise HTTPException(404, "scan not found") from exc
        except ScanConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.post("/scans/{scan_id}/cancel", status_code=202, tags=["scans"])
    def cancel_scan(scan_id: str) -> ScanDetail:
        try:
            return scans.cancel(scan_id)
        except ScanNotFound as exc:
            raise HTTPException(404, "scan not found") from exc
        except ScanConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.delete("/scans/{scan_id}", status_code=204, tags=["scans"])
    def delete_scan(scan_id: str) -> Response:
        try:
            scans.delete(scan_id)
        except ScanNotFound as exc:
            raise HTTPException(404, "scan not found") from exc
        except ScanConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(status_code=204)

    @api.get("/demo-server", tags=["demo"])
    def demo_state() -> DemoServerState:
        return demo.state()

    @api.post("/demo-server", status_code=201, tags=["demo"])
    def demo_start(req: DemoServerRequest) -> DemoServerState:
        try:
            return demo.start(req)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except DemoConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.delete("/demo-server", status_code=204, tags=["demo"])
    def demo_stop() -> Response:
        demo.stop()
        return Response(status_code=204)

    @api.get("/demo-server/stats", tags=["demo"])
    async def demo_stats() -> dict[str, object]:
        try:
            return await demo.stats()
        except DemoConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"demo server unreachable: {exc}") from exc

    app.include_router(public)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if settings.static_dir is not None:
        _mount_spa(app, settings.static_dir.resolve())
    return app


def _mount_spa(app: FastAPI, root: Path) -> None:
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"static dir {root} has no index.html; build the frontend first")
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
