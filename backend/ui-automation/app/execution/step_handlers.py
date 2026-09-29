from typing import Any, Callable, Dict, Optional
from playwright.async_api import Page
from app.execution import assertions
from app.execution.element_locator import enum_value, resolve
from app.models.models import Step, ActionEnum, SelectorStrategyEnum


class MissingSelectorError(ValueError):
    """Raised when an action needs an element but the step has no selector."""


class StepHandlerRegistry:
    """Registry pattern for Playwright step handlers."""

    def __init__(self):
        self.handlers: Dict[str, Callable] = {}

    def register(self, action: ActionEnum):
        """Decorator to register a handler for an action."""

        def decorator(func: Callable):
            self.handlers[action.value] = func
            return func

        return decorator

    async def execute(
        self,
        step: Step,
        page: Page,
        scope: Any = None,
        on_note: Optional[Callable[[str], None]] = None,
        ready_budget_s: Optional[float] = None,
        busy_budget_s: Optional[float] = None,
    ) -> Any:
        """Execute a step, and report the element it acted on.

        `scope` is where the element is looked for - the page itself, or the
        iframe the step was recorded in. Handlers always receive the page, so
        page-level operations (navigation, keyboard, URL waits) keep working
        even for a step that acts inside a frame.

        `on_note` is called when the element had to be found some way other
        than the recorded selector, so the run's evidence says how.

        `ready_budget_s` caps how long an element that cannot be found is
        waited for, and `busy_budget_s` how long one the app has switched off
        is waited for, so the runner can split a step's time across retries.

        The element comes back so the runner can tell whether a step repeated
        straight after this one is about to press the very same button again.
        """
        handler = self.handlers.get(enum_value(step.action))
        if not handler:
            raise ValueError(f"No handler registered for action: {step.action}")
        locator = await resolve(
            step,
            scope or page,
            on_note=on_note,
            budget_s=ready_budget_s,
            busy_budget_s=busy_budget_s,
        )
        await handler(step, page, locator)
        return locator

    @staticmethod
    def resolve_locator(step: Step, scope: Any):
        """Build a locator from the recorded selector alone.

        The strict reading of what was recorded, with none of the fallbacks
        `app.execution.element_locator` adds. Used where the question really is
        about that selector - counting its matches, or drag's second element.

        `scope` is a Page or a Frame; both expose the same locator API.
        """
        if not step.selector:
            return None
        strategy = enum_value(step.selector_strategy)
        if strategy == SelectorStrategyEnum.test_id.value:
            return scope.get_by_test_id(step.selector)
        if strategy == SelectorStrategyEnum.role.value:
            return scope.get_by_role(step.selector)
        if strategy == SelectorStrategyEnum.text.value:
            return scope.get_by_text(step.selector)
        if strategy == SelectorStrategyEnum.xpath.value:
            return scope.locator(f"xpath={step.selector}")
        return scope.locator(step.selector)


registry = StepHandlerRegistry()

# A hover only reveals things - a menu, a tooltip, a row's buttons. Waiting a
# quarter of a minute for one is time spent on a gesture nobody is checking.
GESTURE_TIMEOUT_MS = 3000


def _require(locator: Any, step: Step):
    """The element a step acts on.

    Already narrowed to one match by `app.execution.element_locator`, which
    chooses between several by what the recorder noted about the element. This
    only enforces that the step had a selector at all.
    """
    if locator is None:
        raise MissingSelectorError(f"Action '{step.action}' needs a selector")
    return locator


# ---------------------------------------------------------------- navigation


@registry.register(ActionEnum.navigate)
async def handle_navigate(step: Step, page: Page, locator: Any) -> None:
    await page.goto(step.value)


@registry.register(ActionEnum.reload)
async def handle_reload(step: Step, page: Page, locator: Any) -> None:
    await page.reload()


@registry.register(ActionEnum.go_back)
async def handle_go_back(step: Step, page: Page, locator: Any) -> None:
    await page.go_back()


@registry.register(ActionEnum.go_forward)
async def handle_go_forward(step: Step, page: Page, locator: Any) -> None:
    await page.go_forward()


# ------------------------------------------------------------------- pointer


@registry.register(ActionEnum.click)
async def handle_click(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).click()


@registry.register(ActionEnum.dblclick)
async def handle_dblclick(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).dblclick()


@registry.register(ActionEnum.right_click)
async def handle_right_click(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).click(button="right")


@registry.register(ActionEnum.hover)
async def handle_hover(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).hover(timeout=GESTURE_TIMEOUT_MS)


@registry.register(ActionEnum.drag)
async def handle_drag(step: Step, page: Page, locator: Any) -> None:
    """`value` holds the drop target selector (same strategy as the source)."""
    target = StepHandlerRegistry.resolve_locator(
        Step(selector=step.value, selector_strategy=step.selector_strategy), page
    )
    # The drop target is the recorded selector as it stands, with none of the
    # resolver's narrowing behind it.
    await _require(locator, step).drag_to(_require(target, step).first)


@registry.register(ActionEnum.scroll)
async def handle_scroll(step: Step, page: Page, locator: Any) -> None:
    """Scroll a container to "x,y", an element into view, or the window itself.

    A regression often only shows up below the fold or inside a scrollable
    panel, so the resting position of both the window and any container is
    replayed rather than assumed.
    """
    offset = _offset(step.value)
    if locator is not None:
        if offset is None:
            await _require(locator, step).scroll_into_view_if_needed(
                timeout=GESTURE_TIMEOUT_MS
            )
        else:
            await _require(locator, step).evaluate(
                "(el, [x, y]) => el.scrollTo(x, y)",
                list(offset),
                timeout=GESTURE_TIMEOUT_MS,
            )
        return
    x, y = offset or (0, 0)
    await page.evaluate("([x, y]) => window.scrollTo(x, y)", [x, y])


def _offset(value: str | None) -> tuple[int, int] | None:
    """Parse an "x,y" scroll offset; None when the step carries no position."""
    x, sep, y = (value or "").partition(",")
    if not sep:
        return None
    try:
        return int(float(x or 0)), int(float(y or 0))
    except ValueError:
        return None


# --------------------------------------------------------------------- input


@registry.register(ActionEnum.fill)
async def handle_fill(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).fill(step.value or "")


@registry.register(ActionEnum.type)
async def handle_type(step: Step, page: Page, locator: Any) -> None:
    """Key-by-key entry, for inputs that react to each keystroke."""
    await _require(locator, step).press_sequentially(step.value or "", delay=40)


@registry.register(ActionEnum.press_key)
async def handle_press_key(step: Step, page: Page, locator: Any) -> None:
    # Target the element when the recording captured one, so the key lands on
    # the right field even if focus moved between steps.
    if locator is not None:
        await _require(locator, step).press(step.value)
    else:
        await page.keyboard.press(step.value)


@registry.register(ActionEnum.select)
async def handle_select(step: Step, page: Page, locator: Any) -> None:
    """One option value, or several separated by "||" for a multi-select."""
    raw = step.value or ""
    await _require(locator, step).select_option(raw.split("||") if "||" in raw else raw)


@registry.register(ActionEnum.check)
async def handle_check(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).check()


@registry.register(ActionEnum.uncheck)
async def handle_uncheck(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).uncheck()


@registry.register(ActionEnum.upload)
async def handle_upload(step: Step, page: Page, locator: Any) -> None:
    """`value` is a comma-separated list of paths readable by the runner."""
    paths = [p.strip() for p in (step.value or "").split(",") if p.strip()]
    await _require(locator, step).set_input_files(paths)


# ----------------------------------------------------------- synchronisation


@registry.register(ActionEnum.wait)
async def handle_wait(step: Step, page: Page, locator: Any) -> None:
    await page.wait_for_timeout(int(step.value))


@registry.register(ActionEnum.wait_for_selector)
async def handle_wait_for_selector(step: Step, page: Page, locator: Any) -> None:
    await _require(locator, step).wait_for(state="visible")


@registry.register(ActionEnum.wait_for_url)
async def handle_wait_for_url(step: Step, page: Page, locator: Any) -> None:
    """Used after a login redirect: block until the app URL comes back."""
    await page.wait_for_url(step.value)


@registry.register(ActionEnum.switch_tab)
async def handle_switch_tab(step: Step, page: Page, locator: Any) -> None:
    """Moving between tabs is the runner's job, not a page operation.

    It has to change which page every later step acts on, which needs the
    browser context. Registered so the action is never silently unhandled.
    """
    raise RuntimeError(
        "A switch tab step can only be replayed by the runner, which owns the "
        "browser context and decides which tab the rest of the run drives."
    )


# -------------------------------------------------------------- verification


@registry.register(ActionEnum.assert_)
async def handle_assert(step: Step, page: Page, locator: Any) -> None:
    """Every check lives in app.execution.assertions, which the GUIs mirror."""
    await assertions.run_assertion(step, page, locator)
