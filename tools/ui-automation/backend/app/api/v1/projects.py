from fastapi import APIRouter, Depends
from typing import List, Optional
from app.schemas.project import ProjectResponse, ProjectCreate, ProjectUpdate
from app.schemas.auth_profile import AuthProfileCreate, AuthProfileResponse
from app.schemas.test_case import TestCaseResponse, TestCaseCreate
from app.services.project_service import ProjectService
from app.services.test_case_service import TestCaseService
from app.api.deps import get_project_service, get_test_case_service

router = APIRouter()


@router.get("", response_model=List[ProjectResponse])
async def list_projects(service: ProjectService = Depends(get_project_service)):
    return await service.get_projects()


@router.post("", response_model=ProjectResponse)
async def create_project(
    project_in: ProjectCreate, service: ProjectService = Depends(get_project_service)
):
    return await service.create_project(project_in)


@router.get("/{id}", response_model=ProjectResponse)
async def get_project(id: str, service: ProjectService = Depends(get_project_service)):
    return await service.get_project(id)


@router.patch("/{id}", response_model=ProjectResponse)
async def update_project(
    id: str,
    project_in: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
):
    """Partial update. A new Jira key is verified against Jira before it sticks."""
    return await service.update_project(id, project_in.model_dump(exclude_unset=True))


@router.delete("/{id}")
async def delete_project(
    id: str, service: ProjectService = Depends(get_project_service)
):
    """Delete a project with its test cases, runs and stored evidence."""
    await service.delete_project(id)
    return {"status": "deleted"}


@router.post("/{id}/auth-profile", response_model=AuthProfileResponse)
async def set_auth_profile(
    id: str,
    auth_in: AuthProfileCreate,
    service: ProjectService = Depends(get_project_service),
):
    return await service.set_auth_profile(id, auth_in)


@router.get("/{id}/auth-profile", response_model=Optional[AuthProfileResponse])
async def get_auth_profile(
    id: str, service: ProjectService = Depends(get_project_service)
):
    """Session status for the project, or null when nothing is stored."""
    return await service.get_auth_profile(id)


@router.delete("/{id}/auth-profile")
async def clear_auth_profile(
    id: str, service: ProjectService = Depends(get_project_service)
):
    await service.clear_auth_profile(id)
    return {"status": "cleared"}


@router.get("/{id}/test-cases", response_model=List[TestCaseResponse])
async def get_project_test_cases(
    id: str, service: TestCaseService = Depends(get_test_case_service)
):
    return await service.get_by_project(id)


@router.post("/{id}/test-cases", response_model=TestCaseResponse)
async def create_test_case(
    id: str,
    tc_in: TestCaseCreate,
    service: TestCaseService = Depends(get_test_case_service),
):
    return await service.create_test_case(id, tc_in)
