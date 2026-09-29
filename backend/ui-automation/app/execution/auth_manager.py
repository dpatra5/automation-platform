"""Authentication state for replayed runs.

The recorder captures the browser's cookies and localStorage at the end of a
session and stores them as a Playwright `storage_state`. Replaying with that
state means a regression run starts already signed in, which is what makes SSO
flows (Okta, Entra, Google - anything that ends in a session cookie) replayable
without ever recording a password.

Sessions expire, so the run must decide up front whether the state is still
usable rather than failing halfway through with a confusing "element not
found" on a login page.
"""
import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Treat a session as expired this far ahead of its real expiry, so a run that
# takes a few minutes does not lose its session midway.
EXPIRY_BUFFER = timedelta(minutes=5)


class AuthExpiredError(Exception):
    """The stored session is gone or too close to expiry to start a run."""


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def earliest_expiry(storage_state_json: str) -> Optional[datetime]:
    """When the captured session first goes stale.

    Uses the earliest expiring cookie. Session cookies (expires <= 0) have no
    wall-clock expiry and are ignored: they die with the browser, not with time.
    Returns None when nothing in the state expires on a clock.
    """
    try:
        cookies: Iterable[dict] = json.loads(storage_state_json).get("cookies", [])
    except (ValueError, AttributeError):
        return None

    stamps = [
        datetime.fromtimestamp(c["expires"], tz=timezone.utc)
        for c in cookies
        if isinstance(c.get("expires"), (int, float)) and c["expires"] > 0
    ]
    return min(stamps) if stamps else None


def is_usable(expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """True when the session still has more than the buffer left on it."""
    expires_at = _aware(expires_at)
    if expires_at is None:
        return True  # session-cookie only: no clock to check, let the run try
    return expires_at - EXPIRY_BUFFER > (now or datetime.now(timezone.utc))


class AuthManager:
    """Materialises an auth profile into a Playwright storage_state file."""

    def __init__(self, auth_profile):
        self.auth_profile = auth_profile
        self._temp_path: Path | None = None

    def get_storage_state_path(self, run_id: str) -> str | None:
        """Write the auth profile to a temp file and return its path.

        Raises AuthExpiredError instead of silently replaying a dead session.
        """
        if not self.auth_profile:
            return None

        expires_at = _aware(self.auth_profile.expires_at)
        if not is_usable(expires_at):
            raise AuthExpiredError(
                f"Saved sign-in for this project expired at "
                f"{expires_at:%Y-%m-%d %H:%M UTC}. Record a new session to refresh it."
            )

        self._temp_path = Path(tempfile.gettempdir()) / f"rewind_auth_{run_id}.json"
        self._temp_path.write_text(self.auth_profile.storage_state_json, encoding="utf-8")
        if expires_at:
            logger.info(f"Run {run_id} using saved session, expires {expires_at.isoformat()}")
        return str(self._temp_path)

    def cleanup(self) -> None:
        """Remove the temporary auth file - it holds live session cookies."""
        if self._temp_path and self._temp_path.exists():
            try:
                self._temp_path.unlink()
            except OSError as e:
                logger.warning(f"Could not remove auth state file: {e}")
