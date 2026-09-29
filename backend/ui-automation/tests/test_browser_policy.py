"""Choosing a browser that will still be signed in when the run starts.

A managed Chrome carrying `BlockThirdPartyCookies` throws away the cross-site
cookies an SSO session is made of, and no switch inside the browser overrides a
policy. The runner has to notice and move to a browser the policy misses.
"""

import json
import sys
from types import SimpleNamespace

import pytest

from app.execution import browser_policy, runner as runner_module
from app.execution.runner import PlaywrightRunner


class Recorder:
    """Just enough of PlaywrightRunner for the channel decision."""

    def __init__(self):
        self.console_lines = []

    _channel = PlaywrightRunner._channel


@pytest.fixture
def settings(monkeypatch):
    values = SimpleNamespace(
        browser_channel="chrome",
        require_third_party_cookies=True,
    )
    monkeypatch.setattr(runner_module, "settings", values)
    return values


def test_managed_chrome_is_swapped_for_bundled_chromium(settings, monkeypatch):
    monkeypatch.setattr(browser_policy, "blocks_third_party_cookies", lambda: True)
    recorder = Recorder()

    assert recorder._channel() == ""
    assert any(browser_policy.POLICY_NAME in line for line in recorder.console_lines), (
        "the run's evidence has to say why it changed browser"
    )


def test_unmanaged_chrome_is_used_as_configured(settings, monkeypatch):
    monkeypatch.setattr(browser_policy, "blocks_third_party_cookies", lambda: False)
    recorder = Recorder()

    assert recorder._channel() == "chrome"
    assert recorder.console_lines == []


def test_an_unreadable_policy_leaves_the_run_alone(settings, monkeypatch):
    """Guessing that a browser is broken is worse than letting the run find out."""
    monkeypatch.setattr(browser_policy, "blocks_third_party_cookies", lambda: None)

    assert Recorder()._channel() == "chrome"


def test_the_check_can_be_turned_off(settings, monkeypatch):
    settings.require_third_party_cookies = False
    monkeypatch.setattr(
        browser_policy,
        "blocks_third_party_cookies",
        lambda: pytest.fail("the policy must not be read when the check is off"),
    )

    assert Recorder()._channel() == "chrome"


def test_bundled_chromium_is_never_second_guessed(settings, monkeypatch):
    settings.browser_channel = ""
    monkeypatch.setattr(
        browser_policy,
        "blocks_third_party_cookies",
        lambda: pytest.fail("bundled Chromium is not covered by a Chrome policy"),
    )

    assert Recorder()._channel() == ""


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="linux policy files")
def test_a_managed_linux_chrome_is_detected(monkeypatch, tmp_path):
    (tmp_path / "cookies.json").write_text(
        json.dumps({browser_policy.POLICY_NAME: True}), encoding="utf-8"
    )
    monkeypatch.setattr(browser_policy, "_LINUX_POLICY_DIRS", (str(tmp_path),))

    assert browser_policy.blocks_third_party_cookies() is True


def test_reading_the_policy_never_raises(monkeypatch):
    def explode():
        raise OSError("policy store unavailable")

    for name in ("_windows_policy", "_mac_policy", "_linux_policy"):
        monkeypatch.setattr(browser_policy, name, explode)

    assert browser_policy.blocks_third_party_cookies() is None
