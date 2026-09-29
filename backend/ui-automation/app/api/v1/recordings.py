from fastapi import APIRouter, Depends
from app.api.deps import get_recording_service
from app.services.recording_service import RecordingService
from app.schemas.recording import RecordingPayload, SessionTokenResponse
from app.schemas.test_case import TestCaseResponse

router = APIRouter()

@router.post("", response_model=TestCaseResponse)
async def create_recording(
    payload: RecordingPayload,
    service: RecordingService = Depends(get_recording_service)
):
    return await service.create_from_recording(payload)

@router.get("/session-token", response_model=SessionTokenResponse)
async def get_session_token(
    service: RecordingService = Depends(get_recording_service)
):
    token = service.generate_session_token()
    return SessionTokenResponse(token=token)
