"""FastAPI application factory."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from apitest import __version__, demo
from apitest.config import Settings
from apitest.db import Database
from apitest.routes import collections, environments, testing
from apitest.schemas import Health
from apitest.seed import seed_demo

_PUBLIC_PATHS = frozenset({"/api/v1/health"})


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "demo/")):
            raise HTTPException(404, "not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.db_url)
    if settings.seed_demo:
        seed_demo(db, settings)

    app = FastAPI(
        title="API Testing Tool",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.transport = transport
    app.state.demo = demo.DemoStore()

    @app.middleware("http")
    async def require_token(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if settings.token and path.startswith("/api/") and path not in _PUBLIC_PATHS:
            header = request.headers.get("authorization", "")
            supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), settings.token.encode()):
                return JSONResponse(
                    {"detail": "missing or invalid API token"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    api = APIRouter(prefix="/api/v1")

    @api.get("/health", response_model=Health, tags=["meta"])
    def health() -> Health:
        return Health(status="ok", version=__version__, auth_required=bool(settings.token))

    api.include_router(collections.router)
    api.include_router(environments.router)
    api.include_router(testing.router)
    app.include_router(api)
    app.include_router(demo.router)
    if settings.static_dir:
        _mount_spa(app, settings.static_dir)
    return app
