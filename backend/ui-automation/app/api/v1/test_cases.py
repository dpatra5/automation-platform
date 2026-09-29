from fastapi import APIRouter, Depends
from typing import List
from pydantic import BaseModel
from app.schemas.test_case import (
    TestCaseResponse,
    TestCaseCreate,
    TestCaseUpdate,
    StepUpsert,
)
from app.schemas.run import RunResponse
from app.services.test_case_service import TestCaseService
from app.services.run_service import RunService
from app.api.deps import get_test_case_service, get_run_service

router = APIRouter()


class StepsPayload(BaseModel):
    steps: List[StepUpsert] = []


class ScriptPayload(BaseModel):
    script: str


class ScriptResponse(BaseModel):
    script: str


class RunPayload(BaseModel):
    silent_mode: bool = False


@router.get("/{id}", response_model=TestCaseResponse)
async def get_test_case(
    id: str, service: TestCaseService = Depends(get_test_case_service)
):
    return await service.get_test_case(id)


@router.patch("/{id}", response_model=TestCaseResponse)
async def update_test_case(
    id: str,
    tc_in: TestCaseUpdate,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.update_test_case(id, tc_in.model_dump(exclude_unset=True))


@router.put("/{id}", response_model=TestCaseResponse)
async def replace_test_case(
    id: str,
    tc_in: TestCaseUpdate,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.update_test_case(id, tc_in.model_dump(exclude_unset=True))


@router.put("/{id}/steps", response_model=TestCaseResponse)
async def update_steps(
    id: str,
    payload: StepsPayload,
    service: TestCaseService = Depends(get_test_case_service),
):
    """Replace all steps for a test case, exit criteria included."""
    return await service.update_test_case(
        id, {"steps": [s.model_dump() for s in payload.steps]}
    )


@router.get("/{id}/script", response_model=ScriptResponse)
async def get_script(
    id: str, service: TestCaseService = Depends(get_test_case_service)
):
    """The recorded steps written out as an editable Playwright-style script."""
    return {"script": await service.get_script(id)}


@router.put("/{id}/script", response_model=TestCaseResponse)
async def update_script(
    id: str,
    payload: ScriptPayload,
    service: TestCaseService = Depends(get_test_case_service),
):
    """Replace the steps with the ones the edited script describes."""
    return await service.update_from_script(id, payload.script)


@router.delete("/{id}")
async def delete_test_case(
    id: str, service: TestCaseService = Depends(get_test_case_service)
):
    await service.delete_test_case(id)
    return {"status": "deleted"}


@router.post("/{id}/run", response_model=RunResponse)
async def run_test_case(
    id: str,
    payload: RunPayload,
    service: RunService = Depends(get_run_service),
):
    return await service.trigger_run(id, silent_mode=payload.silent_mode)
