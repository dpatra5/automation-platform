from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import defer

from apitest.db import Collection, Run, utcnow
from apitest.executor import execute
from apitest.importers import import_content
from apitest.reports import html_report, junit
from apitest.runner import PlanItem, parse_data, run_plan
from apitest.schemas import (
    ExecuteIn,
    ExecutionResult,
    ImportIn,
    ImportOut,
    RequestSpec,
    RunDetail,
    RunIn,
    RunSummary,
)
from apitest.store import (
    SessionDep,
    SettingsDep,
    collection_summary,
    get_or_404,
    get_transport,
    run_detail,
    run_summary,
    save_imported,
    variable_scope,
)

router = APIRouter()


@router.post("/execute", response_model=ExecutionResult, tags=["execute"])
def execute_request(body: ExecuteIn, request: Request, session: SessionDep, settings: SettingsDep) -> ExecutionResult:
    variables, secrets, _ = variable_scope(session, body.collection_id, body.environment_id, body.variables)
    session.close()  # don't hold a DB connection while waiting on the network
    return execute(body.request, variables, settings, secrets=secrets, transport=get_transport(request))


@router.post("/runs", status_code=201, response_model=RunDetail, tags=["runs"])
def create_run(body: RunIn, request: Request, session: SessionDep, settings: SettingsDep) -> RunDetail:
    collection = get_or_404(session, Collection, body.collection_id, "collection")
    items = list(collection.requests)
    if body.request_ids is not None:
        by_id = {r.id: r for r in items}
        unknown = [i for i in body.request_ids if i not in by_id]
        if unknown:
            raise HTTPException(422, f"requests not in this collection: {unknown}")
        items = [by_id[i] for i in body.request_ids]
    if not items:
        raise HTTPException(422, "there are no requests to run")
    try:
        rows = parse_data(body.data, settings.max_iterations)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    variables, secrets, env_name = variable_scope(session, collection.id, body.environment_id, {})
    plan = [PlanItem(r.id, r.name, RequestSpec.model_validate(r.spec)) for r in items]
    collection_id, collection_name = collection.id, collection.name
    session.close()

    started = utcnow()
    steps, totals, status = run_plan(
        plan,
        variables,
        settings,
        secrets=secrets,
        iterations=body.iterations,
        data_rows=rows,
        stop_on_failure=body.stop_on_failure,
        delay_ms=body.delay_ms,
        transport=get_transport(request),
    )
    run = Run(
        collection_id=collection_id,
        collection_name=collection_name,
        environment_name=env_name,
        status=status,
        started_at=started,
        finished_at=utcnow(),
        summary=totals.model_dump(),
        steps=[s.model_dump(mode="json") for s in steps],
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run_detail(run)


@router.get("/runs", response_model=list[RunSummary], tags=["runs"])
def list_runs(
    session: SessionDep,
    collection_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[RunSummary]:
    query = select(Run).options(defer(Run.steps)).order_by(Run.id.desc()).limit(limit)
    if collection_id is not None:
        query = query.where(Run.collection_id == collection_id)
    return [run_summary(r) for r in session.scalars(query).all()]


@router.get("/runs/{run_id}", response_model=RunDetail, tags=["runs"])
def get_run(run_id: int, session: SessionDep) -> RunDetail:
    return run_detail(get_or_404(session, Run, run_id, "run"))


@router.delete("/runs/{run_id}", status_code=204, tags=["runs"])
def delete_run(run_id: int, session: SessionDep) -> Response:
    session.delete(get_or_404(session, Run, run_id, "run"))
    session.commit()
    return Response(status_code=204)


@router.get("/runs/{run_id}/report", tags=["runs"])
def run_report(
    run_id: int, session: SessionDep, format: Literal["json", "junit", "html"] = "json"
) -> Response:
    detail = run_detail(get_or_404(session, Run, run_id, "run"))
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", detail.collection_name).strip("-") or "run"
    if format == "junit":
        content, media, ext = junit(detail), "application/xml", "xml"
    elif format == "html":
        content, media, ext = html_report(detail), "text/html; charset=utf-8", "html"
    else:
        content, media, ext = detail.model_dump_json(indent=2), "application/json", "json"
    return Response(
        content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="run-{run_id}-{slug}.{ext}"'},
    )


@router.post("/import", status_code=201, response_model=ImportOut, tags=["import"])
def import_collection(body: ImportIn, session: SessionDep) -> ImportOut:
    try:
        imported = import_content(body.content, body.format)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    collection = save_imported(session, imported, body.name)
    return ImportOut(
        collection=collection_summary(collection, len(imported.requests)),
        format=imported.format,
        request_count=len(imported.requests),
        warnings=imported.warnings,
    )
