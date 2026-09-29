"""The script view of a recorded test case.

A recording is stored as a list of steps, and that is what the runner replays.
This module renders those steps as Playwright-flavoured Python and reads the
same text back, so the editor on the test case page is not a picture of the
test but the test itself: every line maps to exactly one step, each block is
labelled with the step it belongs to, and saving rewrites the steps.

The round trip is the whole point. Anything the parser cannot place is
reported by line number rather than dropped, because a script editor that
quietly discards a step is worse than no script editor at all.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Optional

from app.exceptions import RewindError
from app.models.models import ActionEnum, SelectorStrategyEnum

#: The function holding the checks that run after the flow, whatever their
#: position in the list. Its name is what tells the parser they are checks.
EXIT_FUNCTION = "exit_checks"

#: Everything before this is the flow itself.
FLOW_FUNCTION_PREFIX = "test_"


class ScriptError(RewindError):
    """The script could not be read back as steps. Reported with a line number."""


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value)


# --------------------------------------------------------------- rendering

_LOCATOR_METHOD = {
    SelectorStrategyEnum.test_id.value: "get_by_test_id",
    SelectorStrategyEnum.role.value: "get_by_role",
    SelectorStrategyEnum.text.value: "get_by_text",
}
_STRATEGY_BY_METHOD = {method: key for key, method in _LOCATOR_METHOD.items()}

#: Element methods, and the action each one replays as.
_ELEMENT_METHODS = {
    "click": ActionEnum.click.value,
    "dblclick": ActionEnum.dblclick.value,
    "hover": ActionEnum.hover.value,
    "fill": ActionEnum.fill.value,
    "type": ActionEnum.type.value,
    "press": ActionEnum.press_key.value,
    "select_option": ActionEnum.select.value,
    "check": ActionEnum.check.value,
    "uncheck": ActionEnum.uncheck.value,
    "set_input_files": ActionEnum.upload.value,
    "wait_for": ActionEnum.wait_for_selector.value,
    "drag_to": ActionEnum.drag.value,
    "scroll_to": ActionEnum.scroll.value,
    "scroll_into_view": ActionEnum.scroll.value,
}

#: Page methods, for the steps that drive the browser rather than an element.
_PAGE_METHODS = {
    "goto": ActionEnum.navigate.value,
    "reload": ActionEnum.reload.value,
    "go_back": ActionEnum.go_back.value,
    "go_forward": ActionEnum.go_forward.value,
    "wait_for_timeout": ActionEnum.wait.value,
    "wait_for_url": ActionEnum.wait_for_url.value,
    "scroll_to": ActionEnum.scroll.value,
}

#: Methods whose single argument is the step's value.
_TAKES_VALUE = {
    "goto",
    "wait_for_timeout",
    "wait_for_url",
    "scroll_to",
    "fill",
    "type",
    "press",
    "select_option",
    "set_input_files",
}

HEADER = """\
# Rewind script for {name!r}
#
# This is the recorded test, written out as Playwright-style Python. Every
# call below is one step, in the order the runner replays it, and each block
# is labelled with the step number the dashboard shows.
#
# Editing a line and pressing Save rewrites the steps behind it, so this is a
# real editor rather than a preview. Anything outside the shapes below cannot
# be turned back into a step and is reported instead of being dropped.
#
#   page.goto(url)                     open a URL
#   page.locator("xpath=...")          the element a step acts on
#   frame("<iframe url>")              same, for an element inside an iframe
#   check(<element>, "<check>", ...)   an assertion from Rewind's catalogue
#
# Selectors are recorded as XPath. Paste one into the browser console with
# $x("...") to see exactly what it picks out.
"""


def _lit(value: Any) -> str:
    """A Python literal for a recorded value."""
    if value is None:
        return "None"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _identifier(name: str) -> str:
    """A valid Python function name built from the test case's name."""
    cleaned = re.sub(r"\W+", "_", (name or "").strip().lower()).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"case_{cleaned}" if cleaned else "case"
    return f"{FLOW_FUNCTION_PREFIX}{cleaned}"[:80]


def _scope_expr(frame_url: Optional[str]) -> str:
    return f"frame({_lit(frame_url)})" if frame_url else "page"


def _target_expr(step) -> str:
    """The locator expression for the element a step acts on."""
    scope = _scope_expr(getattr(step, "frame_url", None))
    strategy = _enum_value(step.selector_strategy) or SelectorStrategyEnum.css.value
    selector = step.selector or ""
    method = _LOCATOR_METHOD.get(strategy)
    if method:
        return f"{scope}.{method}({_lit(selector)})"
    if strategy == SelectorStrategyEnum.xpath.value:
        return f"{scope}.locator({_lit('xpath=' + selector)})"
    return f"{scope}.locator({_lit(selector)})"


def _drop_target_expr(step) -> str:
    """A drag's second element, described the same way as its first."""
    scope = _scope_expr(getattr(step, "frame_url", None))
    strategy = _enum_value(step.selector_strategy)
    value = step.value or ""
    method = _LOCATOR_METHOD.get(strategy)
    if method:
        return f"{scope}.{method}({_lit(value)})"
    if strategy == SelectorStrategyEnum.xpath.value:
        return f"{scope}.locator({_lit('xpath=' + value)})"
    return f"{scope}.locator({_lit(value)})"


def _check_expr(step) -> str:
    """`check(...)`, the one shape every assertion in the catalogue takes."""
    subject = _target_expr(step) if step.selector else _scope_expr(step.frame_url)
    parts = [subject, _lit(step.assertion_type or "")]
    if step.expected_value is not None:
        parts.append(_lit(step.expected_value))
    if step.value:
        parts.append(f"detail={_lit(step.value)}")
    return f"check({', '.join(parts)})"


_SIMPLE_PAGE_CALL = {
    ActionEnum.reload.value: "page.reload()",
    ActionEnum.go_back.value: "page.go_back()",
    ActionEnum.go_forward.value: "page.go_forward()",
}


def _browser_call(action: str, step) -> Optional[str]:
    """The line for a step that drives the browser rather than an element."""
    value = step.value
    if action in _SIMPLE_PAGE_CALL:
        return _SIMPLE_PAGE_CALL[action]
    if action == ActionEnum.assert_.value:
        return _check_expr(step)
    if action == ActionEnum.switch_tab.value:
        return f"switch_tab({_lit(value)})"
    if action == ActionEnum.navigate.value:
        return f"page.goto({_lit(value)})"
    if action == ActionEnum.wait.value:
        return f"page.wait_for_timeout({_lit(_as_int(value))})"
    if action == ActionEnum.wait_for_url.value:
        return f"page.wait_for_url({_lit(value)})"
    if step.selector:
        return None
    # Both of these also exist as element steps; without a selector they are
    # the keyboard and the window rather than something on the page.
    if action == ActionEnum.press_key.value:
        return f"page.keyboard.press({_lit(value)})"
    if action == ActionEnum.scroll.value:
        return f"page.scroll_to({_lit(value)})"
    return None


def _call_for(step) -> str:
    """The one line of Python that replays this step."""
    action = _enum_value(step.action)
    browser = _browser_call(action, step)
    if browser is not None:
        return browser

    if action == ActionEnum.right_click.value:
        return f'{_target_expr(step)}.click(button="right")'
    if action == ActionEnum.drag.value:
        return f"{_target_expr(step)}.drag_to({_drop_target_expr(step)})"
    if action == ActionEnum.scroll.value:
        if step.value is None:
            return f"{_target_expr(step)}.scroll_into_view()"
        return f"{_target_expr(step)}.scroll_to({_lit(step.value)})"

    method = next(
        (name for name, mapped in _ELEMENT_METHODS.items() if mapped == action), None
    )
    if method is None:
        raise ScriptError(f"No script form for the action {action!r}.")
    argument = _lit(step.value) if method in _TAKES_VALUE else ""
    return f"{_target_expr(step)}.{method}({argument})"


def _as_int(value: Any) -> Any:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return value


def _label(step, position: int, is_exit: bool) -> list[str]:
    """The comment block that ties a line of script to a step in the editor."""
    action = _enum_value(step.action)
    kind = "Exit check" if is_exit else "Step"
    said = step.assertion_type if action == ActionEnum.assert_.value else action
    lines = [f"# {kind} {position} - {said}"]

    name = _element_name(step)
    if name:
        lines.append(f"# on: {name}")
    if step.selector:
        lines.append(f"# {_enum_value(step.selector_strategy)}: {step.selector}")
    if getattr(step, "frame_url", None):
        lines.append(f"# inside iframe: {step.frame_url}")
    return lines


def _element_name(step) -> str:
    """What the recorder called the element, for the block's comment."""
    raw = getattr(step, "element_meta", None)
    if not raw:
        return ""
    try:
        meta = raw if isinstance(raw, dict) else json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("name") or meta.get("text") or "").strip()[:80]


def _body(steps: list, is_exit: bool) -> list[str]:
    lines: list[str] = []
    for position, step in enumerate(steps, start=1):
        if lines:
            lines.append("")
        lines.extend(f"    {line}" for line in _label(step, position, is_exit))
        lines.append(f"    {_call_for(step)}")
    if not lines:
        lines.append("    pass")
    return lines


def render_script(test_case) -> str:
    """The whole test case as an editable script."""
    steps = list(test_case.steps or [])
    flow = [s for s in steps if not s.is_exit_criteria]
    criteria = [s for s in steps if s.is_exit_criteria]

    lines = [HEADER.format(name=test_case.name), ""]
    lines.append(f"def {_identifier(test_case.name)}():")
    if test_case.start_url:
        lines.append(f"    # Recorded from {test_case.start_url}")
    lines.extend(_body(flow, is_exit=False))
    lines.extend(["", "", f"def {EXIT_FUNCTION}():"])
    lines.append("    # Checked once the flow above has finished.")
    lines.extend(_body(criteria, is_exit=True))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------- parsing


def _fail(node: ast.AST, message: str) -> "ScriptError":
    return ScriptError(f"Line {getattr(node, 'lineno', 0)}: {message}")


def _literal(node: ast.AST) -> Any:
    """A constant argument, or a clear complaint about why it is not one."""
    if isinstance(node, ast.Constant) and (
        node.value is None or isinstance(node.value, (str, int, float))
    ):
        return node.value
    raise _fail(node, "expected a plain string or number here.")


def _text(node: ast.AST) -> str:
    value = _literal(node)
    return "" if value is None else str(value)


def _frame_of(node: ast.AST) -> tuple[bool, Optional[str]]:
    """Whether this expression is a scope, and which frame it names."""
    if isinstance(node, ast.Name) and node.id == "page":
        return True, None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frame"
        and len(node.args) == 1
    ):
        return True, _text(node.args[0]) or None
    return False, None


def _target_of(node: ast.AST) -> Optional[dict]:
    """The selector, strategy and frame a locator expression describes."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    is_scope, frame_url = _frame_of(node.func.value)
    if not is_scope or len(node.args) != 1:
        return None

    method = node.func.attr
    if method in _STRATEGY_BY_METHOD:
        return {
            "selector": _text(node.args[0]),
            "selector_strategy": _STRATEGY_BY_METHOD[method],
            "frame_url": frame_url,
        }
    if method != "locator":
        return None
    raw = _text(node.args[0])
    if raw.startswith("xpath="):
        return {
            "selector": raw[len("xpath=") :],
            "selector_strategy": SelectorStrategyEnum.xpath.value,
            "frame_url": frame_url,
        }
    return {
        "selector": raw,
        "selector_strategy": SelectorStrategyEnum.css.value,
        "frame_url": frame_url,
    }


def _blank_step(action: str) -> dict:
    return {
        "action": action,
        "selector": "",
        "selector_strategy": SelectorStrategyEnum.xpath.value,
        "value": None,
        "assertion_type": None,
        "expected_value": None,
        "frame_url": None,
    }


def _keyword(call: ast.Call, name: str) -> Any:
    for keyword in call.keywords:
        if keyword.arg == name:
            return _literal(keyword.value)
    return None


def _check_step(call: ast.Call) -> dict:
    """`check(<element or page>, "<key>", "<expected>", detail="...")`."""
    if len(call.args) < 2:
        raise _fail(call, "check() needs the element and the name of the check.")
    step = _blank_step(ActionEnum.assert_.value)
    is_scope, frame_url = _frame_of(call.args[0])
    if is_scope:
        step["frame_url"] = frame_url
    else:
        target = _target_of(call.args[0])
        if target is None:
            raise _fail(call, "check() needs page or a locator as its first argument.")
        step.update(target)
    step["assertion_type"] = _text(call.args[1])
    if len(call.args) > 2:
        step["expected_value"] = _text(call.args[2])
    detail = _keyword(call, "detail")
    if detail is not None:
        step["value"] = str(detail)
    return step


def _page_step(method: str, call: ast.Call, frame_url: Optional[str]) -> dict:
    action = _PAGE_METHODS[method]
    step = _blank_step(action)
    step["frame_url"] = frame_url
    if method in _TAKES_VALUE:
        if not call.args:
            raise _fail(call, f"{method}() needs a value.")
        step["value"] = _text(call.args[0])
    return step


def _element_step(method: str, call: ast.Call, target: dict) -> dict:
    action = _ELEMENT_METHODS[method]
    if method == "click" and _keyword(call, "button") == "right":
        action = ActionEnum.right_click.value
    step = _blank_step(action)
    step.update(target)

    if method == "drag_to":
        if not call.args:
            raise _fail(call, "drag_to() needs the element to drop onto.")
        drop = _target_of(call.args[0])
        if drop is None:
            raise _fail(call, "drag_to() needs a locator as its argument.")
        if drop["selector_strategy"] != step["selector_strategy"]:
            raise _fail(
                call,
                "a drag's two elements have to be described the same way; "
                f"found {step['selector_strategy']} and {drop['selector_strategy']}.",
            )
        step["value"] = drop["selector"]
        return step

    if method in _TAKES_VALUE:
        if not call.args:
            raise _fail(call, f"{method}() needs a value.")
        step["value"] = _text(call.args[0])
    return step


def _keyboard_step(call: ast.Call) -> dict:
    step = _blank_step(ActionEnum.press_key.value)
    if not call.args:
        raise _fail(call, "keyboard.press() needs a key.")
    step["value"] = _text(call.args[0])
    return step


def _named_call(call: ast.Call, name: str) -> dict:
    if name == "check":
        return _check_step(call)
    if name == "switch_tab":
        step = _blank_step(ActionEnum.switch_tab.value)
        if not call.args:
            raise _fail(call, "switch_tab() needs the URL of the tab.")
        step["value"] = _text(call.args[0])
        return step
    raise _fail(call, f"{name}() is not one of Rewind's step calls.")


def _step_from_call(call: ast.Call) -> dict:
    if isinstance(call.func, ast.Name):
        return _named_call(call, call.func.id)
    if not isinstance(call.func, ast.Attribute):
        raise _fail(call, "this is not a Rewind step call.")

    method = call.func.attr
    receiver = call.func.value

    if (
        method == "press"
        and isinstance(receiver, ast.Attribute)
        and receiver.attr == "keyboard"
        and _frame_of(receiver.value)[0]
    ):
        return _keyboard_step(call)

    is_scope, frame_url = _frame_of(receiver)
    if is_scope:
        if method not in _PAGE_METHODS:
            raise _fail(call, f"page has no step called {method!r}.")
        return _page_step(method, call, frame_url)

    target = _target_of(receiver)
    if target is None:
        raise _fail(call, "this call does not act on page or on a locator.")
    if method not in _ELEMENT_METHODS:
        raise _fail(call, f"an element has no step called {method!r}.")
    return _element_step(method, call, target)


def _read_body(statements: list[ast.stmt]) -> list[dict]:
    steps: list[dict] = []
    for statement in statements:
        if isinstance(statement, (ast.Pass, ast.Import, ast.ImportFrom)):
            continue
        if not isinstance(statement, ast.Expr):
            raise _fail(statement, "only Rewind step calls belong in this script.")
        if isinstance(statement.value, ast.Constant):
            continue  # a docstring
        if not isinstance(statement.value, ast.Call):
            raise _fail(statement, "only Rewind step calls belong in this script.")
        steps.append(_step_from_call(statement.value))
    return steps


def parse_script(source: str) -> list[dict]:
    """The steps a script describes, flow first and exit checks last."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ScriptError(
            f"Line {error.lineno or 0}: {error.msg}. The script has to stay "
            "valid Python."
        ) from None

    flow: list[dict] = []
    criteria: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.FunctionDef):
            bucket = criteria if node.name == EXIT_FUNCTION else flow
            bucket.extend(_read_body(node.body))
            continue
        flow.extend(_read_body([node]))

    ordered: list[dict] = []
    for position, step in enumerate(flow):
        ordered.append({**step, "order_index": position, "is_exit_criteria": False})
    for position, step in enumerate(criteria):
        ordered.append({**step, "order_index": position, "is_exit_criteria": True})
    return ordered


def carry_over(parsed: list[dict], existing: list) -> list[dict]:
    """Keep what the script cannot say, where the step it belongs to survived.

    The script describes what a step does. It says nothing about the element
    fingerprint the recorder wrote down, which is what lets replay find a
    control the page has moved - so that is carried across whenever the step
    still points at the same element. An edited selector deliberately loses
    it: a fingerprint of the element that used to be there would send the
    healing after the wrong thing.
    """
    by_slot: dict[tuple[bool, int], Any] = {}
    for step in existing:
        by_slot[(bool(step.is_exit_criteria), step.order_index)] = step

    out: list[dict] = []
    for step in parsed:
        previous = by_slot.get((step["is_exit_criteria"], step["order_index"]))
        merged = dict(step)
        if previous is not None:
            merged["id"] = previous.id
            same_element = (previous.selector or "") == (
                step["selector"] or ""
            ) and _enum_value(previous.selector_strategy) == step["selector_strategy"]
            if same_element:
                merged["element_meta"] = previous.element_meta
        out.append(merged)
    return out
