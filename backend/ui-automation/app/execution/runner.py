import asyncio
import fnmatch
import logging
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page
from app.execution import browser_policy
from app.execution.step_handlers import registry, enum_value
from app.execution.element_locator import (
    ABSENCE_ASSERTIONS,
    DRIFT_NOTE,
    ElementNotReadyError,
    element_label,
)
from app.models.models import TestRun, TestCase, StatusEnum, ActionEnum
from app.config import settings

logger = logging.getLogger(__name__)

# Substrings that mark a URL as an authentication page rather than the app.
SIGN_IN_HINTS = ("/login", "/signin", "/sign-in", "/sso", "/oauth", "/auth", "/saml")

# Class names that describe an element's state rather than what it is. A step
# whose selector contains one can only match *after* the action it performs,
# so it never matches on replay. The recorder strips these now; recordings made
# before that still carry them.
STATE_CLASSES = (
    "completed",
    "active",
    "selected",
    "checked",
    "done",
    "open",
    "expanded",
    "collapsed",
    "disabled",
    "hidden",
    "focused",
    "current",
    "editing",
    "highlighted",
)

# A class name inside a CSS selector, escapes (`.h-\[150px\]`) included.
CLASS_TOKEN = re.compile(r"\.((?:\\.|[\w-])+)")

# A webm smaller than this never received a frame. Keeping it would leave the
# dashboard with a player that cannot start instead of a usable fallback.
MIN_PLAYABLE_VIDEO_BYTES = 1024

# How far to go looking for the ancestor whose hover reveals a hidden element,
# and how long to spend on each attempt. Both are deliberately small: this is a
# recovery, not something to spend the step's whole budget on.
MAX_REVEAL_ANCESTORS = 6
REVEAL_HOVER_TIMEOUT_MS = 1000

# Failures the browser reports *before* it touches anything: the element never
# became operable, or was replaced while it was being waited on. The action did
# not happen, so running the step again cannot apply it twice. Anything not
# listed here - a check that did not hold, a selector nobody can parse - is
# reported the first time it happens.
TRANSIENT_FAILURES = (
    "element is not enabled",
    "element is not visible",
    "element is not stable",
    "element is not editable",
    "element is not attached",
    "not attached to the dom",
    "detached from the dom",
    "intercepts pointer events",
    "outside of the viewport",
    "execution context was destroyed",
    "waiting for locator",
    "element(s) not found",
)

# How long to let the app finish what it was doing before trying a step again.
SETTLE_TIMEOUT_MS = 3000

# How long to give the app to answer the step before, when the next step is the
# same action on the same selector, and how often to look while waiting. A
# tester pressing Skip four times waits for each answer without noticing; a run
# does not, and presses the button that was already pressed.
REPEAT_WAIT_S = 5.0
REPEAT_POLL_S = 0.15

# How still the page must be before the next step acts, and how long to wait for
# that stillness. Every recorded step was taken after the app had finished
# answering the one before it - that pause is part of the recording, and a run
# that skips it types the next answer into the question still being replaced.
PAGE_QUIET_MS = 500
PAGE_QUIET_CAP_S = 6.0

# A request still open after this long is a stream or a long poll the page holds
# by design. Waiting on one would stop the run for good.
STALE_REQUEST_S = 5.0

# Reports how long the document has gone unchanged, installing the watcher that
# measures it on first use. Attributes count: a button switching itself off is
# the app reacting, even when nothing is added or removed.
QUIET_PROBE = """() => {
  if (!window.__rewindQuiet) {
    window.__rewindQuiet = { at: Date.now() };
    new MutationObserver(() => { window.__rewindQuiet.at = Date.now(); })
      .observe(document, {
        subtree: true, childList: true, characterData: true, attributes: true,
      });
  }
  return Date.now() - window.__rewindQuiet.at;
}"""

# Gestures, not assertions. A hover reveals a menu and a scroll brings a row
# into view; neither is what the test is checking, and neither leaves the page
# any different when its element has moved on. Failing the run on one buries
# the step that actually matters under a timeout for a container.
OPTIONAL_ACTIONS = {ActionEnum.hover.value, ActionEnum.scroll.value}

# What a gesture gets to find its element. It is not worth the whole budget.
GESTURE_BUDGET_S = 4.0


def _bare(url: str) -> str:
    """A URL without its query string or fragment."""
    return (url or "").split("?")[0].split("#")[0].rstrip("/")


def _url_matches(actual: str, wanted: str) -> bool:
    """Whether an open tab or frame is the one a step was recorded against.

    Exact first, then a glob, then ignoring the query string - session ids and
    cache busters differ on every run and must not decide the match.
    """
    if not actual:
        return False
    if actual == wanted:
        return True
    if any(ch in wanted for ch in "*?[") and fnmatch.fnmatch(actual, wanted):
        return True
    return bool(_bare(wanted)) and _bare(actual) == _bare(wanted)


def _match_frame(page: Page, frame_url: str):
    """The frame of `page` that the step was recorded in, if it is loaded."""
    frames = [f for f in page.frames if f.url]
    for frame in frames:
        if frame.url == frame_url:
            return frame
    for frame in frames:
        if _url_matches(frame.url, frame_url):
            return frame
    return None


def execute_blocking(runner: "PlaywrightRunner") -> dict:
    """Run `runner.execute()` on a private event loop owned by this thread.

    Playwright talks to its driver over a subprocess. On Windows that needs a
    ProactorEventLoop, but `uvicorn --reload` serves on a SelectorEventLoop,
    where `create_subprocess_exec` raises NotImplementedError. Running the
    browser session on its own loop in a worker thread makes the runner work
    regardless of how the API server was started.
    """
    loop = (
        asyncio.ProactorEventLoop()
        if sys.platform == "win32"
        else asyncio.new_event_loop()
    )
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(runner.execute())
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%H:%M:%S.%f")[:-3]


def _first_line(error: Exception) -> str:
    """The headline of a browser error, without its call log."""
    return (
        str(error).strip().splitlines()[0]
        if str(error).strip()
        else type(error).__name__
    )


def _step_key(step) -> tuple:
    """What makes two steps the same instruction, given twice."""
    return (
        enum_value(step.action),
        enum_value(step.selector_strategy),
        step.selector,
        step.value,
    )


async def _handle_for(locator):
    """A reference to the node itself, rather than to the query that found it.

    A locator is re-read every time it is used, so `nth(2)` means whatever sits
    third at the moment it is read. Only a handle can answer whether the app has
    since replaced what was acted on.
    """
    try:
        return await locator.element_handle()
    except Exception:
        return None


async def _still_offered(element) -> bool:
    """Whether the node acted on is still on the page and still accepting."""
    try:
        return bool(
            await element.evaluate(
                "el => el.isConnected && !el.disabled"
                " && el.getAttribute('aria-disabled') !== 'true'"
            )
        )
    except Exception:
        return False


class PlaywrightRunner:
    """Executes a test run by driving Chrome through the recorded steps."""

    def __init__(
        self,
        run: TestRun,
        test_case: TestCase,
        auth_state_path: str | None = None,
        on_step: Callable[[dict], None] | None = None,
        silent_mode: bool = False,
    ):
        self.run = run
        self.test_case = test_case
        self.auth_state_path = auth_state_path
        # Called from the runner thread after every step, so the dashboard can
        # show the traversal filling in live instead of only at the end.
        self.on_step = on_step
        self.silent_mode = silent_mode
        self.artifacts_dir = Path(settings.artifacts_dir) / self.run.id
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.console_lines: list[str] = []
        self.network_lines: list[str] = []
        # Steps whose recorded selector matched something unrecognisable. They
        # do not fail; they are why a later step finds the app waiting.
        self.drifted_steps: list[tuple[int, str]] = []
        # The tab the steps currently act on; a switch_tab step moves it.
        self.page: Page | None = None
        self._prepared: set = set()
        # What the step before acted on, so a step repeating it can wait for
        # the app to answer instead of pressing the same button twice.
        self._acted_key: tuple | None = None
        self._acted_element = None
        self._acted_matches = 0
        # Requests the page has out, and when each started.
        self._in_flight: dict = {}

    # ---------- capture ----------

    def _attach_capture(self, page: Page) -> None:
        """Record everything the page emits, so a run can be reconstructed."""
        page.on(
            "console",
            lambda m: self.console_lines.append(
                f"[{_stamp()}] {m.type.upper():8} {m.text}"
            ),
        )
        page.on(
            "pageerror",
            lambda e: self.console_lines.append(f"[{_stamp()}] PAGEERROR {e}"),
        )
        page.on(
            "dialog",
            lambda d: self.console_lines.append(
                f"[{_stamp()}] DIALOG    {d.type}: {d.message}"
            ),
        )
        page.on(
            "framenavigated",
            lambda f: (
                f.parent_frame is None
                and self.console_lines.append(f"[{_stamp()}] NAVIGATE  {f.url}")
            ),
        )

        page.on(
            "request",
            lambda r: self.network_lines.append(
                f"[{_stamp()}] --> {r.method:6} {r.url}"
            ),
        )
        page.on(
            "response",
            lambda r: self.network_lines.append(
                f"[{_stamp()}] <-- {r.status:6} {r.url}"
            ),
        )
        page.on(
            "requestfailed",
            lambda r: self.network_lines.append(
                f"[{_stamp()}] !!! {r.method:6} {r.url} ({r.failure})"
            ),
        )

        # Counted as well as logged: a step must not act while the answer to
        # the step before it is still on its way.
        page.on("request", lambda r: self._in_flight.setdefault(r, time.monotonic()))
        page.on("requestfinished", lambda r: self._in_flight.pop(r, None))
        page.on("requestfailed", lambda r: self._in_flight.pop(r, None))

    @staticmethod
    def _record_video() -> bool:
        """Whether to ask Playwright for a video of this run.

        Every run is filmed by default. Headed Chrome only paints its recording
        surface while the window is in front, so the runner raises the window
        before the first step; if a file still ends up unusable the dashboard
        falls back to a filmstrip built from the per-step screenshots.
        """
        return (settings.video or "on").lower() != "off"

    async def _launch(self, p):
        """Launch Chrome, falling back to bundled Chromium if Chrome is absent.
        
        In silent mode, try to connect to existing Chrome first, then fall back to launching.
        """
        import sys
        
        print(f"[_launch] DEBUG: silent_mode={self.silent_mode}", file=sys.stderr, flush=True)
        
        # In silent mode, try to connect to existing browser first (new tab in existing window)
        if self.silent_mode:
            print("[_launch] DEBUG: Attempting CDP connection", file=sys.stderr, flush=True)
            try:
                browser = await self._connect_to_existing_browser(p)
                if browser:
                    print("[_launch] DEBUG: CDP connection succeeded!", file=sys.stderr, flush=True)
                    self.console_lines.append(
                        f"[{_stamp()}] INFO      ✓ Connected to Chrome on port 9222 - opening new tab"
                    )
                    return browser
            except Exception as e:
                print(f"[_launch] ERROR in CDP connection: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                logger.debug(f"Could not connect to existing browser for silent mode: {e}")
            
            # If connection failed, inform user
            print("[_launch] DEBUG: CDP failed, will use fallback", file=sys.stderr, flush=True)
            self.console_lines.append(
                f"[{_stamp()}] WARN      Silent mode: Could not connect to Chrome on port 9222"
            )
            self.console_lines.append(
                f"[{_stamp()}] WARN      To use silent mode, start Chrome with:"
            )
            self.console_lines.append(
                f"[{_stamp()}] WARN      chrome --remote-debugging-port=9222"
            )
            self.console_lines.append(
                f"[{_stamp()}] WARN      Falling back to launching new browser..."
            )
        
        print("[_launch] DEBUG: Launching new browser", file=sys.stderr, flush=True)
        
        # Normal mode or fallback: launch new browser
        opts = {"headless": settings.headless}
        if settings.slow_mo_ms:
            opts["slow_mo"] = settings.slow_mo_ms
        if not settings.headless:
            # Size the real window instead of emulating a viewport inside a
            # differently sized one - see _context_options for why.
            opts["args"] = [
                f"--window-size={settings.viewport_width},{settings.viewport_height}",
                "--window-position=0,0",
            ]
        channel = self._channel()
        if channel:
            try:
                return await p.chromium.launch(channel=channel, **opts)
            except Exception as e:
                logger.warning(
                    f"Chrome channel '{channel}' unavailable ({e}); "
                    "falling back to bundled Chromium"
                )
        return await p.chromium.launch(**opts)

    async def _connect_to_existing_browser(self, p):
        """Try to connect to already running Chrome browser via CDP.
        
        This allows silent mode to open a new tab in the user's existing browser
        instead of launching a separate browser process.
        """
        import socket
        import urllib.request
        import json
        import sys
        
        print("[CDP] Starting connection attempt", file=sys.stderr, flush=True)
        
        try:
            # Step 1: Check if Chrome is listening on remote debugging port
            print("[CDP] Step 1: Checking if port 9222 is open", file=sys.stderr, flush=True)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 9222))
            sock.close()
            
            print(f"[CDP] Port check result: {result}", file=sys.stderr, flush=True)
            
            if result != 0:  # Port is closed
                print("[CDP] Port 9222 is not open", file=sys.stderr, flush=True)
                self.console_lines.append(
                    f"[{_stamp()}] DEBUG     Port 9222 not open - Chrome not running with --remote-debugging-port=9222"
                )
                return None
            
            print("[CDP] Port 9222 is open!", file=sys.stderr, flush=True)
            self.console_lines.append(
                f"[{_stamp()}] INFO      Port 9222 is open - attempting CDP connection to Chrome..."
            )
            
            # Step 2: Get Chrome DevTools endpoint info
            print("[CDP] Step 2: Getting endpoint info from http://127.0.0.1:9222/json/version", file=sys.stderr, flush=True)
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2) as response:
                    endpoint_data = json.loads(response.read())
                    print(f"[CDP] Endpoint data: {endpoint_data}", file=sys.stderr, flush=True)
                    self.console_lines.append(
                        f"[{_stamp()}] DEBUG     Chrome endpoint found: {endpoint_data.get('Browser', 'unknown')}"
                    )
            except Exception as e:
                print(f"[CDP] Endpoint check failed: {e}", file=sys.stderr, flush=True)
                self.console_lines.append(
                    f"[{_stamp()}] DEBUG     Endpoint check: {e}"
                )
            
            # Step 3: Connect via CDP
            print("[CDP] Step 3: Attempting connect_over_cdp", file=sys.stderr, flush=True)
            try:
                browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                print("[CDP] SUCCESS! Connected to Chrome", file=sys.stderr, flush=True)
                self.console_lines.append(
                    f"[{_stamp()}] INFO      ✓ Successfully connected to Chrome via CDP on port 9222"
                )
                logger.info("Successfully connected to Chrome via CDP on port 9222")
                return browser
            except Exception as e:
                print(f"[CDP] connect_over_cdp failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                self.console_lines.append(
                    f"[{_stamp()}] ERROR     CDP connection failed: {e}"
                )
                logger.error(f"CDP connection failed: {e}")
                return None
                
        except Exception as e:
            print(f"[CDP] Outer exception: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            self.console_lines.append(
                f"[{_stamp()}] ERROR     Error connecting to Chrome: {e}"
            )
            logger.error(f"Error in _connect_to_existing_browser: {e}")
        
        return None

    def _channel(self) -> str:
        """The Chrome build to drive, unless its policy would drop the session.

        A managed Chrome carrying `BlockThirdPartyCookies` throws away the
        cross-site cookies the recorded session is made of, so every step after
        the first lands on a sign-in page. The policy cannot be overridden from
        inside the browser, so the run moves to a browser it does not cover.
        """
        channel = settings.browser_channel
        if not channel or not settings.require_third_party_cookies:
            return channel
        if not browser_policy.blocks_third_party_cookies():
            return channel

        logger.warning(browser_policy.EXPLANATION)
        self.console_lines.append(
            f"[{_stamp()}] WARN      {browser_policy.EXPLANATION}"
        )
        return ""

    def _context_options(self) -> dict:
        """How the browser context should be sized and recorded.

        A headed run uses the window's own size (`no_viewport`). Setting an
        explicit viewport makes Playwright push a device-metrics override onto
        the tab, so the page renders at that size and is then squeezed into
        whatever the real window is - the page looks zoomed and cropped, and
        every screenshot re-applies the override, which is what makes the
        window flicker. Headless has no real window, so there it is required.
        """
        opts: dict = {}
        if settings.headless:
            opts["viewport"] = {
                "width": settings.viewport_width,
                "height": settings.viewport_height,
            }
        else:
            opts["no_viewport"] = True

        if self._record_video():
            opts["record_video_dir"] = str(self.artifacts_dir)
            if settings.headless:
                # Only meaningful with a fixed viewport; with a real window
                # Playwright films at the window's own size.
                opts["record_video_size"] = {
                    "width": settings.viewport_width,
                    "height": settings.viewport_height,
                }
        if self.auth_state_path:
            opts["storage_state"] = self.auth_state_path
        return opts

    @staticmethod
    async def _context_with_page(browser, options: dict):
        """A traced context and its first page, or nothing left half-open."""
        context = await browser.new_context(**options)
        try:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            return context, await context.new_page()
        except Exception:
            await context.close()
            raise

    async def _open_context(self, browser):
        """Open the context to run in, giving up the video rather than the run.

        Playwright only spawns the video recorder when the first page opens, so
        a machine without its ffmpeg binary fails there - and video is evidence
        the run is nice to have, not a reason to lose the trace, the logs and
        the screenshots along with it.
        """
        options = self._context_options()
        try:
            return await self._context_with_page(browser, options)
        except Exception as e:
            if "record_video_dir" not in options:
                raise
            logger.warning("Could not record video (%s); running without it", e)
            self.console_lines.append(
                f"[{_stamp()}] WARN      Video could not be recorded ({e}). The trace and "
                "the per-step screenshots still cover this run."
            )
            options.pop("record_video_dir", None)
            options.pop("record_video_size", None)
            return await self._context_with_page(browser, options)

    # ---------- auth ----------

    def _same_site(self, url: str) -> bool:
        start = urlparse(self.test_case.start_url or "")
        return not start.netloc or urlparse(url).netloc == start.netloc

    def _looks_like_sign_in(self, url: str) -> bool:
        """A run bounced to an identity provider, or to a login route."""
        lowered = (url or "").lower()
        return not self._same_site(url) or any(
            hint in lowered for hint in SIGN_IN_HINTS
        )

    @staticmethod
    def _stale_state_class(step) -> str | None:
        """The state class in this step's selector, if it has one.

        Whole class names only: `overflow-hidden` is a layout utility that
        merely ends in a state word, and blaming it sends the tester after a
        bug that is not there.
        """
        selector = getattr(step, "selector", "") or ""
        for token in CLASS_TOKEN.findall(selector):
            name = token.replace("\\", "").casefold()
            if name in STATE_CLASSES:
                return name
            prefix, _, rest = name.partition("-")
            if prefix in ("is", "has") and rest in STATE_CLASSES:
                return name
        return None

    def _explain(self, error: Exception, page: Page, step=None) -> str:
        """Prefix a raw Playwright error with a diagnosis when one applies.

        Diagnosis is best-effort: it must never replace the real error.
        """
        message = str(error)
        try:
            # Already a diagnosis, written where the facts were: the element
            # was found, it was on screen, and the app held it shut. Prefixing
            # it with a guess would only bury it.
            if isinstance(error, ElementNotReadyError):
                return message + self._drift_aside(step)

            if "element is not enabled" in message:
                attempts = max(1, settings.step_retry_attempts + 1)
                return (
                    "The element was enabled when the run looked at it and switched "
                    "off again by the time it acted, on every one of the "
                    f"{attempts} attempts. An app that locks a control the instant "
                    "work starts is changing it faster than a step can follow. Add a "
                    "wait step for whatever settles first - a selector like "
                    "'input:not([disabled])' matches nothing until the app is ready - "
                    "or raise ELEMENT_BUSY_TIMEOUT_MS so the run keeps waiting for "
                    f"it.\n\n{message}"
                )

            if "not stable" in message or "detached from the DOM" in message:
                return (
                    "The element kept moving, or was replaced, while the step was acting "
                    "on it. That is an animation still running or a list the app is "
                    "re-rendering underneath. Wait for whatever settles it first, then "
                    f"act.\n\n{message}"
                )

            stale = self._stale_state_class(step) if step is not None else None
            if stale:
                return (
                    f"The selector contains '{stale}', a class the app only adds once this "
                    f"action has happened, so it can never match beforehand. Recordings made "
                    f"before this was fixed carry these - re-record the flow, or edit the "
                    f"selector on the test case.\n\n{message}"
                )

            url = page.url
            if isinstance(url, str) and url and self._looks_like_sign_in(url):
                return (
                    f"The run ended up on a sign-in page ({url}). The saved session was "
                    f"rejected or has expired - record the flow again to refresh it.\n\n{message}"
                )

            # Last resort, and the common one: a step that timed out reads as a
            # selector nobody can interpret. Say which element it was after.
            label = element_label(step) if step is not None else ""
            if label and "Timeout" in message:
                return (
                    f"Timed out on the element the recording called {label!r}. Nothing "
                    "the recording knows about it - the selector, its role, its label, "
                    "its text - reached an element that was on screen and operable "
                    "within the time allowed. The screenshot for this step shows what "
                    f"the page was actually showing.\n\n{message}"
                )
        except Exception as diag_e:
            logger.debug(f"Could not diagnose step failure: {diag_e}")
        return message

    async def _warn_if_ambiguous(self, step, scope) -> None:
        """Note in the evidence when a recorded selector now matches several elements.

        The resolver picks between them by what the element was recorded as,
        but a silent extra match is exactly the kind of regression this tool
        exists to surface.
        """
        try:
            locator = registry.resolve_locator(step, scope)
            if locator is None:
                return
            count = await locator.count()
            if count > 1:
                self.console_lines.append(
                    f"[{_stamp()}] AMBIGUOUS #{step.order_index} {step.selector!r} "
                    f"matched {count} elements; choosing by what was recorded"
                )
        except Exception as e:
            logger.debug(f"Ambiguity check skipped: {e}")

    def _note_for(self, step) -> Callable[[str], None]:
        """Record in the evidence how a step's element was found.

        Healing is a finding, not a detail: a selector that no longer works is
        the first sign the UI has moved, and the tester should see it even
        though the run carried on. The same line carries the waiting notes, so
        a step that sat still for half a minute says why afterwards.
        """

        def note(message: str) -> None:
            if DRIFT_NOTE in message:
                self.drifted_steps.append(
                    (step.order_index, element_label(step) or step.selector or "")
                )
            self.console_lines.append(
                f"[{_stamp()}] ELEMENT   #{step.order_index} {message}"
            )

        return note

    def _drift_aside(self, step=None) -> str:
        """Name an earlier step that acted on something it did not recognise.

        A run that clicked the wrong thing does not fail there - clicking a
        div always works. It fails further on, where the app is still waiting
        for an answer it was never given, and that step gets the blame. The
        earlier one is the one to look at.
        """
        here = getattr(step, "order_index", None)
        earlier = [
            (index, label)
            for index, label in self.drifted_steps
            if here is None or index != here
        ]
        if not earlier:
            return ""
        index, label = earlier[-1]
        return (
            f"\n\nLook at step #{index} first. Its recorded selector no longer "
            f"matched anything like {label!r}, so the run acted on whatever that "
            "path happens to point at now - which for a path built out of "
            "positions is often the wrong element. If that step did not do what "
            "it did while recording, the app would still be waiting here."
        )

    @staticmethod
    def _may_retry(step, error: Exception) -> bool:
        """Whether this failure is worth another attempt.

        Only the ones the browser raises without having acted. A check that
        simply did not hold is a result rather than a blip, and a check for
        absence would spend the whole budget proving the same thing twice. An
        element the app has been holding shut for minutes has already been
        waited for properly; asking again would only repeat the wait.
        """
        if isinstance(error, ElementNotReadyError):
            return False
        message = str(error).lower()
        if not any(mark in message for mark in TRANSIENT_FAILURES):
            return False
        if enum_value(step.action) != ActionEnum.assert_.value:
            return True
        return (getattr(step, "assertion_type", None) or "") not in ABSENCE_ASSERTIONS

    async def _settle(self, page: Page) -> None:
        """Let an app that is mid-request finish before the step is tried again.

        A control the app locks while it is busy comes back on its own once the
        requests behind it land. Waiting for that is the wait a tester would
        have added by hand, and it is why a second attempt is worth making.
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
        except Exception as e:
            logger.debug(f"Settle skipped: {e}")

    def _budget_for(self, step) -> tuple[int, float, float]:
        """How many attempts a step gets, how long each may look, and how long
        it may wait out an app that has locked the element.

        A gesture gets one short attempt and no waiting. Trying three times to
        hover something that is not there spends the run's time on the least of
        what it came to do.
        """
        if enum_value(step.action) in OPTIONAL_ACTIONS:
            return 1, GESTURE_BUDGET_S, 0
        attempts = max(1, settings.step_retry_attempts + 1)
        share_s = settings.element_ready_timeout_ms / 1000 / attempts
        return attempts, share_s, settings.element_busy_timeout_ms / 1000

    async def _match_count(self, step, scope) -> int:
        """How many elements the recorded selector matches at this moment."""
        try:
            locator = registry.resolve_locator(step, scope)
            return await locator.count() if locator is not None else 0
        except Exception as e:
            logger.debug(f"Could not count matches for step {step.order_index}: {e}")
            return 0

    async def _still_for_ms(self, scope) -> float | None:
        """How long the document has gone unchanged, or None if it cannot say."""
        try:
            reading = await scope.evaluate(QUIET_PROBE)
        except Exception as e:
            logger.debug(f"Quiet probe unavailable: {e}")
            return None
        return float(reading) if isinstance(reading, (int, float)) else None

    def _busy_with_requests(self) -> bool:
        """Whether the app has a request out that the next step should wait for."""
        cutoff = time.monotonic() - STALE_REQUEST_S
        self._in_flight = {
            request: started
            for request, started in self._in_flight.items()
            if started > cutoff
        }
        return bool(self._in_flight)

    async def _how_much_longer(self, scope) -> float:
        """Seconds still to wait before the page can be called settled.

        A request out with no answer yet counts as the app working even while
        the page sits perfectly still - which is exactly how it sits between
        pressing a button and the reply that redraws the screen.
        """
        if self._busy_with_requests():
            return REPEAT_POLL_S
        waited = await self._still_for_ms(scope)
        if waited is None:
            return 0
        return max(PAGE_QUIET_MS - waited, 0) / 1000

    async def _let_the_app_catch_up(self, step, scope) -> None:
        """Wait for the page to stop changing before the step acts.

        A recording is made at the speed of a person: the tester pressed Skip,
        watched the next question arrive, and only then typed. Replayed at the
        speed elements can be found, the typing goes into the box belonging to
        the question being replaced, and the answer lands against the wrong one
        - which is worse than failing, because the run carries on.

        Capped, because a page with a spinner or a clock on it never falls
        completely still, and a run must not stop for one.
        """
        if enum_value(step.action) in OPTIONAL_ACTIONS:
            return
        deadline = time.monotonic() + PAGE_QUIET_CAP_S
        while time.monotonic() < deadline:
            pause = await self._how_much_longer(scope)
            if pause <= 0:
                return
            await asyncio.sleep(pause)
        logger.debug(f"Step {step.order_index}: the page never stopped changing")

    async def _remember_target(self, step, locator, matches: int) -> None:
        """Keep what this step acted on, for the step after it to compare with.

        A gesture answers nothing, so it does not take the place of the memory:
        a hover recorded between two presses of the same button must not hide
        that they are two presses of the same button.
        """
        if enum_value(step.action) in OPTIONAL_ACTIONS:
            return
        self._acted_key = _step_key(step)
        self._acted_matches = matches
        self._acted_element = await _handle_for(locator)

    async def _await_the_apps_answer(self, step, scope) -> None:
        """Hold a step that repeats the one before it until the app has moved on.

        Four Skips in a row are four questions, not four clicks: the button for
        the next one exists only once the app has drawn it. Fired back to back,
        the run presses the button it has already pressed, gets no complaint
        from the browser for doing so, and arrives at the end of four skips
        having skipped twice.

        The wait ends the moment that button goes, is switched off, or is
        joined by another like it. It is capped because some buttons really do
        stay: where the app keeps one, the pause itself is the interval the
        tester's own hand gave it.
        """
        if self._acted_element is None or self._acted_key != _step_key(step):
            return
        deadline = time.monotonic() + REPEAT_WAIT_S
        while time.monotonic() < deadline:
            if not await _still_offered(self._acted_element):
                return
            if await self._match_count(step, scope) != self._acted_matches:
                return
            await asyncio.sleep(REPEAT_POLL_S)
        self.console_lines.append(
            f"[{_stamp()}] REPEAT    #{step.order_index} the app still offers the "
            f"same element as the step before after {REPEAT_WAIT_S:g}s; acting on it again"
        )

    async def _run_step(self, step) -> None:
        """Run one step, trying again while its failure still looks transient.

        Every attempt looks the element up afresh: a page that re-renders
        replaces the node, and the one resolved a moment ago is then a
        reference to something no longer on screen.

        The attempts share the budget for finding an element, so a step whose
        element has genuinely gone costs no more than it did on one attempt.
        Waiting out an app that has locked the element is different: that is
        one long wait, not three short ones, so it happens on the first
        attempt and the retries get none of it. Either way each attempt acts
        with the full step timeout - an action given the scraps of a budget
        fails for no better reason than that it was rushed.
        """
        attempts, share_s, busy_s = self._budget_for(step)
        deadline = time.monotonic() + share_s * attempts
        last: Exception | None = None

        for attempt in range(1, attempts + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0 and last is not None:
                break
            scope = await self._scope_for(step, self.page)
            if attempt == 1:
                await self._let_the_app_catch_up(step, scope)
                await self._await_the_apps_answer(step, scope)
                await self._warn_if_ambiguous(step, scope)
            await self._reveal_if_hidden(step, scope)
            try:
                matches = await self._match_count(step, scope)
                acted = await registry.execute(
                    step,
                    self.page,
                    scope,
                    on_note=self._note_for(step),
                    ready_budget_s=max(min(share_s, remaining), 0),
                    busy_budget_s=busy_s,
                )
                await self._remember_target(step, acted, matches)
                return
            except Exception as step_e:
                last = step_e
                busy_s = 0
                if attempt == attempts or not self._may_retry(step, step_e):
                    break
                self.console_lines.append(
                    f"[{_stamp()}] RETRY     #{step.order_index} attempt {attempt} "
                    f"of {attempts} could not act on the element; waiting for the "
                    "app to go quiet and looking for it again"
                )
                await self._settle(self.page)
        if last is not None:
            self._raise_unless_optional(step, last)

    def _raise_unless_optional(self, step, error: Exception) -> None:
        """Fail the run, unless the step was only a gesture.

        A hover that finds nothing is not a failing test: the pointer was
        somewhere the page no longer has anything to show. The step that comes
        after it will report the real problem, and far better than a timeout
        on a container ever could.
        """
        if enum_value(step.action) not in OPTIONAL_ACTIONS:
            raise error
        self.console_lines.append(
            f"[{_stamp()}] SKIPPED   #{step.order_index} "
            f"{enum_value(step.action)} could not reach its element and only moves "
            f"the pointer, so the run carried on: {_first_line(error)}"
        )

    async def _reveal_if_hidden(self, step, scope) -> None:
        """Hover an element's ancestors when it is there but not yet shown.

        A menu that opens on CSS `:hover` alone changes no markup, so nothing a
        recorder watches for ever fires and no hover step is captured. Replay
        would then wait out the clock on an element the page only shows while
        the pointer rests on its parent. Hovering the nearest visible ancestor
        puts the pointer back where the tester had it.

        Not worth doing for a gesture: hovering a chain of ancestors to make a
        hover possible is more work than the hover was ever going to be worth.
        """
        if enum_value(step.action) in OPTIONAL_ACTIONS:
            return
        try:
            locator = registry.resolve_locator(step, scope)
            if locator is None:
                return
            target = locator.first
            if await target.count() == 0 or await target.is_visible():
                return

            ancestors = target.locator("xpath=ancestor::*")
            total = await ancestors.count()
            tried = 0
            for index in range(total - 1, -1, -1):  # nearest ancestor first
                if tried >= MAX_REVEAL_ANCESTORS:
                    return
                candidate = ancestors.nth(index)
                if not await candidate.is_visible():
                    continue
                tried += 1
                await candidate.hover(timeout=REVEAL_HOVER_TIMEOUT_MS)
                if await target.is_visible():
                    self.console_lines.append(
                        f"[{_stamp()}] REVEAL    #{step.order_index} hovered an ancestor "
                        f"to bring {step.selector!r} into view"
                    )
                    return
        except Exception as e:
            # Best effort: the step's own wait still decides whether it passes.
            logger.debug(f"Reveal attempt skipped: {e}")

    # ---------- frames and tabs ----------

    async def _scope_for(self, step, page: Page):
        """Where to look for this step's element: the page, or one of its frames.

        Products that stream their whole UI into an iframe - Windchill, Veeva
        Vault - record every step against that frame. Frames are matched on URL
        rather than on an `iframe[...]` selector, which survives nesting and
        the wrapper markup changing between runs.
        """
        frame_url = (getattr(step, "frame_url", None) or "").strip()
        if not frame_url:
            return page

        deadline = time.monotonic() + settings.step_timeout_ms / 1000
        while True:
            frame = _match_frame(page, frame_url)
            if frame is not None:
                return frame
            if time.monotonic() >= deadline:
                seen = (
                    ", ".join(sorted({f.url for f in page.frames if f.url})) or "none"
                )
                raise RuntimeError(
                    f"The frame this step was recorded in never appeared "
                    f"({frame_url}). Frames currently loaded: {seen}"
                )
            await asyncio.sleep(0.25)

    async def _switch_tab(self, step, context) -> None:
        """Make the tab the recording moved to the active one.

        A link with target=_blank, or a window.open, gives Playwright a new
        page in the same context. Without following it the rest of the
        recording would be replayed against the tab the user had left.
        """
        target = (step.value or "").strip()
        if not target:
            raise RuntimeError("A switch tab step needs the URL of the tab to move to.")

        deadline = time.monotonic() + settings.navigation_timeout_ms / 1000
        while True:
            for candidate in context.pages:
                if candidate.is_closed():
                    continue
                if _url_matches(candidate.url, target):
                    if candidate is not self.page:
                        self.console_lines.append(
                            f"[{_stamp()}] TAB       now driving {candidate.url}"
                        )
                    self.page = candidate
                    self._prepare_page(candidate)
                    try:
                        await candidate.bring_to_front()
                    except Exception as e:
                        logger.debug(f"Could not raise the switched tab: {e}")
                    return
            if time.monotonic() >= deadline:
                open_urls = (
                    ", ".join(p.url for p in context.pages if not p.is_closed())
                    or "none"
                )
                raise RuntimeError(
                    f"No open tab matched {target}. Open tabs: {open_urls}"
                )
            await asyncio.sleep(0.25)

    def _prepare_page(self, page: Page) -> None:
        """Apply this run's timeouts and capture to a page, exactly once."""
        if page in self._prepared:
            return
        self._prepared.add(page)
        page.set_default_timeout(settings.step_timeout_ms)
        # Separate from the step timeout: a first hit can spend seconds on
        # DNS, TLS and redirects before the app is even reached.
        page.set_default_navigation_timeout(settings.navigation_timeout_ms)
        self._attach_capture(page)

    def _adopt_page(self, page: Page) -> None:
        """A tab the app opened by itself. Capture it, but do not switch to it.

        Switching is a recorded decision (`switch_tab`), so a popup the flow
        never touches cannot hijack the rest of the run.
        """
        self.console_lines.append(
            f"[{_stamp()}] TAB       opened {page.url or 'about:blank'}"
        )
        self._prepare_page(page)

    async def _capture_step_screenshot(self, position: int) -> str | None:
        """Screenshot after a step; never lets a capture failure fail the run."""
        name = f"step_{position}_screenshot.png"
        try:
            await self.page.screenshot(path=str(self.artifacts_dir / name))
            return f"artifacts/{self.run.id}/{name}"
        except Exception as e:
            logger.warning(f"Step screenshot failed: {e}")
            return None

    def _error_result(self, message: str) -> dict:
        logger.error(message)
        return {
            "status": StatusEnum.error,
            "error_message": message,
            "finished_at": _now(),
            "step_results": [],
            "evidences": [],
        }

    def _ordered_steps(self) -> list:
        """Recorded steps first, then the exit criteria that judge the result.

        The ORM already sorts them this way; sorting again keeps the runner
        correct when it is handed a plain list, as the tests do.
        """
        steps = list(self.test_case.steps or [])
        return sorted(
            steps,
            key=lambda s: (bool(getattr(s, "is_exit_criteria", False)), s.order_index),
        )

    def _write_logs(self) -> list[dict]:
        """Collect the run's artefacts and flush the captured logs."""
        rel = f"artifacts/{self.run.id}"
        evidences = [
            {"type": "console_log", "file_path": f"{rel}/console.log"},
            {"type": "network_log", "file_path": f"{rel}/network.log"},
        ]

        for pattern, ev_type in (("*.webm", "video"), ("*.zip", "trace")):
            for f in sorted(self.artifacts_dir.glob(pattern)):
                # A film that never got a frame is worse than none: the player
                # would sit on a broken file instead of falling back to the
                # screenshot filmstrip.
                if ev_type == "video" and f.stat().st_size < MIN_PLAYABLE_VIDEO_BYTES:
                    self.console_lines.append(
                        f"[{_stamp()}] INFO      Discarded an empty video file ({f.name}); "
                        "the dashboard replays the step screenshots instead."
                    )
                    f.unlink(missing_ok=True)
                    continue
                evidences.append({"type": ev_type, "file_path": f"{rel}/{f.name}"})

        if (self.artifacts_dir / "failure.png").exists():
            evidences.append({"type": "screenshot", "file_path": f"{rel}/failure.png"})

        # Written last so late notes above still make it into the file.
        (self.artifacts_dir / "console.log").write_text(
            "\n".join(self.console_lines) or "(no console output)", encoding="utf-8"
        )
        (self.artifacts_dir / "network.log").write_text(
            "\n".join(self.network_lines) or "(no network activity)", encoding="utf-8"
        )
        return evidences

    # ---------- execution ----------

    async def execute(self) -> dict:
        """Open Chrome at the start URL, traverse every step, capture evidence."""
        import sys
        print(f"[execute] START: silent_mode={self.silent_mode}", file=sys.stderr, flush=True)
        
        async with async_playwright() as p:
            try:
                print("[execute] Calling _launch()", file=sys.stderr, flush=True)
                browser = await self._launch(p)
                print("[execute] _launch() completed successfully", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[execute] _launch() failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                return self._error_result(f"Failed to launch browser: {e}")

            # In silent mode connected to existing browser, open new page directly
            # Otherwise create a new context with stored auth
            print(f"[execute] After _launch, silent_mode={self.silent_mode}", file=sys.stderr, flush=True)
            if self.silent_mode:
                try:
                    # Try to open new page in default context (existing browser)
                    print("[execute] Opening new page in existing browser", file=sys.stderr, flush=True)
                    page = await browser.new_page()
                    context = None  # No separate context when using existing browser
                    self.console_lines.append(
                        f"[{_stamp()}] INFO      Opened new tab in existing Chrome browser"
                    )
                except Exception as e:
                    # If that fails, create context normally (fallback to new browser)
                    try:
                        context, page = await self._open_context(browser)
                    except Exception as context_e:
                        await browser.close()
                        return self._error_result(f"Failed to create browser context: {context_e}")
            else:
                try:
                    context, page = await self._open_context(browser)
                except Exception as e:
                    await browser.close()
                    return self._error_result(f"Failed to create browser context: {e}")

            # Only register page handler if we have a separate context
            if context:
                # A target=_blank link or a window.open gives the context a new
                # page. Capturing it here means its console and network traffic are
                # in the evidence even before a switch_tab step moves onto it.
                context.on("page", self._adopt_page)

            if not self._record_video():
                self.console_lines.append(
                    f"[{_stamp()}] INFO      Video disabled (VIDEO=off); the trace and the "
                    "per-step screenshots still cover this run."
                )

            self.page = page
            self._prepare_page(page)
            
            # In silent mode with existing browser, browser is already visible
            # In normal mode, try to raise the browser window for visibility
            if not self.silent_mode:
                try:
                    await page.bring_to_front()
                except Exception as e:
                    logger.debug(f"Could not raise the browser window: {e}")
            else:
                self.console_lines.append(
                    f"[{_stamp()}] INFO      Silent mode enabled - running in existing browser tab"
                )

            status = StatusEnum.passed
            error_msg = None
            step_results = []
            # The step that broke already carries the diagnosis; the run-level
            # message is what the dashboard shows first, so reuse it there.
            failure_detail = None

            try:
                if self.test_case.start_url:
                    self.console_lines.append(
                        f"[{_stamp()}] STEP      open {self.test_case.start_url}"
                    )
                    await page.goto(
                        self.test_case.start_url, wait_until="domcontentloaded"
                    )
                    # Landing on an identity provider means the session did not
                    # take. Say so now instead of after a step times out.
                    if self.auth_state_path and self._looks_like_sign_in(page.url):
                        raise RuntimeError(
                            f"Opening {self.test_case.start_url} redirected to {page.url}. "
                            "The saved sign-in was not accepted - record the flow again to refresh it."
                        )

                for position, step in enumerate(self._ordered_steps(), start=1):
                    start_time = _now()
                    step_status = StatusEnum.passed
                    step_error = None
                    kind = (
                        "EXIT      "
                        if getattr(step, "is_exit_criteria", False)
                        else "STEP      "
                    )
                    frame_note = (
                        f" frame={step.frame_url!r}"
                        if getattr(step, "frame_url", None)
                        else ""
                    )
                    label = element_label(step)
                    label_note = f" label={label!r}" if label else ""
                    self.console_lines.append(
                        f"[{_stamp()}] {kind}#{step.order_index} {enum_value(step.action)} "
                        f"{enum_value(step.selector_strategy)}={step.selector!r} "
                        f"value={step.value!r}{label_note}{frame_note}"
                    )
                    try:
                        if enum_value(step.action) == ActionEnum.switch_tab.value:
                            # Handled here, not by a step handler: it changes
                            # which page the rest of the run drives.
                            await self._switch_tab(step, context)
                        else:
                            await self._run_step(step)
                    except Exception as step_e:
                        step_status = StatusEnum.failed
                        step_error = self._explain(step_e, self.page, step)
                        failure_detail = step_error
                        raise
                    finally:
                        duration = int((_now() - start_time).total_seconds() * 1000)
                        # Numbered by position, not order_index: a flow step and
                        # an exit criterion can share an index and would
                        # otherwise overwrite each other's screenshot.
                        screenshot_path = await self._capture_step_screenshot(position)

                        result = {
                            "step_id": step.id,
                            "status": step_status,
                            "error_message": step_error,
                            "duration_ms": duration,
                            "screenshot_path": screenshot_path,
                        }
                        step_results.append(result)
                        if self.on_step:
                            self.on_step(result)

            except Exception as e:
                status = StatusEnum.failed
                error_msg = failure_detail or self._explain(e, self.page)
                try:
                    await self.page.screenshot(
                        path=str(self.artifacts_dir / "failure.png")
                    )
                except Exception:
                    pass
            finally:
                # Only close context if we created one (not for existing browser mode)
                closers = []
                if context:
                    closers.append(
                        lambda: context.tracing.stop(
                            path=str(self.artifacts_dir / "trace.zip")
                        )
                    )
                    closers.append(context.close)  # flushes the video file
                closers.append(browser.close)
                
                for closer in closers:
                    try:
                        await closer()
                    except Exception as e:
                        logger.warning(f"Teardown step failed: {e}")

            return {
                "status": status,
                "error_message": error_msg,
                "finished_at": _now(),
                "step_results": step_results,
                "evidences": self._write_logs(),
            }
