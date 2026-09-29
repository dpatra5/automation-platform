import json
from datetime import datetime, timedelta, timezone

import pytest

from app.execution.auth_manager import (
    EXPIRY_BUFFER, AuthExpiredError, AuthManager, earliest_expiry, is_usable,
)


def state(*expiries: float) -> str:
    return json.dumps({
        "cookies": [{"name": f"c{i}", "value": "x", "expires": e} for i, e in enumerate(expiries)],
        "origins": [],
    })


class Profile:
    def __init__(self, storage_state_json, expires_at=None):
        self.storage_state_json = storage_state_json
        self.expires_at = expires_at


def test_earliest_expiry_picks_the_soonest_cookie():
    soon = datetime(2030, 1, 1, tzinfo=timezone.utc)
    later = datetime(2031, 1, 1, tzinfo=timezone.utc)
    got = earliest_expiry(state(later.timestamp(), soon.timestamp()))
    assert got == soon


def test_session_cookies_have_no_clock_expiry():
    # -1 marks a session cookie: it dies with the browser, not on a clock.
    assert earliest_expiry(state(-1, -1)) is None
    assert earliest_expiry("not json") is None


def test_is_usable_applies_the_buffer():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert is_usable(now + EXPIRY_BUFFER + timedelta(minutes=1), now)
    # Inside the buffer the session would lapse mid-run, so it counts as gone.
    assert not is_usable(now + EXPIRY_BUFFER - timedelta(minutes=1), now)
    assert not is_usable(now - timedelta(seconds=1), now)
    assert is_usable(None, now), "session-cookie-only state has no clock to check"


def test_is_usable_treats_stored_naive_times_as_utc():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    naive_future = datetime(2026, 1, 1, 13, 0)  # what SQLite hands back
    assert is_usable(naive_future, now)


def test_manager_refuses_an_expired_session(tmp_path):
    profile = Profile(state(), datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(AuthExpiredError, match="expired"):
        AuthManager(profile).get_storage_state_path("run-1")


def test_manager_writes_and_removes_the_state_file():
    profile = Profile(state(), datetime.now(timezone.utc) + timedelta(days=1))
    manager = AuthManager(profile)

    path = manager.get_storage_state_path("run-2")
    assert path and json.loads(open(path, encoding="utf-8").read())["cookies"] == []

    # The file holds live session cookies, so it must not survive the run.
    manager.cleanup()
    assert not manager._temp_path.exists()


def test_no_profile_means_no_state_file():
    assert AuthManager(None).get_storage_state_path("run-3") is None
