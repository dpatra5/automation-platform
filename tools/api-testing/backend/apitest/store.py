"""Request-scoped dependencies and ORM <-> schema conversions."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Annotated, Any, TypeVar

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from apitest.config import Settings
from apitest.db import Collection, Environment, RequestItem, Run
from apitest.importers import ImportedCollection
from apitest.schemas import (
    CollectionExport,
    CollectionOut,
    CollectionSummary,
    EnvironmentOut,
    RequestItemIn,
    RequestItemOut,
    RequestSpec,
    RunDetail,
    RunStep,
    RunSummary,
    RunTotals,
    Variable,
)
from apitest.variables import scope

T = TypeVar("T")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.db.sessions() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_transport(request: Request) -> httpx.BaseTransport | None:
    transport: httpx.BaseTransport | None = request.app.state.transport
    return transport


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_or_404(session: Session, model: type[T], item_id: int, label: str) -> T:
    obj = session.get(model, item_id)
    if obj is None:
        raise HTTPException(404, f"{label} {item_id} not found")
    return obj


def variables_of(raw: list[dict[str, Any]]) -> list[Variable]:
    return [Variable.model_validate(v) for v in raw or []]


def request_out(item: RequestItem) -> RequestItemOut:
    spec = RequestSpec.model_validate(item.spec).model_dump()
    return RequestItemOut(
        id=item.id,
        collection_id=item.collection_id,
        position=item.position,
        updated_at=item.updated_at,
        name=item.name,
        **spec,
    )


def spec_of(body: RequestItemIn) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"name"})


def collection_summary(c: Collection, count: int) -> CollectionSummary:
    return CollectionSummary(
        id=c.id, name=c.name, description=c.description, request_count=count, updated_at=c.updated_at
    )


def collection_out(c: Collection) -> CollectionOut:
    return CollectionOut(
        id=c.id,
        name=c.name,
        description=c.description,
        variables=variables_of(c.variables),
        updated_at=c.updated_at,
        requests=[request_out(r) for r in c.requests],
    )


def collection_export(c: Collection) -> CollectionExport:
    # Secret values never leave the tool in an export file.
    variables = [v.model_copy(update={"value": ""}) if v.secret else v for v in variables_of(c.variables)]
    return CollectionExport(
        name=c.name,
        description=c.description,
        variables=variables,
        requests=[RequestItemIn(name=r.name, **RequestSpec.model_validate(r.spec).model_dump()) for r in c.requests],
    )


def environment_out(e: Environment) -> EnvironmentOut:
    return EnvironmentOut(id=e.id, name=e.name, variables=variables_of(e.variables), updated_at=e.updated_at)


def run_summary(run: Run) -> RunSummary:
    return RunSummary(
        id=run.id,
        collection_id=run.collection_id,
        collection_name=run.collection_name,
        environment_name=run.environment_name,
        status=run.status,  # type: ignore[arg-type]
        started_at=run.started_at,
        finished_at=run.finished_at,
        totals=RunTotals.model_validate(run.summary),
    )


def run_detail(run: Run) -> RunDetail:
    return RunDetail(
        **run_summary(run).model_dump(),
        steps=[RunStep.model_validate(s) for s in run.steps],
    )


def variable_scope(
    session: Session,
    collection_id: int | None,
    environment_id: int | None,
    runtime: Mapping[str, str],
) -> tuple[dict[str, str], list[str], str | None]:
    """Collection < environment < runtime. Returns ``(variables, secret values, env name)``."""
    layers: list[list[Variable]] = []
    env_name: str | None = None
    if collection_id is not None:
        layers.append(variables_of(get_or_404(session, Collection, collection_id, "collection").variables))
    if environment_id is not None:
        env = get_or_404(session, Environment, environment_id, "environment")
        env_name = env.name
        layers.append(variables_of(env.variables))
    variables = scope(*layers)
    variables.update(runtime)
    secrets = [v.value for layer in layers for v in layer if v.secret and v.enabled and v.value]
    return variables, secrets, env_name


def save_imported(session: Session, imported: ImportedCollection, name: str | None) -> Collection:
    collection = Collection(
        name=(name or "").strip()[:200] or imported.name,
        description=imported.description,
        variables=[v.model_dump() for v in imported.variables],
    )
    collection.requests = [
        RequestItem(name=r.name, position=i, spec=r.spec.model_dump(mode="json"))
        for i, r in enumerate(imported.requests)
    ]
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection
