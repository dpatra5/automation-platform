"""Jira, over the REST API.

Two things depend on this: a project's Jira key is verified before it is
stored, and finished runs comment on that key with their evidence attached.
Neither is allowed to take the app down, so every failure here surfaces as a
`JiraError` carrying a sentence a tester can act on.

Authentication differs by deployment, and getting it wrong does not produce a
clean 401:

* Data Center / Server - Personal Access Token as a bearer token. Sending basic
  auth instead makes Jira answer with an HTML 500 and an error reference.
* Cloud                - account email plus API token as basic auth. A bearer
  token is rejected outright.

The scheme is therefore picked by host, retried with the other one if the first
is refused, and remembered once something works.
"""

import asyncio
import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.exceptions import RewindError
from app.integrations.base import IssueTracker

logger = logging.getLogger(__name__)

# PROJ-123: an uppercase project prefix and an issue number.
ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,20}-\d{1,10}$")

BEARER = "bearer"
BASIC = "basic"
# Jira DC answers the wrong auth scheme with a 500 rather than a 401, so a
# server error is worth one retry with the other scheme before giving up.
RETRY_AUTH_STATUSES = frozenset({401, 403, 500})

# Whatever last worked per host, so the fallback costs one request in total
# rather than one per call.
_WORKING_SCHEME: dict[str, str] = {}

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _is_cloud(host: str) -> bool:
    return urlparse(host).hostname is not None and urlparse(host).hostname.endswith(
        ".atlassian.net"
    )


def _readable(response: httpx.Response) -> str:
    """A one-line summary of an error body, HTML error pages included."""
    body = (response.text or "").strip()
    if not body:
        return "no details"
    try:
        payload = response.json()
        messages = payload.get("errorMessages") or []
        errors = list((payload.get("errors") or {}).values())
        joined = "; ".join(str(m) for m in [*messages, *errors] if m)
        if joined:
            return joined[:300]
    except ValueError:
        pass
    return _WHITESPACE.sub(" ", _TAG.sub(" ", body)).strip()[:200] or "no details"


class JiraError(RewindError):
    """Jira refused, or could not be reached. The message is user-facing."""


class JiraNotConfiguredError(JiraError):
    """No Jira URL or token in the environment."""


def normalise_issue_key(raw: str | None) -> str | None:
    """Trim and upper-case a key, or None when nothing was given."""
    key = (raw or "").strip().upper()
    return key or None


def validate_issue_key_format(key: str) -> None:
    if not ISSUE_KEY_PATTERN.match(key):
        raise JiraError(
            f"'{key}' is not a Jira issue key. Keys look like JGQE-23122 - "
            "a project prefix, a hyphen, then the issue number."
        )


class JiraClient(IssueTracker):
    """Talks to one Jira instance. Cheap to construct, one HTTP client per call."""

    def __init__(
        self,
        host: str,
        token: str,
        email: str = "",
        verify_ssl: bool = True,
        timeout: int = 20,
        test_execution_type: str = "Test Execution",
        auth_mode: str = "auto",
    ):
        if not host or not token:
            raise JiraNotConfiguredError(
                "Jira is not configured. Set JIRA_URL and JIRA_TOKEN in backend/.env, "
                "then restart the backend."
            )
        self.host = host.rstrip("/")
        self.token = token
        self.email = email
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.test_execution_type = test_execution_type
        self.auth_mode = auth_mode

    # ------------------------------------------------------------- plumbing

    def _auth_header(self, scheme: str) -> dict[str, str]:
        if scheme == BASIC:
            raw = f"{self.email}:{self.token}".encode()
            return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}
        return {"Authorization": f"Bearer {self.token}"}

    def _preferred_scheme(self) -> str:
        """Which scheme to try first for this host.

        Jira Cloud only accepts an email plus API token as basic auth. Data
        Center and Server want a Personal Access Token as a bearer token, and
        answer basic auth with an HTML 500 rather than a 401 - which is exactly
        the failure this picks the right scheme to avoid.
        """
        cached = _WORKING_SCHEME.get(self.host)
        if cached:
            return cached
        configured = (self.auth_mode or "auto").strip().lower()
        if configured in (BASIC, BEARER):
            return configured
        if _is_cloud(self.host) and self.email:
            return BASIC
        return BEARER

    def _fallback_scheme(self, used: str) -> str | None:
        """The other scheme, when the credentials allow trying it."""
        if (self.auth_mode or "auto").strip().lower() != "auto":
            return None
        if used == BEARER:
            return BASIC if self.email else None
        return BEARER

    def _client(self, scheme: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self.host}/rest/api/2",
            headers={"Accept": "application/json", **self._auth_header(scheme)},
            timeout=self.timeout,
            verify=self.verify_ssl,
            follow_redirects=True,
        )

    def _explain(
        self, response: httpx.Response, subject: str, scheme: str
    ) -> JiraError:
        """Turn a status code into something worth reading."""
        if response.status_code in (401, 403):
            return JiraError(
                f"Jira rejected the credentials while {subject}. Check JIRA_TOKEN, and "
                "that the account it belongs to may see this project."
            )
        if response.status_code == 404:
            return JiraError(f"Jira has no such issue ({subject}).")
        if response.status_code >= 500:
            return JiraError(
                f"Jira answered {response.status_code} while {subject} "
                f"({_readable(response)}). Rewind sent {scheme} authentication; if this is "
                "Jira Cloud set JIRA_EMAIL, and if it is Data Center or Server make sure "
                "JIRA_TOKEN is a Personal Access Token and leave JIRA_EMAIL empty."
            )
        return JiraError(
            f"Jira returned {response.status_code} while {subject}: {_readable(response)}."
        )

    async def _send(self, scheme: str, method: str, url: str, subject: str, **kwargs):
        try:
            async with self._client(scheme) as client:
                return await client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            raise JiraError(
                f"Jira did not answer within {self.timeout}s while {subject}."
            ) from e
        except httpx.HTTPError as e:
            raise JiraError(
                f"Could not reach Jira at {self.host} while {subject}: {e}"
            ) from e

    async def _request(
        self, method: str, url: str, subject: str, **kwargs
    ) -> httpx.Response:
        """Send a request, retrying once with the other auth scheme if refused."""
        scheme = self._preferred_scheme()
        response = await self._send(scheme, method, url, subject, **kwargs)

        if response.status_code in RETRY_AUTH_STATUSES:
            other = self._fallback_scheme(scheme)
            if other:
                logger.info(
                    "Jira refused %s auth (%s); retrying with %s",
                    scheme,
                    response.status_code,
                    other,
                )
                retried = await self._send(other, method, url, subject, **kwargs)
                if retried.status_code < 400:
                    # Remember what worked: every call builds its own client.
                    _WORKING_SCHEME[self.host] = other
                    return retried
                response = retried
                scheme = other

        if response.status_code >= 400:
            raise self._explain(response, subject, scheme)

        _WORKING_SCHEME[self.host] = scheme
        return response

    # ---------------------------------------------------------------- reads

    async def whoami(self) -> dict[str, str]:
        """Who the configured credentials authenticate as, for diagnostics."""
        response = await self._request(
            "GET", "/myself", subject="checking the connection"
        )
        me = response.json()
        return {
            "account": me.get("name") or me.get("accountId") or "",
            "display_name": me.get("displayName") or "",
            "email": me.get("emailAddress") or "",
            "auth": _WORKING_SCHEME.get(self.host, self._preferred_scheme()),
            "url": self.host,
        }

    async def test_connection(self) -> bool:
        """True when the credentials identify somebody."""
        me = await self.whoami()
        return bool(me["account"] or me["display_name"])

    async def get_issue(self, issue_key: str) -> Optional[dict[str, Any]]:
        """The issue's summary, type and status, or None when it does not exist."""
        key = normalise_issue_key(issue_key)
        if not key:
            return None
        try:
            response = await self._request(
                "GET",
                f"/issue/{key}",
                subject=f"looking up {key}",
                params={"fields": "summary,issuetype,status,project"},
            )
        except JiraError as e:
            if "no such issue" in str(e):
                return None
            raise
        return response.json()

    async def resolve_test_execution(self, issue_key: str) -> dict[str, str]:
        """Confirm the key exists and is a Test Execution; describe it if so."""
        key = normalise_issue_key(issue_key) or ""
        validate_issue_key_format(key)

        issue = await self.get_issue(key)
        if issue is None:
            raise JiraError(
                f"{key} does not exist in Jira, or the configured token cannot see it."
            )

        fields = issue.get("fields") or {}
        issue_type = ((fields.get("issuetype") or {}).get("name") or "").strip()
        if issue_type.casefold() != self.test_execution_type.casefold():
            raise JiraError(
                f"{key} is a '{issue_type or 'unknown'}' issue. Rewind only links to "
                f"'{self.test_execution_type}' issues, so runs are reported where the "
                "test team expects them."
            )

        return {
            "key": issue.get("key", key),
            "summary": (fields.get("summary") or "").strip(),
            "issue_type": issue_type,
            "status": ((fields.get("status") or {}).get("name") or "").strip(),
            "url": self.browse_url(issue.get("key", key)),
        }

    # --------------------------------------------------------------- writes

    async def create_issue(self, title: str, description: str) -> str:
        response = await self._request(
            "POST",
            "/issue",
            subject="creating an issue",
            json={"fields": {"summary": title, "description": description}},
        )
        return response.json().get("key", "")

    async def add_comment(self, issue_key: str, body: str) -> str:
        key = normalise_issue_key(issue_key) or ""
        validate_issue_key_format(key)
        response = await self._request(
            "POST",
            f"/issue/{key}/comment",
            subject=f"commenting on {key}",
            json={"body": body},
        )
        return str(response.json().get("id", ""))

    async def attach_files(self, issue_key: str, paths: Sequence[str]) -> list[str]:
        """Attach whatever exists and is small enough; skip the rest quietly."""
        key = normalise_issue_key(issue_key) or ""
        validate_issue_key_format(key)

        limit = max(1, settings.jira_max_attachment_mb) * 1024 * 1024
        payload: list[tuple[str, tuple[str, bytes, str]]] = []
        for raw in paths:
            path = Path(raw)
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
                if size == 0 or size > limit:
                    logger.info(
                        "Skipping Jira attachment %s (%d bytes)", path.name, size
                    )
                    continue
                content = await asyncio.to_thread(path.read_bytes)
            except OSError as e:
                logger.warning("Could not read %s for Jira: %s", path, e)
                continue
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            payload.append(("file", (path.name, content, mime)))

        if not payload:
            return []

        scheme = self._preferred_scheme()
        try:
            async with httpx.AsyncClient(
                base_url=f"{self.host}/rest/api/2",
                # Jira refuses multipart uploads without this header, by design.
                headers={"X-Atlassian-Token": "no-check", **self._auth_header(scheme)},
                timeout=max(self.timeout, 60),
                verify=self.verify_ssl,
                follow_redirects=True,
            ) as client:
                response = await client.post(f"/issue/{key}/attachments", files=payload)
        except httpx.HTTPError as e:
            raise JiraError(f"Could not upload evidence to {key}: {e}") from e

        if response.status_code >= 400:
            raise self._explain(response, f"attaching evidence to {key}", scheme)

        return [item.get("filename", "") for item in response.json()]

    def browse_url(self, issue_key: str) -> str:
        return f"{self.host}/browse/{normalise_issue_key(issue_key)}"


def get_jira_client() -> Optional[JiraClient]:
    """A client built from the environment, or None when Jira is not set up."""
    if not settings.jira_url or not settings.jira_token:
        return None
    return JiraClient(
        host=settings.jira_url,
        token=settings.jira_token,
        email=settings.jira_email,
        verify_ssl=settings.jira_verify_ssl,
        timeout=settings.jira_timeout_seconds,
        test_execution_type=settings.jira_test_execution_type,
        auth_mode=settings.jira_auth,
    )


def require_jira_client() -> JiraClient:
    client = get_jira_client()
    if client is None:
        raise JiraNotConfiguredError(
            "Jira is not configured. Set JIRA_URL and JIRA_TOKEN in backend/.env "
            "(and JIRA_EMAIL for Jira Cloud), then restart the backend."
        )
    return client
