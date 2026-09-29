"""A small built-in API to try the tool against: login, CRUD products, echo, status, delay."""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"  # noqa: S105 - public demo credentials, documented in the UI
_MAX_TOKENS = 1000

router = APIRouter(prefix="/demo", tags=["demo target"])


def _initial_products() -> dict[int, dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    items = [("Mechanical keyboard", 49.99, True), ("Wireless mouse", 19.5, True), ("4K monitor", 189.0, False)]
    return {
        i: {"id": i, "name": name, "price": price, "in_stock": stock, "created_at": now}
        for i, (name, price, stock) in enumerate(items, start=1)
    }


@dataclass
class DemoStore:
    tokens: set[str] = field(default_factory=set)
    products: dict[int, dict[str, Any]] = field(default_factory=_initial_products)
    next_id: int = 4
    lock: threading.Lock = field(default_factory=threading.Lock)


def _store(request: Request) -> DemoStore:
    store: DemoStore = request.app.state.demo
    return store


def require_auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token or token not in _store(request).tokens:
        raise HTTPException(401, "missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"})


class LoginIn(BaseModel):
    username: str
    password: str


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    in_stock: bool = True


@router.post("/auth/login")
def login(body: LoginIn, request: Request) -> dict[str, Any]:
    valid = hmac.compare_digest(body.username.encode(), DEMO_USERNAME.encode()) & hmac.compare_digest(
        body.password.encode(), DEMO_PASSWORD.encode()
    )
    if not valid:
        raise HTTPException(401, "invalid username or password")
    store = _store(request)
    token = secrets.token_urlsafe(24)
    with store.lock:
        if len(store.tokens) >= _MAX_TOKENS:
            store.tokens.clear()
        store.tokens.add(token)
    return {"token": token, "token_type": "bearer", "expires_in": 3600}


@router.get("/products", dependencies=[Depends(require_auth)])
def list_products(request: Request, q: str | None = None, in_stock: bool | None = None) -> dict[str, Any]:
    items = sorted(_store(request).products.values(), key=lambda p: p["id"])
    if q:
        items = [p for p in items if q.lower() in p["name"].lower()]
    if in_stock is not None:
        items = [p for p in items if p["in_stock"] is in_stock]
    return {"items": items, "count": len(items)}


@router.post("/products", status_code=201, dependencies=[Depends(require_auth)])
def create_product(body: ProductIn, request: Request) -> dict[str, Any]:
    store = _store(request)
    with store.lock:
        product = {"id": store.next_id, **body.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
        store.products[store.next_id] = product
        store.next_id += 1
    return product


def _product(request: Request, product_id: int) -> dict[str, Any]:
    product = _store(request).products.get(product_id)
    if product is None:
        raise HTTPException(404, "product not found")
    return product


@router.get("/products/{product_id}", dependencies=[Depends(require_auth)])
def get_product(product_id: int, request: Request) -> dict[str, Any]:
    return _product(request, product_id)


@router.put("/products/{product_id}", dependencies=[Depends(require_auth)])
def update_product(product_id: int, body: ProductIn, request: Request) -> dict[str, Any]:
    product = _product(request, product_id)
    product.update(body.model_dump())
    return product


@router.delete("/products/{product_id}", status_code=204, dependencies=[Depends(require_auth)])
def delete_product(product_id: int, request: Request) -> Response:
    _product(request, product_id)
    with _store(request).lock:
        _store(request).products.pop(product_id, None)
    return Response(status_code=204)


@router.api_route("/echo", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def echo(request: Request) -> dict[str, Any]:
    raw = (await request.body())[:10_000].decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw) if raw.strip() else None
    except ValueError:
        parsed = None
    headers = {
        k: ("••••••" if k in ("authorization", "cookie") else v) for k, v in request.headers.items()
    }
    return {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params.multi_items()),
        "headers": headers,
        "body": raw,
        "json": parsed,
    }


@router.get("/status/{code}")
def status(code: int) -> Response:
    if not 200 <= code <= 599:
        raise HTTPException(400, "code must be between 200 and 599")
    if code in (204, 304):
        return Response(status_code=code)
    return JSONResponse({"status": code}, status_code=code)


@router.get("/delay/{ms}")
async def delay(ms: int) -> dict[str, int]:
    ms = max(0, min(ms, 10_000))
    await asyncio.sleep(ms / 1000)
    return {"delayed_ms": ms}
