import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from app.models.models import StatusEnum
from app.schemas.run import RunResponse
from app.services.run_service import RunService
from app.api.deps import get_run_service
from app.config import settings

router = APIRouter()


class RunIdsPayload(BaseModel):
    ids: List[str] = []


@router.get("", response_model=List[RunResponse])
async def list_runs(
    test_case_id: Optional[str] = None,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    service: RunService = Depends(get_run_service),
):
    return await service.get_runs(test_case_id, status, project_id)


@router.post("/delete")
async def delete_runs(
    payload: RunIdsPayload, service: RunService = Depends(get_run_service)
):
    """Delete several runs at once. A body is used so the list cannot be truncated
    by a URL length limit."""
    return {"deleted": await service.delete_runs(payload.ids)}


@router.get("/{id}", response_model=RunResponse)
async def get_run(id: str, service: RunService = Depends(get_run_service)):
    return await service.get_run(id)


@router.delete("/{id}")
async def delete_run(id: str, service: RunService = Depends(get_run_service)):
    await service.delete_run(id)
    return {"status": "deleted"}


@router.get("/{id}/evidence/{evidence_id}")
async def get_run_evidence(
    id: str, evidence_id: str, service: RunService = Depends(get_run_service)
):
    run = await service.get_run(id)
    for ev in run.evidences:
        if ev.id == evidence_id:
            file_path = str(ev.file_path)
            # Handle both absolute and relative paths
            if not os.path.isabs(file_path):
                # If relative, resolve from cwd
                file_path = os.path.abspath(file_path)
            if os.path.exists(file_path):
                return FileResponse(file_path)
            raise HTTPException(
                status_code=404, detail=f"Evidence file not found on disk"
            )
    raise HTTPException(status_code=404, detail="Evidence not found")
