from fastapi import APIRouter, Depends
from typing import List, Optional

from app.api.deps import get_run_batch_service
from app.schemas.run_batch import RunBatchCreate, RunBatchResponse
from app.services.run_batch_service import RunBatchService

router = APIRouter()


@router.get("", response_model=List[RunBatchResponse])
async def list_batches(
    project_id: Optional[str] = None,
    service: RunBatchService = Depends(get_run_batch_service),
):
    return await service.get_batches(project_id)


@router.post("", response_model=RunBatchResponse)
async def create_batch(
    payload: RunBatchCreate,
    service: RunBatchService = Depends(get_run_batch_service),
):
    """Queue the selected test cases to replay one after another."""
    return await service.create_batch(payload.test_case_ids, payload.name)


@router.get("/{id}", response_model=RunBatchResponse)
async def get_batch(id: str, service: RunBatchService = Depends(get_run_batch_service)):
    return await service.get_batch(id)
