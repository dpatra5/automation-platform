"""End-to-end check of the recorder: dashboard -> extension -> backend -> replay.

Loads the real unpacked extension into Chromium, starts a recording from the
dashboard, drives a flow, stops it from the floating island, and then replays
the test case the extension created.

Needs the backend on :8000, the frontend dev server on :5173, and a built
extension in extension/dist:

    cd extension && npm run build
    cd backend   && uvicorn app.main:app --reload --port 8000
    cd frontend  && npm run dev
    cd backend   && python -m scripts.smoke_extension

Set REWIND_DASHBOARD if Vite fell back to another port (it must still be one
the extension trusts - see DASHBOARD_ORIGINS in the extension source).
"""
import asyncio
import inspect
import os
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

API = "http://localhost:8000/api/v1"
DASHBOARD = os.environ.get("REWIND_DASHBOARD", "http://localhost:5173")
TARGET_APP = "https://demo.playwright.dev/todomvc/#/"
EXTENSION = Path(__file__).resolve().parents[2] / "extension" / "dist"

# Recording is asynchronous end to end (content script -> service worker ->
# backend), so every wait here is a poll with a ceiling, never a fixed sleep.
TIMEOUT_MS = 20_000


async def wait_for(check, what: str, timeout_ms: int = TIMEOUT_MS):
    """Poll `check` (sync or async) until it returns something truthy."""
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        result = check()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return result
        await asyncio.sleep(0.4)
    raise AssertionError(f"Timed out waiting for {what}")


async def require_services() -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in (("backend", "http://localhost:8000/health"), ("frontend", DASHBOARD)):
            try:
                (await client.get(url)).raise_for_status()
            except Exception as e:
                raise SystemExit(f"{name} is not reachable at {url} ({e})")
    if not (EXTENSION / "manifest.json").exists():
        raise SystemExit(f"No built extension at {EXTENSION}. Run `npm run build` in extension/.")


async def create_project(client: httpx.AsyncClient) -> str:
    res = await client.post(f"{API}/projects", json={
        "name": "Extension smoke",
        "base_url": TARGET_APP,
        "description": "Created by scripts/smoke_extension.py",
    })
    res.raise_for_status()
    return res.json()["id"]


async def main() -> None:
    await require_services()
    profile_dir = Path(tempfile.mkdtemp(prefix="rewind-ext-"))

    async with httpx.AsyncClient(timeout=20) as client:
        project_id = await create_project(client)

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,  # MV3 service workers do not run headless.
                args=[
                    f"--disable-extensions-except={EXTENSION}",
                    f"--load-extension={EXTENSION}",
                ],
            )
            try:
                dashboard = await context.new_page()
                await dashboard.goto(f"{DASHBOARD}/projects/{project_id}")

                # The dashboard pings the extension through the content script;
                # if that relay is missing, recording silently does nothing.
                await dashboard.get_by_text("Extension connected").wait_for(timeout=TIMEOUT_MS)
                print("dashboard sees the extension")

                await dashboard.get_by_role("button", name="Record new test").click()

                app = await wait_for(
                    lambda: next(
                        (pg for pg in context.pages if urlparse(pg.url).netloc == "demo.playwright.dev"),
                        None,
                    ),
                    "the app tab to open",
                )
                await app.wait_for_load_state("domcontentloaded")

                island = app.locator("#rewind-recorder-island")
                await island.wait_for(state="attached", timeout=TIMEOUT_MS)
                print("island mounted")

                # The service worker also injects content.js into tabs that were
                # already open when the extension loaded. Drive that same path
                # here: a tab that receives both copies must not record twice.
                await reinject_via_service_worker(context)

                # A flow that exercises fill, key press and a checkbox toggle.
                await app.fill(".new-todo", "recorded by the extension")
                await app.press(".new-todo", "Enter")
                await app.click(".todo-list li:nth-child(1) .toggle")

                await wait_for(lambda: _steps_shown(island), "steps to register on the island")
                shown = await island.locator(".count").inner_text()
                print(f"island reports {shown}")

                await island.locator('[data-rewind="stop"]').click()

                test_cases = await wait_for(
                    lambda: _fetch_test_cases(client, project_id),
                    "the recording to reach the backend",
                )
            finally:
                await context.close()
                shutil.rmtree(profile_dir, ignore_errors=True)

        test_case = test_cases[0]
        actions = [s["action"] for s in test_case["steps"]]
        print(f"recorded {len(actions)} steps: {actions}")
        assert "fill" in actions, f"typing was not recorded: {actions}"
        assert "press_key" in actions, f"Enter was not recorded: {actions}"
        assert "check" in actions, f"the checkbox was not recorded: {actions}"
        assert actions == ["fill", "press_key", "check"], (
            f"expected exactly one step per action, got {actions} - a second copy "
            "of the content script is recording duplicates"
        )

        # TodoMVC marks the row `completed` the instant the box is ticked. If that
        # class reaches the selector, the step can only ever match after the click
        # it is meant to perform, so the recording is unreplayable.
        check_selector = next(s["selector"] for s in test_case["steps"] if s["action"] == "check")
        print(f"check selector: {check_selector}")
        assert "completed" not in check_selector, (
            f"selector captured post-click state: {check_selector}"
        )

        # The recording must be replayable, which is the whole point of it.
        run = (await client.post(f"{API}/test-cases/{test_case['id']}/run")).json()
        final = await wait_for(
            lambda: _finished_run(client, run["id"]), "the replay to finish", timeout_ms=120_000
        )
        print(f"replay finished: {final['status']} ({len(final['step_results'])} steps)")
        assert final["status"] == "passed", final.get("error_message")

    print("OK - record in Chrome, save to the backend, replay it")


async def reinject_via_service_worker(context) -> None:
    """Run the extension's own `chrome.scripting.executeScript` a second time.

    This is the code path that rescues tabs which were already open when the
    extension loaded, so it is also the path that could double up listeners.
    """
    worker = context.service_workers[0] if context.service_workers else await context.wait_for_event("serviceworker")
    injected = await worker.evaluate("""async () => {
        const tabs = await chrome.tabs.query({ url: 'https://demo.playwright.dev/*' });
        for (const tab of tabs) {
            await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
        }
        return tabs.length;
    }""")
    print(f"re-injected content script into {injected} tab(s)")


async def _steps_shown(island) -> bool:
    text = await island.locator(".count").inner_text()
    return not text.startswith("0")


async def _fetch_test_cases(client: httpx.AsyncClient, project_id: str):
    res = await client.get(f"{API}/projects/{project_id}/test-cases")
    cases = res.json() if res.status_code == 200 else []
    return cases if cases and cases[0].get("steps") else None


async def _finished_run(client: httpx.AsyncClient, run_id: str):
    run = (await client.get(f"{API}/runs/{run_id}")).json()
    return run if run["status"] not in ("running", "pending") else None


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.ProactorEventLoop)
    else:
        asyncio.run(main())
