from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import func, select

from apitest.db import Environment
from apitest.schemas import EnvironmentIn, EnvironmentOut
from apitest.store import SessionDep, environment_out, get_or_404

router = APIRouter(prefix="/environments", tags=["environments"])


@router.get("", response_model=list[EnvironmentOut])
def list_environments(session: SessionDep) -> list[EnvironmentOut]:
    rows = session.scalars(select(Environment).order_by(func.lower(Environment.name))).all()
    return [environment_out(e) for e in rows]


@router.post("", status_code=201, response_model=EnvironmentOut)
def create_environment(body: EnvironmentIn, session: SessionDep) -> EnvironmentOut:
    env = Environment(name=body.name, variables=[v.model_dump() for v in body.variables])
    session.add(env)
    session.commit()
    session.refresh(env)
    return environment_out(env)


@router.get("/{environment_id}", response_model=EnvironmentOut)
def get_environment(environment_id: int, session: SessionDep) -> EnvironmentOut:
    return environment_out(get_or_404(session, Environment, environment_id, "environment"))


@router.put("/{environment_id}", response_model=EnvironmentOut)
def update_environment(environment_id: int, body: EnvironmentIn, session: SessionDep) -> EnvironmentOut:
    env = get_or_404(session, Environment, environment_id, "environment")
    env.name = body.name
    env.variables = [v.model_dump() for v in body.variables]
    session.commit()
    session.refresh(env)
    return environment_out(env)


@router.delete("/{environment_id}", status_code=204)
def delete_environment(environment_id: int, session: SessionDep) -> Response:
    session.delete(get_or_404(session, Environment, environment_id, "environment"))
    session.commit()
    return Response(status_code=204)
