from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from apitest.db import Collection, RequestItem
from apitest.schemas import CollectionIn, CollectionOut, CollectionSummary, ReorderIn, RequestItemIn, RequestItemOut
from apitest.store import (
    SessionDep,
    collection_export,
    collection_out,
    collection_summary,
    get_or_404,
    request_out,
    spec_of,
)

router = APIRouter(tags=["collections"])


@router.get("/collections", response_model=list[CollectionSummary])
def list_collections(session: SessionDep) -> list[CollectionSummary]:
    counts: dict[int, int] = {
        cid: n
        for cid, n in session.execute(
            select(RequestItem.collection_id, func.count()).group_by(RequestItem.collection_id)
        )
    }
    rows = session.scalars(select(Collection).order_by(func.lower(Collection.name))).all()
    return [collection_summary(c, counts.get(c.id, 0)) for c in rows]


@router.post("/collections", status_code=201, response_model=CollectionOut)
def create_collection(body: CollectionIn, session: SessionDep) -> CollectionOut:
    collection = Collection(
        name=body.name, description=body.description, variables=[v.model_dump() for v in body.variables]
    )
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return collection_out(collection)


@router.get("/collections/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: int, session: SessionDep) -> CollectionOut:
    return collection_out(get_or_404(session, Collection, collection_id, "collection"))


@router.put("/collections/{collection_id}", response_model=CollectionOut)
def update_collection(collection_id: int, body: CollectionIn, session: SessionDep) -> CollectionOut:
    collection = get_or_404(session, Collection, collection_id, "collection")
    collection.name = body.name
    collection.description = body.description
    collection.variables = [v.model_dump() for v in body.variables]
    session.commit()
    session.refresh(collection)
    return collection_out(collection)


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: int, session: SessionDep) -> Response:
    session.delete(get_or_404(session, Collection, collection_id, "collection"))
    session.commit()
    return Response(status_code=204)


@router.get("/collections/{collection_id}/export")
def export_collection(collection_id: int, session: SessionDep) -> JSONResponse:
    collection = get_or_404(session, Collection, collection_id, "collection")
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", collection.name).strip("-") or "collection"
    return JSONResponse(
        collection_export(collection).model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}.apitest.json"'},
    )


@router.post("/collections/{collection_id}/requests", status_code=201, response_model=RequestItemOut)
def create_request(collection_id: int, body: RequestItemIn, session: SessionDep) -> RequestItemOut:
    get_or_404(session, Collection, collection_id, "collection")
    last = session.scalar(
        select(func.max(RequestItem.position)).where(RequestItem.collection_id == collection_id)
    )
    item = RequestItem(
        collection_id=collection_id, name=body.name, position=(last or 0) + 1, spec=spec_of(body)
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return request_out(item)


@router.put("/collections/{collection_id}/order", response_model=CollectionOut)
def reorder_requests(collection_id: int, body: ReorderIn, session: SessionDep) -> CollectionOut:
    collection = get_or_404(session, Collection, collection_id, "collection")
    by_id = {r.id: r for r in collection.requests}
    if sorted(body.request_ids) != sorted(by_id):
        raise HTTPException(422, "request_ids must list every request in the collection exactly once")
    for position, request_id in enumerate(body.request_ids):
        by_id[request_id].position = position
    session.commit()
    session.expire(collection)
    return collection_out(collection)


@router.get("/requests/{request_id}", response_model=RequestItemOut)
def get_request(request_id: int, session: SessionDep) -> RequestItemOut:
    return request_out(get_or_404(session, RequestItem, request_id, "request"))


@router.put("/requests/{request_id}", response_model=RequestItemOut)
def update_request(request_id: int, body: RequestItemIn, session: SessionDep) -> RequestItemOut:
    item = get_or_404(session, RequestItem, request_id, "request")
    item.name = body.name
    item.spec = spec_of(body)
    session.commit()
    session.refresh(item)
    return request_out(item)


@router.delete("/requests/{request_id}", status_code=204)
def delete_request(request_id: int, session: SessionDep) -> Response:
    session.delete(get_or_404(session, RequestItem, request_id, "request"))
    session.commit()
    return Response(status_code=204)


@router.post("/requests/{request_id}/duplicate", status_code=201, response_model=RequestItemOut)
def duplicate_request(request_id: int, session: SessionDep) -> RequestItemOut:
    source = get_or_404(session, RequestItem, request_id, "request")
    siblings = session.scalars(
        select(RequestItem)
        .where(RequestItem.collection_id == source.collection_id, RequestItem.position > source.position)
    ).all()
    for sibling in siblings:
        sibling.position += 1
    copy = RequestItem(
        collection_id=source.collection_id,
        name=f"{source.name} (copy)"[:200],
        position=source.position + 1,
        spec=dict(source.spec),
    )
    session.add(copy)
    session.commit()
    session.refresh(copy)
    return request_out(copy)
