from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.execution import assertions
from app.integrations.jira_client import (
    JiraClient,
    get_jira_client,
    require_jira_client,
)
from app.integrations.confluence_client import ConfluenceClient
from app.integrations.bitbucket_client import BitbucketClient
from app.integrations.noop_client import NoopIssueTracker

router = APIRouter()


class TestConnectionPayload(BaseModel):
    type: str
    url: str
    token: str
    email: Optional[str] = None


@router.post("/test-connection")
async def test_connection(payload: TestConnectionPayload):
    if payload.type == "jira":
        client = JiraClient(
            host=payload.url,
            token=payload.token,
            email=payload.email or "",
            verify_ssl=settings.jira_verify_ssl,
            timeout=settings.jira_timeout_seconds,
        )
    elif payload.type == "confluence":
        client = ConfluenceClient(host=payload.url, token=payload.token)
    elif payload.type == "bitbucket":
        client = BitbucketClient(host=payload.url, token=payload.token)
    else:
        client = NoopIssueTracker()

    success = await client.test_connection()
    return {
        "status": "success" if success else "failure",
        "message": "Connection test completed",
    }


@router.get("/jira/status")
async def jira_status():
    """Whether the backend has Jira credentials, so the GUI can say so."""
    client = get_jira_client()
    return {
        "configured": client is not None,
        "url": settings.jira_url,
        "required_issue_type": settings.jira_test_execution_type,
        "attaches_evidence": settings.jira_attach_evidence,
    }


@router.get("/jira/whoami")
async def jira_whoami():
    """Who the configured credentials authenticate as.

    The first thing to check when Jira misbehaves: it proves the token reaches
    Jira and says which authentication scheme worked.
    """
    return await require_jira_client().whoami()


@router.get("/jira/validate")
async def validate_jira_key(key: str):
    """Confirm a key is a Test Execution issue this token can reach."""
    issue = await require_jira_client().resolve_test_execution(key)
    return {"valid": True, "issue": issue}


@router.get("/assertions")
async def assertion_catalogue():
    """Every check the runner understands, for the exit-criteria pickers."""
    return {
        "assertions": assertions.catalogue(),
        "default": assertions.DEFAULT_ASSERTION,
    }
