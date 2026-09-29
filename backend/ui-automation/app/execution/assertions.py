"""Checks a step can make about the page: the exit criteria vocabulary.

One place defines every condition Rewind understands. The runner uses it to
evaluate a check, and the API publishes it so the dashboard and the recorder
can build their pickers from the same list instead of hard-coding labels that
drift out of sync with the engine.

A check reads three things off the step:

* ``selector`` / ``selector_strategy`` - the element, when the check needs one
* ``value``                            - a parameter, e.g. the attribute name
* ``expected_value``                   - what the element is expected to hold
"""

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, NoReturn

# Groups, in the order the pickers should show them.
TEXT = "Text"
VALUE = "Input value"
DROPDOWN = "Dropdown"
STATE = "State"
ATTRIBUTE = "Attribute"
IMAGE = "Image"
COUNT = "Count"
PAGE = "Page"

DEFAULT_ASSERTION = "text_contains"


@dataclass(frozen=True)
class AssertionSpec:
    """What a check is called, and what the GUI has to ask for."""

    key: str
    label: str
    group: str
    #: Human sentence used as the picker's helper text.
    hint: str = ""
    needs_selector: bool = True
    needs_expected: bool = True
    expected_label: str = "Expected value"
    #: Some checks take a second input (attribute name, CSS property, ...),
    #: which is stored in the step's `value` field.
    param_label: str = ""
    #: The expected value must parse as a whole number.
    expected_is_number: bool = False


SPECS: list[AssertionSpec] = [
    # --------------------------------------------------------------- text
    AssertionSpec(
        "text_contains",
        "Text contains",
        TEXT,
        "The element's visible text includes this.",
    ),
    AssertionSpec(
        "text_not_contains",
        "Text does not contain",
        TEXT,
        "The element's visible text must not include this.",
    ),
    AssertionSpec(
        "text_equals",
        "Text is exactly",
        TEXT,
        "Compared after trimming surrounding whitespace.",
    ),
    AssertionSpec("text_not_equals", "Text is not", TEXT),
    AssertionSpec(
        "text_matches",
        "Text matches pattern",
        TEXT,
        "A regular expression, e.g. ^Order \\d+ confirmed$",
        expected_label="Regular expression",
    ),
    AssertionSpec(
        "text_length_equals",
        "Text length is",
        TEXT,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec(
        "text_length_at_least",
        "Text length is at least",
        TEXT,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec(
        "text_length_at_most",
        "Text length is at most",
        TEXT,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec("text_empty", "Text is empty", TEXT, needs_expected=False),
    AssertionSpec("text_not_empty", "Text is not empty", TEXT, needs_expected=False),
    # -------------------------------------------------------------- values
    AssertionSpec(
        "value_equals",
        "Value is exactly",
        VALUE,
        "What the field currently holds, not its placeholder.",
    ),
    AssertionSpec("value_contains", "Value contains", VALUE),
    AssertionSpec(
        "value_matches",
        "Value matches pattern",
        VALUE,
        expected_label="Regular expression",
    ),
    AssertionSpec(
        "value_length_equals",
        "Value length is",
        VALUE,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec(
        "value_length_at_least",
        "Value length is at least",
        VALUE,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec(
        "value_length_at_most",
        "Value length is at most",
        VALUE,
        expected_label="Number of characters",
        expected_is_number=True,
    ),
    AssertionSpec("value_empty", "Value is empty", VALUE, needs_expected=False),
    AssertionSpec("value_not_empty", "Value is not empty", VALUE, needs_expected=False),
    AssertionSpec(
        "value_number_equals",
        "Number equals",
        VALUE,
        "Reads the field as a number, so 5.0 and 5 match.",
        expected_label="Number",
    ),
    AssertionSpec(
        "value_number_at_least", "Number is at least", VALUE, expected_label="Number"
    ),
    AssertionSpec(
        "value_number_at_most", "Number is at most", VALUE, expected_label="Number"
    ),
    # ------------------------------------------------------------ dropdown
    AssertionSpec(
        "selected_value_equals",
        "Selected option value is",
        DROPDOWN,
        "Matches the option's value attribute.",
    ),
    AssertionSpec(
        "selected_label_equals",
        "Selected option label is",
        DROPDOWN,
        "Matches the text the user sees in the list.",
    ),
    AssertionSpec(
        "selected_label_contains", "Selected option label contains", DROPDOWN
    ),
    AssertionSpec(
        "selected_count_equals",
        "Number of selected options is",
        DROPDOWN,
        expected_label="How many",
        expected_is_number=True,
    ),
    AssertionSpec(
        "option_count_equals",
        "Number of options is",
        DROPDOWN,
        expected_label="How many",
        expected_is_number=True,
    ),
    AssertionSpec("has_option", "Has an option labelled", DROPDOWN),
    # --------------------------------------------------------------- state
    AssertionSpec("visible", "Is visible", STATE, needs_expected=False),
    AssertionSpec("hidden", "Is hidden", STATE, needs_expected=False),
    AssertionSpec("exists", "Exists in the page", STATE, needs_expected=False),
    AssertionSpec("not_exists", "Is not in the page", STATE, needs_expected=False),
    AssertionSpec("enabled", "Is enabled", STATE, needs_expected=False),
    AssertionSpec("disabled", "Is disabled", STATE, needs_expected=False),
    AssertionSpec("editable", "Is editable", STATE, needs_expected=False),
    AssertionSpec("not_editable", "Is read-only", STATE, needs_expected=False),
    AssertionSpec("checked", "Is checked", STATE, needs_expected=False),
    AssertionSpec("unchecked", "Is not checked", STATE, needs_expected=False),
    AssertionSpec("focused", "Has keyboard focus", STATE, needs_expected=False),
    # ----------------------------------------------------------- attribute
    AssertionSpec(
        "attribute_equals",
        "Attribute is exactly",
        ATTRIBUTE,
        param_label="Attribute name, e.g. href",
    ),
    AssertionSpec(
        "attribute_contains",
        "Attribute contains",
        ATTRIBUTE,
        param_label="Attribute name, e.g. href",
    ),
    AssertionSpec(
        "attribute_exists",
        "Attribute is present",
        ATTRIBUTE,
        needs_expected=False,
        param_label="Attribute name",
    ),
    AssertionSpec("has_class", "Has CSS class", ATTRIBUTE, expected_label="Class name"),
    AssertionSpec(
        "not_has_class",
        "Does not have CSS class",
        ATTRIBUTE,
        expected_label="Class name",
    ),
    AssertionSpec(
        "css_equals",
        "Computed style is",
        ATTRIBUTE,
        "Reads the value the browser actually applied.",
        param_label="CSS property, e.g. color",
    ),    # ---------------------------------------------------------------- image
    AssertionSpec("image_visible", "Image is visible", IMAGE, needs_expected=False),
    AssertionSpec("image_hidden", "Image is hidden", IMAGE, needs_expected=False),
    AssertionSpec(
        "image_loaded",
        "Image has loaded successfully",
        IMAGE,
        "The image src has loaded without errors.",
        needs_expected=False,
    ),
    AssertionSpec(
        "image_src_contains",
        "Image src contains",
        IMAGE,
        "Checks the src attribute includes this text.",
    ),
    AssertionSpec(
        "image_src_equals",
        "Image src is exactly",
        IMAGE,
        "The complete src attribute value.",
        expected_label="Full URL or path",
    ),
    AssertionSpec(
        "image_alt_text_contains",
        "Image alt text contains",
        IMAGE,
        "The alt attribute includes this text.",
    ),
    AssertionSpec(
        "image_alt_text_equals",
        "Image alt text is exactly",
        IMAGE,
        "The complete alt attribute value.",
    ),
    AssertionSpec(
        "image_alt_text_exists",
        "Image has alt text",
        IMAGE,
        needs_expected=False,
    ),
    AssertionSpec(
        "image_width_equals",
        "Image width is",
        IMAGE,
        "The actual rendered width in pixels.",
        expected_label="Width in pixels",
        expected_is_number=True,
    ),
    AssertionSpec(
        "image_height_equals",
        "Image height is",
        IMAGE,
        "The actual rendered height in pixels.",
        expected_label="Height in pixels",
        expected_is_number=True,
    ),    # --------------------------------------------------------------- count
    AssertionSpec(
        "count_equals",
        "Matching elements",
        COUNT,
        "How many elements the selector finds.",
        expected_label="How many",
        expected_is_number=True,
    ),
    AssertionSpec(
        "count_at_least",
        "Matching elements at least",
        COUNT,
        expected_label="How many",
        expected_is_number=True,
    ),
    AssertionSpec(
        "count_at_most",
        "Matching elements at most",
        COUNT,
        expected_label="How many",
        expected_is_number=True,
    ),
    # ---------------------------------------------------------------- page
    AssertionSpec("url_contains", "URL contains", PAGE, needs_selector=False),
    AssertionSpec("url_equals", "URL is exactly", PAGE, needs_selector=False),
    AssertionSpec(
        "url_matches",
        "URL matches pattern",
        PAGE,
        needs_selector=False,
        expected_label="Regular expression",
    ),
    AssertionSpec("title_contains", "Page title contains", PAGE, needs_selector=False),
    AssertionSpec("title_equals", "Page title is exactly", PAGE, needs_selector=False),
]

BY_KEY: dict[str, AssertionSpec] = {spec.key: spec for spec in SPECS}


@dataclass
class Check:
    """Everything a check function is allowed to look at."""

    page: Any
    locator: Any
    selector: str
    expected: str
    param: str

    async def text(self) -> str:
        """Visible text, falling back to markup text for collapsed nodes."""
        element = self.element()
        rendered = (await element.inner_text()) or ""
        if rendered.strip():
            return rendered
        return (await element.text_content()) or ""

    async def input_value(self) -> str:
        return (await self.element().input_value()) or ""

    def element(self):
        if self.locator is None:
            raise AssertionCheckError(
                "This check needs an element, but the step has no selector."
            )
        return self.locator.first

    def number(self) -> float:
        try:
            return float(self.expected.strip())
        except (TypeError, ValueError):
            raise AssertionCheckError(f"'{self.expected}' is not a number.") from None

    def whole_number(self) -> int:
        value = self.number()
        if value != int(value):
            raise AssertionCheckError(f"'{self.expected}' has to be a whole number.")
        return int(value)

    def pattern(self) -> "re.Pattern[str]":
        try:
            return re.compile(self.expected)
        except re.error as e:
            raise AssertionCheckError(
                f"'{self.expected}' is not a valid pattern: {e}"
            ) from None

    def require_param(self, what: str) -> str:
        if not (self.param or "").strip():
            raise AssertionCheckError(f"This check needs {what}.")
        return self.param.strip()


class AssertionCheckError(ValueError):
    """The check itself is misconfigured, as opposed to the page being wrong."""


CheckFn = Callable[[Check], Awaitable[None]]
_CHECKS: dict[str, CheckFn] = {}


def check(key: str):
    def register(fn: CheckFn) -> CheckFn:
        _CHECKS[key] = fn
        return fn

    return register


def _fail(message: str) -> NoReturn:
    raise AssertionError(message)


# ------------------------------------------------------------------- text


@check("text_contains")
async def _text_contains(c: Check) -> None:
    text = await c.text()
    if c.expected not in text:
        _fail(
            f"Expected the text of {c.selector} to contain {c.expected!r}, found {text.strip()!r}"
        )


@check("text_not_contains")
async def _text_not_contains(c: Check) -> None:
    text = await c.text()
    if c.expected in text:
        _fail(f"Expected the text of {c.selector} not to contain {c.expected!r}")


@check("text_equals")
async def _text_equals(c: Check) -> None:
    text = (await c.text()).strip()
    if text != c.expected.strip():
        _fail(f"Expected the text of {c.selector} to be {c.expected!r}, found {text!r}")


@check("text_not_equals")
async def _text_not_equals(c: Check) -> None:
    text = (await c.text()).strip()
    if text == c.expected.strip():
        _fail(f"Expected the text of {c.selector} to differ from {c.expected!r}")


@check("text_matches")
async def _text_matches(c: Check) -> None:
    text = await c.text()
    if not c.pattern().search(text):
        _fail(
            f"Expected the text of {c.selector} to match /{c.expected}/, found {text.strip()!r}"
        )


@check("text_length_equals")
async def _text_length_equals(c: Check) -> None:
    text = (await c.text()).strip()
    if len(text) != c.whole_number():
        _fail(
            f"Expected {c.selector} to hold {c.expected} characters, found {len(text)}"
        )


@check("text_length_at_least")
async def _text_length_at_least(c: Check) -> None:
    text = (await c.text()).strip()
    if len(text) < c.whole_number():
        _fail(
            f"Expected {c.selector} to hold at least {c.expected} characters, found {len(text)}"
        )


@check("text_length_at_most")
async def _text_length_at_most(c: Check) -> None:
    text = (await c.text()).strip()
    if len(text) > c.whole_number():
        _fail(
            f"Expected {c.selector} to hold at most {c.expected} characters, found {len(text)}"
        )


@check("text_empty")
async def _text_empty(c: Check) -> None:
    text = (await c.text()).strip()
    if text:
        _fail(f"Expected {c.selector} to have no text, found {text!r}")


@check("text_not_empty")
async def _text_not_empty(c: Check) -> None:
    if not (await c.text()).strip():
        _fail(f"Expected {c.selector} to have some text, found none")


# ------------------------------------------------------------------ values


@check("value_equals")
async def _value_equals(c: Check) -> None:
    value = await c.input_value()
    if value != c.expected:
        _fail(f"Expected {c.selector} to hold {c.expected!r}, found {value!r}")


@check("value_contains")
async def _value_contains(c: Check) -> None:
    value = await c.input_value()
    if c.expected not in value:
        _fail(f"Expected {c.selector} to contain {c.expected!r}, found {value!r}")


@check("value_matches")
async def _value_matches(c: Check) -> None:
    value = await c.input_value()
    if not c.pattern().search(value):
        _fail(f"Expected {c.selector} to match /{c.expected}/, found {value!r}")


@check("value_length_equals")
async def _value_length_equals(c: Check) -> None:
    value = await c.input_value()
    if len(value) != c.whole_number():
        _fail(
            f"Expected {c.selector} to hold {c.expected} characters, found {len(value)}"
        )


@check("value_length_at_least")
async def _value_length_at_least(c: Check) -> None:
    value = await c.input_value()
    if len(value) < c.whole_number():
        _fail(
            f"Expected {c.selector} to hold at least {c.expected} characters, found {len(value)}"
        )


@check("value_length_at_most")
async def _value_length_at_most(c: Check) -> None:
    value = await c.input_value()
    if len(value) > c.whole_number():
        _fail(
            f"Expected {c.selector} to hold at most {c.expected} characters, found {len(value)}"
        )


@check("value_empty")
async def _value_empty(c: Check) -> None:
    value = await c.input_value()
    if value.strip():
        _fail(f"Expected {c.selector} to be empty, found {value!r}")


@check("value_not_empty")
async def _value_not_empty(c: Check) -> None:
    if not (await c.input_value()).strip():
        _fail(f"Expected {c.selector} to hold something, found an empty field")


def _as_number(raw: str, selector: str) -> float:
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        _fail(f"Expected {selector} to hold a number, found {raw!r}")


@check("value_number_equals")
async def _value_number_equals(c: Check) -> None:
    value = _as_number(await c.input_value(), c.selector)
    if value != c.number():
        _fail(f"Expected {c.selector} to be {c.expected}, found {value:g}")


@check("value_number_at_least")
async def _value_number_at_least(c: Check) -> None:
    value = _as_number(await c.input_value(), c.selector)
    if value < c.number():
        _fail(f"Expected {c.selector} to be at least {c.expected}, found {value:g}")


@check("value_number_at_most")
async def _value_number_at_most(c: Check) -> None:
    value = _as_number(await c.input_value(), c.selector)
    if value > c.number():
        _fail(f"Expected {c.selector} to be at most {c.expected}, found {value:g}")


# ---------------------------------------------------------------- dropdown


async def _selected_labels(c: Check) -> list[str]:
    return await c.element().evaluate(
        "el => Array.from(el.selectedOptions || []).map(o => (o.textContent || '').trim())"
    )


@check("selected_value_equals")
async def _selected_value_equals(c: Check) -> None:
    value = await c.input_value()
    if value != c.expected:
        _fail(f"Expected {c.selector} to have {c.expected!r} selected, found {value!r}")


@check("selected_label_equals")
async def _selected_label_equals(c: Check) -> None:
    labels = await _selected_labels(c)
    if c.expected.strip() not in labels:
        _fail(
            f"Expected {c.selector} to show {c.expected!r}, found {labels or 'nothing'}"
        )


@check("selected_label_contains")
async def _selected_label_contains(c: Check) -> None:
    labels = await _selected_labels(c)
    if not any(c.expected in label for label in labels):
        _fail(
            f"Expected a selected option of {c.selector} to contain {c.expected!r}, "
            f"found {labels or 'nothing'}"
        )


@check("selected_count_equals")
async def _selected_count_equals(c: Check) -> None:
    labels = await _selected_labels(c)
    if len(labels) != c.whole_number():
        _fail(
            f"Expected {c.expected} selected options in {c.selector}, found {len(labels)}"
        )


@check("option_count_equals")
async def _option_count_equals(c: Check) -> None:
    count = await c.element().evaluate("el => (el.options || []).length")
    if count != c.whole_number():
        _fail(f"Expected {c.expected} options in {c.selector}, found {count}")


@check("has_option")
async def _has_option(c: Check) -> None:
    labels = await c.element().evaluate(
        "el => Array.from(el.options || []).map(o => (o.textContent || '').trim())"
    )
    if c.expected.strip() not in labels:
        _fail(f"Expected {c.selector} to offer {c.expected!r}, found {labels}")


# ------------------------------------------------------------------- state


@check("visible")
async def _visible(c: Check) -> None:
    if not await c.element().is_visible():
        _fail(f"Expected {c.selector} to be visible")


@check("hidden")
async def _hidden(c: Check) -> None:
    if await c.element().is_visible():
        _fail(f"Expected {c.selector} to be hidden")


@check("exists")
async def _exists(c: Check) -> None:
    if await _count(c) == 0:
        _fail(f"Expected {c.selector} to be somewhere in the page")


@check("not_exists")
async def _not_exists(c: Check) -> None:
    found = await _count(c)
    if found:
        _fail(f"Expected {c.selector} to be gone, found {found}")


@check("enabled")
async def _enabled(c: Check) -> None:
    if not await c.element().is_enabled():
        _fail(f"Expected {c.selector} to be enabled")


@check("disabled")
async def _disabled(c: Check) -> None:
    if not await c.element().is_disabled():
        _fail(f"Expected {c.selector} to be disabled")


@check("editable")
async def _editable(c: Check) -> None:
    if not await c.element().is_editable():
        _fail(f"Expected {c.selector} to be editable")


@check("not_editable")
async def _not_editable(c: Check) -> None:
    if await c.element().is_editable():
        _fail(f"Expected {c.selector} to be read-only")


@check("checked")
async def _checked(c: Check) -> None:
    if not await c.element().is_checked():
        _fail(f"Expected {c.selector} to be checked")


@check("unchecked")
async def _unchecked(c: Check) -> None:
    if await c.element().is_checked():
        _fail(f"Expected {c.selector} not to be checked")


@check("focused")
async def _focused(c: Check) -> None:
    focused = await c.element().evaluate("el => el === document.activeElement")
    if not focused:
        _fail(f"Expected {c.selector} to have keyboard focus")


# --------------------------------------------------------------- attribute


@check("attribute_equals")
async def _attribute_equals(c: Check) -> None:
    name = c.require_param("an attribute name")
    actual = await c.element().get_attribute(name)
    if actual != c.expected:
        _fail(f"Expected {c.selector}[{name}] to be {c.expected!r}, found {actual!r}")


@check("attribute_contains")
async def _attribute_contains(c: Check) -> None:
    name = c.require_param("an attribute name")
    actual = await c.element().get_attribute(name) or ""
    if c.expected not in actual:
        _fail(
            f"Expected {c.selector}[{name}] to contain {c.expected!r}, found {actual!r}"
        )


@check("attribute_exists")
async def _attribute_exists(c: Check) -> None:
    name = c.require_param("an attribute name")
    if await c.element().get_attribute(name) is None:
        _fail(f"Expected {c.selector} to carry the {name} attribute")


@check("has_class")
async def _has_class(c: Check) -> None:
    classes = (await c.element().get_attribute("class") or "").split()
    if c.expected.strip() not in classes:
        _fail(
            f"Expected {c.selector} to have the class {c.expected!r}, found {classes or 'none'}"
        )


@check("not_has_class")
async def _not_has_class(c: Check) -> None:
    classes = (await c.element().get_attribute("class") or "").split()
    if c.expected.strip() in classes:
        _fail(f"Expected {c.selector} not to have the class {c.expected!r}")


@check("css_equals")
async def _css_equals(c: Check) -> None:
    prop = c.require_param("a CSS property name")
    actual = await c.element().evaluate(
        "(el, prop) => getComputedStyle(el).getPropertyValue(prop).trim()", prop
    )
    if actual != c.expected.strip():
        _fail(
            f"Expected {c.selector} to compute {prop} as {c.expected!r}, found {actual!r}"
        )


# ------------------------------------------------------------------- image


@check("image_visible")
async def _image_visible(c: Check) -> None:
    if not await c.element().is_visible():
        _fail(f"Expected {c.selector} to be visible")


@check("image_hidden")
async def _image_hidden(c: Check) -> None:
    if await c.element().is_visible():
        _fail(f"Expected {c.selector} to be hidden")


@check("image_loaded")
async def _image_loaded(c: Check) -> None:
    is_loaded = await c.element().evaluate(
        "img => img.complete && img.naturalHeight !== 0"
    )
    if not is_loaded:
        _fail(f"Expected {c.selector} to have loaded successfully, but it hasn't")


@check("image_src_contains")
async def _image_src_contains(c: Check) -> None:
    src = (await c.element().get_attribute("src")) or ""
    if c.expected not in src:
        _fail(
            f"Expected {c.selector} src to contain {c.expected!r}, found {src!r}"
        )


@check("image_src_equals")
async def _image_src_equals(c: Check) -> None:
    src = (await c.element().get_attribute("src")) or ""
    if src != c.expected:
        _fail(
            f"Expected {c.selector} src to be {c.expected!r}, found {src!r}"
        )


@check("image_alt_text_contains")
async def _image_alt_text_contains(c: Check) -> None:
    alt = (await c.element().get_attribute("alt")) or ""
    if c.expected not in alt:
        _fail(
            f"Expected {c.selector} alt text to contain {c.expected!r}, found {alt!r}"
        )


@check("image_alt_text_equals")
async def _image_alt_text_equals(c: Check) -> None:
    alt = (await c.element().get_attribute("alt")) or ""
    if alt != c.expected:
        _fail(
            f"Expected {c.selector} alt text to be {c.expected!r}, found {alt!r}"
        )


@check("image_alt_text_exists")
async def _image_alt_text_exists(c: Check) -> None:
    alt = await c.element().get_attribute("alt")
    if not alt or not alt.strip():
        _fail(f"Expected {c.selector} to have alt text, but it's empty or missing")


@check("image_width_equals")
async def _image_width_equals(c: Check) -> None:
    width = await c.element().evaluate("img => img.naturalWidth")
    if width != c.whole_number():
        _fail(
            f"Expected {c.selector} width to be {c.expected} pixels, found {width}"
        )


@check("image_height_equals")
async def _image_height_equals(c: Check) -> None:
    height = await c.element().evaluate("img => img.naturalHeight")
    if height != c.whole_number():
        _fail(
            f"Expected {c.selector} height to be {c.expected} pixels, found {height}"
        )


# ------------------------------------------------------------------- count


async def _count(c: Check) -> int:
    if c.locator is None:
        raise AssertionCheckError("This check needs a selector to count.")
    return await c.locator.count()


@check("count_equals")
async def _count_equals(c: Check) -> None:
    found = await _count(c)
    if found != c.whole_number():
        _fail(f"Expected {c.expected} elements matching {c.selector}, found {found}")


@check("count_at_least")
async def _count_at_least(c: Check) -> None:
    found = await _count(c)
    if found < c.whole_number():
        _fail(
            f"Expected at least {c.expected} elements matching {c.selector}, found {found}"
        )


@check("count_at_most")
async def _count_at_most(c: Check) -> None:
    found = await _count(c)
    if found > c.whole_number():
        _fail(
            f"Expected at most {c.expected} elements matching {c.selector}, found {found}"
        )


# -------------------------------------------------------------------- page


@check("url_contains")
async def _url_contains(c: Check) -> None:
    if c.expected not in c.page.url:
        _fail(f"Expected the URL to contain {c.expected!r}, found {c.page.url}")


@check("url_equals")
async def _url_equals(c: Check) -> None:
    if c.page.url.rstrip("/") != c.expected.strip().rstrip("/"):
        _fail(f"Expected the URL to be {c.expected!r}, found {c.page.url}")


@check("url_matches")
async def _url_matches(c: Check) -> None:
    if not c.pattern().search(c.page.url):
        _fail(f"Expected the URL to match /{c.expected}/, found {c.page.url}")


@check("title_contains")
async def _title_contains(c: Check) -> None:
    title = await c.page.title()
    if c.expected not in title:
        _fail(f"Expected the page title to contain {c.expected!r}, found {title!r}")


@check("title_equals")
async def _title_equals(c: Check) -> None:
    title = await c.page.title()
    if title.strip() != c.expected.strip():
        _fail(f"Expected the page title to be {c.expected!r}, found {title!r}")


# ----------------------------------------------------------------- runtime


def catalogue() -> list[dict]:
    """The vocabulary, shaped for the API so the GUIs can render a picker."""
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "group": spec.group,
            "hint": spec.hint,
            "needs_selector": spec.needs_selector,
            "needs_expected": spec.needs_expected,
            "expected_label": spec.expected_label,
            "param_label": spec.param_label,
            "expected_is_number": spec.expected_is_number,
        }
        for spec in SPECS
    ]


async def run_assertion(step, page, locator) -> None:
    """Evaluate the step's check. Raises AssertionError when the page is wrong."""
    key = (getattr(step, "assertion_type", None) or DEFAULT_ASSERTION).strip()
    fn = _CHECKS.get(key)
    if fn is None:
        raise AssertionCheckError(
            f"Unknown check '{key}'. Known checks: {', '.join(sorted(_CHECKS))}"
        )
    await fn(
        Check(
            page=page,
            locator=locator,
            selector=getattr(step, "selector", "") or "the page",
            expected=getattr(step, "expected_value", None) or "",
            param=getattr(step, "value", None) or "",
        )
    )
