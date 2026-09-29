import asyncio
import pytest
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from app.config import settings
from app.execution.element_locator import DRIFT_NOTE, ElementNotReadyError
from app.execution.runner import PlaywrightRunner
from app.execution.step_handlers import enum_value
from app.models.models import (
    TestRun,
    TestCase,
    Step,
    StatusEnum,
    ActionEnum,
    SelectorStrategyEnum,
)


@pytest.fixture
def mock_playwright_context():
    with patch("app.execution.runner.async_playwright") as mock_pw:
        pw_context = AsyncMock()
        mock_pw.return_value.__aenter__.return_value = pw_context

        browser = AsyncMock()
        pw_context.chromium.launch.return_value = browser

        context = AsyncMock()
        browser.new_context.return_value = context

        page = AsyncMock()
        # These are synchronous on a real Page; AsyncMock would leak coroutines.
        page.on = MagicMock()
        page.set_default_timeout = MagicMock()
        page.set_default_navigation_timeout = MagicMock()
        context.new_page.return_value = page

        yield {"pw": mock_pw, "browser": browser, "context": context, "page": page}


def test_create_run_pending():
    run = TestRun(status=StatusEnum.pending)
    assert run.status == StatusEnum.pending


@pytest.mark.asyncio
async def test_runner_success(mock_playwright_context):
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.navigate,
                selector="",
                selector_strategy=SelectorStrategyEnum.css,
                value="https://test.com/login",
            )
        ],
    )
    run = TestRun(id="test-run-1")
    runner = PlaywrightRunner(run, test_case)

    result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert result["error_message"] is None
    assert isinstance(result["finished_at"], datetime)
    assert mock_playwright_context["page"].goto.call_count == 2


@pytest.mark.asyncio
async def test_navigation_gets_a_longer_budget_than_a_step(mock_playwright_context):
    """A cold redirect can outlast the step timeout; it must not fail the run."""
    runner = PlaywrightRunner(
        TestRun(id="test-run-1"), TestCase(start_url="https://test.com", steps=[])
    )
    await runner.execute()

    page = mock_playwright_context["page"]
    page.set_default_timeout.assert_called_once_with(settings.step_timeout_ms)
    page.set_default_navigation_timeout.assert_called_once_with(
        settings.navigation_timeout_ms
    )
    assert settings.navigation_timeout_ms > settings.step_timeout_ms


@pytest.mark.parametrize(
    "mode, headless, expected",
    [
        ("on", False, True),
        ("on", True, True),
        ("auto", False, True),  # anything but "off" films
        ("", True, True),  # unset falls back to filming
        ("off", True, False),
        ("off", False, False),
    ],
)
def test_video_mode(monkeypatch, mode, headless, expected):
    monkeypatch.setattr(settings, "video", mode)
    monkeypatch.setattr(settings, "headless", headless)
    assert PlaywrightRunner._record_video() is expected


@pytest.mark.asyncio
async def test_headed_runs_are_filmed(mock_playwright_context, monkeypatch):
    """Every run gets a video, and the window is raised so it has frames in it."""
    monkeypatch.setattr(settings, "video", "on")
    monkeypatch.setattr(settings, "headless", False)
    runner = PlaywrightRunner(
        TestRun(id="test-run-1"), TestCase(start_url="https://test.com", steps=[])
    )

    await runner.execute()

    opts = mock_playwright_context["browser"].new_context.call_args.kwargs
    assert "record_video_dir" in opts
    mock_playwright_context["page"].bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_video_off_says_so(mock_playwright_context, monkeypatch):
    monkeypatch.setattr(settings, "video", "off")
    runner = PlaywrightRunner(
        TestRun(id="test-run-1"), TestCase(start_url="https://test.com", steps=[])
    )

    result = await runner.execute()

    opts = mock_playwright_context["browser"].new_context.call_args.kwargs
    assert "record_video_dir" not in opts
    assert not any(ev["type"] == "video" for ev in result["evidences"])
    console = (Path(settings.artifacts_dir) / "test-run-1" / "console.log").read_text(
        encoding="utf-8"
    )
    assert "Video disabled" in console


@pytest.mark.asyncio
async def test_a_machine_that_cannot_film_still_runs(
    mock_playwright_context, monkeypatch
):
    """No ffmpeg means no video - it must not also mean no run.

    Playwright only starts the recorder when the first page opens, so the
    failure lands well after the context was asked for.
    """
    monkeypatch.setattr(settings, "video", "on")
    context = mock_playwright_context["context"]
    page = mock_playwright_context["page"]
    context.new_page.side_effect = [
        Exception("Executable doesn't exist at ffmpeg-win64.exe"),
        page,
    ]

    runner = PlaywrightRunner(
        TestRun(id="test-run-1"), TestCase(start_url="https://test.com", steps=[])
    )
    result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    calls = mock_playwright_context["browser"].new_context.call_args_list
    assert "record_video_dir" in calls[0].kwargs
    assert "record_video_dir" not in calls[-1].kwargs
    console = (Path(settings.artifacts_dir) / "test-run-1" / "console.log").read_text(
        encoding="utf-8"
    )
    assert "Video could not be recorded" in console


@pytest.mark.asyncio
async def test_exit_criteria_run_after_every_recorded_step(mock_playwright_context):
    """An exit criterion judges the end state, so it cannot run in the middle."""
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                id="exit",
                action=ActionEnum.assert_,
                selector="h1",
                selector_strategy=SelectorStrategyEnum.css,
                assertion_type="visible",
                order_index=0,
                is_exit_criteria=True,
            ),
            Step(
                id="click",
                action=ActionEnum.click,
                selector="button",
                selector_strategy=SelectorStrategyEnum.css,
                order_index=1,
            ),
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-1"), test_case)

    assert [s.id for s in runner._ordered_steps()] == ["click", "exit"]


@pytest.mark.parametrize(
    "selector, expected",
    [
        ("li.completed > input.toggle", "completed"),
        ("ul.tabs li.active a", "active"),
        ("input.new-todo", None),
        ("", None),
        # Tailwind utilities that merely contain a state word are not state.
        ("button.group.rounded-2xl.overflow-hidden.p-4", None),
        ("div.shadow-elevation-card-hover.transition-shadow", None),
        ("button.h-\\[150px\\].focus-visible\\:ring-ring", None),
        # A prefixed state class still counts.
        ("li.is-active > a", "is-active"),
    ],
)
def test_stale_state_class_detection(selector, expected):
    step = Step(
        action=ActionEnum.click,
        selector=selector,
        selector_strategy=SelectorStrategyEnum.css,
    )
    assert PlaywrightRunner._stale_state_class(step) == expected


@pytest.mark.asyncio
async def test_failure_on_a_state_selector_says_why(mock_playwright_context):
    """A selector carrying post-click state can never match; say so plainly."""
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.check,
                selector="li.completed > div.view > input.toggle",
                selector_strategy=SelectorStrategyEnum.css,
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-2"), test_case)

    with patch(
        "app.execution.runner.registry.execute",
        side_effect=Exception("Timeout 15000ms exceeded"),
    ):
        result = await runner.execute()

    step_error = result["step_results"][0]["error_message"]
    assert "completed" in step_error and "re-record" in step_error
    assert "Timeout 15000ms exceeded" in step_error, "the raw error must survive"
    # The dashboard shows the run-level message first, so it needs it too.
    assert result["error_message"] == step_error


@pytest.mark.asyncio
async def test_failure_on_a_disabled_element_says_why(mock_playwright_context):
    """An input the app locks while it is busy is a wait problem, not a selector one."""
    raw = (
        "Locator.fill: Timeout 15000ms exceeded.\n"
        "  - waiting for element to be visible, enabled and editable\n"
        "    - element is not enabled"
    )
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="CAPA-013538",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-2"), test_case)

    with patch("app.execution.runner.registry.execute", side_effect=Exception(raw)):
        result = await runner.execute()

    step_error = result["step_results"][0]["error_message"]
    assert "switched off again" in step_error
    assert "wait step" in step_error and "ELEMENT_BUSY_TIMEOUT_MS" in step_error
    assert raw in step_error, "the raw error must survive"


@pytest.mark.asyncio
async def test_an_app_that_never_frees_the_element_is_reported_as_it_stands(
    mock_playwright_context,
):
    """The resolver already had the facts; nothing may be pinned on top of them."""
    said = (
        "The run found the answer box on screen but the app kept it switched "
        "off for the whole 180s it waited, so there was nothing to fill."
    )
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="CAPA-013538",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-6"), test_case)

    with patch(
        "app.execution.runner.registry.execute",
        side_effect=ElementNotReadyError(said),
    ) as execute:
        result = await runner.execute()

    assert result["step_results"][0]["error_message"] == said
    assert execute.call_count == 1, "waiting it out again would only repeat the wait"


@pytest.mark.asyncio
async def test_a_stuck_step_points_back_at_the_one_that_lost_its_element(
    mock_playwright_context,
):
    """A run stalls where the app is waiting, not where the mistake was made.

    The click that landed on the wrong element succeeded - clicking a div
    always does - so the report has to send the tester back to it.
    """
    said = "the app kept it switched off for the whole 180s it waited"
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                order_index=1,
                action=ActionEnum.click,
                selector="div:nth-of-type(16) > div:nth-of-type(2)",
                selector_strategy=SelectorStrategyEnum.css,
                element_meta='{"tag": "div", "name": "No"}',
            ),
            Step(
                order_index=2,
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="CAPA-013538",
            ),
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-7"), test_case)

    async def execute(step, page, scope, on_note=None, **budgets):
        if step.order_index == 1:
            on_note(f"css=... {DRIFT_NOTE} 'No'; the step acted on that match anyway")
            return
        raise ElementNotReadyError(said)

    with patch("app.execution.runner.registry.execute", side_effect=execute):
        result = await runner.execute()

    step_error = result["step_results"][1]["error_message"]
    assert said in step_error, "the resolver's own account is kept"
    assert "step #1" in step_error and "'No'" in step_error


@pytest.mark.asyncio
async def test_a_step_that_could_not_act_is_tried_again(mock_playwright_context):
    """The app was still busy the first time; a second go is all it needed."""
    busy = Exception(
        "Locator.fill: Timeout 15000ms exceeded.\n"
        "  - waiting for element to be visible, enabled and editable\n"
        "    - element is not enabled"
    )
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="CAPA-013538",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-2"), test_case)

    with patch(
        "app.execution.runner.registry.execute", side_effect=[busy, None]
    ) as execute:
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert execute.call_count == 2, "the element was looked up and acted on afresh"
    assert any("RETRY" in line for line in runner.console_lines)
    # The app is given a chance to finish whatever locked the input.
    mock_playwright_context["page"].wait_for_load_state.assert_awaited()


@pytest.mark.asyncio
async def test_a_check_that_did_not_hold_is_not_tried_again(mock_playwright_context):
    """A failed assertion is a result. Repeating it only delays the report."""
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.assert_,
                selector="#total",
                selector_strategy=SelectorStrategyEnum.css,
                assertion_type="text_equals",
                expected_value="42",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-2"), test_case)

    with patch(
        "app.execution.runner.registry.execute",
        side_effect=AssertionError("Expected '42' but found '41'"),
    ) as execute:
        result = await runner.execute()

    assert result["status"] == StatusEnum.failed
    assert execute.call_count == 1


@pytest.mark.asyncio
async def test_failure_on_a_moving_element_says_why(mock_playwright_context):
    """An animating or re-rendered element is a timing problem, not a selector one."""
    raw = (
        "Locator.click: Timeout 15000ms exceeded.\n"
        "  - waiting for element to be visible and stable\n"
        "    - element is not stable\n"
        "  - element was detached from the DOM, retrying"
    )
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.click,
                selector="button.group.overflow-hidden.rounded-2xl",
                selector_strategy=SelectorStrategyEnum.css,
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-2"), test_case)

    with patch("app.execution.runner.registry.execute", side_effect=Exception(raw)):
        result = await runner.execute()

    step_error = result["step_results"][0]["error_message"]
    assert "kept moving" in step_error
    # The styling classes are not state, so they must not be blamed for this.
    assert "overflow-hidden" not in step_error.split(raw)[0]
    assert raw in step_error, "the raw error must survive"


@pytest.mark.asyncio
async def test_a_hover_that_finds_nothing_does_not_end_the_run(mock_playwright_context):
    """A hover reveals; it decides nothing.

    The dialog a tester happened to be over is often not open on the next run,
    and the click that follows hovers on its own anyway.
    """
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.hover,
                selector='div[role="dialog"] > div:nth-of-type(1)',
                selector_strategy=SelectorStrategyEnum.css,
                order_index=0,
            ),
            Step(
                action=ActionEnum.click,
                selector='button[aria-label="CAPA"]',
                selector_strategy=SelectorStrategyEnum.css,
                order_index=1,
            ),
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-hover"), test_case)

    async def only_the_hover_fails(step, *args, **kwargs):
        if enum_value(step.action) == ActionEnum.hover.value:
            raise Exception("Locator.hover: Timeout 3000ms exceeded.\n  - waiting")

    with patch(
        "app.execution.runner.registry.execute", side_effect=only_the_hover_fails
    ):
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert [s["status"] for s in result["step_results"]] == [
        StatusEnum.passed,
        StatusEnum.passed,
    ], "the click after the hover must still run"
    assert any("SKIPPED" in line for line in runner.console_lines)


@pytest.mark.asyncio
async def test_a_click_that_finds_nothing_still_ends_the_run(mock_playwright_context):
    """Only gestures are forgiven. A click is what the test came to do."""
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.click,
                selector="button.missing",
                selector_strategy=SelectorStrategyEnum.css,
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-click"), test_case)

    with patch(
        "app.execution.runner.registry.execute",
        side_effect=Exception("Locator.click: Timeout exceeded"),
    ):
        result = await runner.execute()

    assert result["status"] == StatusEnum.failed


def _skip_button(still_offered):
    """A button that answers whether it is still there, and the locator for it."""
    element = MagicMock()
    element.evaluate = AsyncMock(side_effect=lambda _expr: still_offered())
    locator = MagicMock()
    locator.element_handle = AsyncMock(return_value=element)
    return locator


@pytest.mark.asyncio
async def test_a_repeated_step_waits_for_the_app_to_answer_the_one_before(
    mock_playwright_context,
):
    """Four Skips are four questions, not four presses of one button.

    Fired back to back, the second lands on the button the first already
    pressed - the browser reports a good click and two of the four are lost.
    """
    looks = {"count": 0}

    def still_offered():
        looks["count"] += 1
        # The app takes a moment to take the button away and draw the next.
        return looks["count"] < 3

    locator = _skip_button(still_offered)
    acted_at: list[int] = []

    async def execute(step, *args, **kwargs):
        acted_at.append(looks["count"])
        return locator

    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.click,
                selector="Skip",
                selector_strategy=SelectorStrategyEnum.text,
                order_index=i,
            )
            for i in range(2)
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-repeat"), test_case)

    with patch("app.execution.runner.registry.execute", side_effect=execute):
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert acted_at == [0, 3], "the repeat must wait until the button is gone"


@pytest.mark.asyncio
async def test_a_step_on_a_different_element_does_not_wait(mock_playwright_context):
    """Only a repeat needs the pause; the run must not stop between steps."""
    looks = {"count": 0}

    def still_offered():
        looks["count"] += 1
        return True

    locator = _skip_button(still_offered)

    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.click,
                selector="Skip",
                selector_strategy=SelectorStrategyEnum.text,
                order_index=0,
            ),
            Step(
                action=ActionEnum.click,
                selector="Next",
                selector_strategy=SelectorStrategyEnum.text,
                order_index=1,
            ),
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-no-repeat"), test_case)

    with patch("app.execution.runner.registry.execute", return_value=locator):
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert looks["count"] == 0


@pytest.mark.asyncio
async def test_a_step_waits_for_the_page_to_stop_changing(mock_playwright_context):
    """Typing must not start while the app is still redrawing.

    The box for the next question is on screen before that question is, so a
    run that types the moment it finds one answers the wrong question and
    carries on as though it had not.
    """
    readings = iter([0, 120])
    page = mock_playwright_context["page"]
    page.evaluate = AsyncMock(side_effect=lambda _probe: next(readings, 900))

    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="ok",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-quiet"), test_case)

    with patch("app.execution.runner.registry.execute", new=AsyncMock()) as execute:
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert execute.await_count == 1
    assert page.evaluate.await_count == 3, "it must look again after each pause"


@pytest.mark.asyncio
async def test_a_step_waits_for_the_reply_the_step_before_asked_for(
    mock_playwright_context,
):
    """A page sits perfectly still between a click and the answer to it."""
    page = mock_playwright_context["page"]
    page.evaluate = AsyncMock(return_value=5000)

    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.fill,
                selector="textarea#message",
                selector_strategy=SelectorStrategyEnum.css,
                value="ok",
            )
        ],
    )
    runner = PlaywrightRunner(TestRun(id="test-run-inflight"), test_case)
    request = object()
    runner._in_flight[request] = time.monotonic()
    asyncio.get_running_loop().call_later(
        0.4, lambda: runner._in_flight.pop(request, None)
    )

    started = time.monotonic()
    with patch("app.execution.runner.registry.execute", new=AsyncMock()):
        result = await runner.execute()

    assert result["status"] == StatusEnum.passed
    assert time.monotonic() - started >= 0.4, "the step went before the reply landed"


@pytest.mark.asyncio
async def test_runner_failure(mock_playwright_context):
    test_case = TestCase(
        start_url="https://test.com",
        steps=[
            Step(
                action=ActionEnum.click,
                selector="invalid-selector",
                selector_strategy=SelectorStrategyEnum.css,
            )
        ],
    )
    run = TestRun(id="test-run-2")
    runner = PlaywrightRunner(run, test_case)

    with patch(
        "app.execution.runner.registry.execute",
        side_effect=Exception("Timeout waiting for element"),
    ):
        result = await runner.execute()

    assert result["status"] == StatusEnum.failed
    assert "Timeout waiting for element" in result["error_message"]
    assert isinstance(result["finished_at"], datetime)

    assert mock_playwright_context["page"].screenshot.call_count >= 1
