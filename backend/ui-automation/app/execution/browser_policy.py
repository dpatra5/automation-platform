"""Whether the browser a run is about to drive will keep the recorded session.

A replayed run starts from the cookies the recorder captured. In an SSO flow
most of those belong to the identity provider, and at replay time the app asks
for them from a cross-site frame or a silent-renew iframe - so they are
third-party cookies, and a browser that drops them signs the run out before the
first step.

Managed Chrome installs are routinely given the `BlockThirdPartyCookies`
policy. A policy is not a preference: no command-line switch, profile setting
or DevTools override can turn it off, which is by design. The only thing a test
runner can do is notice, and drive a browser that is not covered by it.
"""

import json
import logging
import plistlib
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

POLICY_NAME = "BlockThirdPartyCookies"

_WINDOWS_KEY = r"Software\Policies\Google\Chrome"

# Where a managed Chrome reads its policy from on each platform.
_LINUX_POLICY_DIRS = (
    "/etc/opt/chrome/policies/managed",
    "/etc/opt/edge/policies/managed",
)
_MAC_POLICY_FILES = (
    "/Library/Managed Preferences/com.google.Chrome.plist",
    "/Library/Preferences/com.google.Chrome.plist",
)


def _windows_policy() -> Optional[bool]:
    import winreg  # Windows-only; imported here so the module stays portable.

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, _WINDOWS_KEY) as key:
                value, _ = winreg.QueryValueEx(key, POLICY_NAME)
        except OSError:
            continue
        if value is not None:
            return bool(int(value))
    return False


def _linux_policy() -> Optional[bool]:
    for directory in _LINUX_POLICY_DIRS:
        for path in sorted(Path(directory).glob("*.json")):
            try:
                policies = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(policies, dict) and POLICY_NAME in policies:
                return bool(policies[POLICY_NAME])
    return False


def _mac_policy() -> Optional[bool]:
    for name in _MAC_POLICY_FILES:
        path = Path(name)
        if not path.exists():
            continue
        try:
            policies = plistlib.loads(path.read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(policies, dict) and POLICY_NAME in policies:
            return bool(policies[POLICY_NAME])
    return False


def blocks_third_party_cookies() -> Optional[bool]:
    """True when the installed Chrome is told to drop third-party cookies.

    None when the answer cannot be read on this platform, which is treated as
    "carry on": guessing that a browser is broken is worse than letting the run
    find out for itself.
    """
    try:
        if sys.platform.startswith("win"):
            return _windows_policy()
        if sys.platform == "darwin":
            return _mac_policy()
        if sys.platform.startswith("linux"):
            return _linux_policy()
    except Exception as e:  # a policy read must never stop a run
        logger.debug("Could not read the Chrome cookie policy: %s", e)
    return None


EXPLANATION = (
    f"Chrome on this machine is managed by the {POLICY_NAME} policy, which "
    "drops the cross-site cookies an SSO session is made of - the run would "
    "start signed out. Playwright's bundled Chromium is not covered by that "
    "policy, so this run used it instead. Set BROWSER_CHANNEL= (empty) to make "
    "that the default, or REQUIRE_THIRD_PARTY_COOKIES=false to drive managed "
    "Chrome anyway."
)
