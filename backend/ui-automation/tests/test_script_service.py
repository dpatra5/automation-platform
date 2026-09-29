"""The script view has to be able to read back everything it writes.

A step that survives rendering but not parsing is a step the user loses the
moment they press Save, so the round trip is checked for every action rather
than for a representative few.
"""

import pytest

from app.exceptions import RewindError
from app.models.models import ActionEnum, SelectorStrategyEnum, Step, TestCase
from app.services.script_service import (
    ScriptError,
    carry_over,
    parse_script,
    render_script,
)


def step(action, **kwargs):
    defaults = {
        "order_index": kwargs.pop("order_index", 0),
        "selector": "",
        "selector_strategy": SelectorStrategyEnum.xpath,
        "value": None,
        "assertion_type": None,
        "expected_value": None,
        "frame_url": None,
        "element_meta": None,
        "is_exit_criteria": False,
    }
    defaults.update(kwargs)
    return Step(action=ActionEnum(action), **defaults)


def case(steps):
    for index, one in enumerate(steps):
        one.order_index = index if not one.is_exit_criteria else one.order_index
    return TestCase(name="Checkout flow", start_url="https://shop.test/", steps=steps)


ALL_STEPS = [
    step("navigate", value="https://shop.test/cart"),
    step("reload"),
    step("go_back"),
    step("go_forward"),
    step("click", selector="//button[@id='pay']"),
    step("dblclick", selector="//li[normalize-space()='Row']"),
    step("right_click", selector="//td[@data-col='name']"),
    step("hover", selector="//nav[@aria-label='Main']"),
    step("drag", selector="//li[@id='a']", value="//ul[@id='bin']"),
    step("scroll", selector="//div[@id='panel']", value="0,400"),
    step("scroll", value="0,900"),
    step("scroll", selector="//div[@id='lazy']"),
    step("fill", selector="//input[@name='email']", value="a@b.test"),
    step("type", selector="//input[@name='code']", value="1234"),
    step("press_key", selector="//input[@name='code']", value="Enter"),
    step("press_key", value="Control+A"),
    step("select", selector="//select[@name='size']", value="large"),
    step("check", selector="//input[@id='terms']"),
    step("uncheck", selector="//input[@id='news']"),
    step("upload", selector="//input[@type='file']", value="/tmp/a.png"),
    step("wait", value="1500"),
    step("wait_for_selector", selector="//div[@id='done']"),
    step("wait_for_url", value="https://shop.test/**"),
    step("switch_tab", value="https://shop.test/receipt"),
]


def test_every_action_survives_the_round_trip():
    parsed = parse_script(render_script(case(list(ALL_STEPS))))
    assert len(parsed) == len(ALL_STEPS)
    for original, read_back in zip(ALL_STEPS, parsed):
        assert read_back["action"] == original.action.value
        assert read_back["selector"] == original.selector
        assert read_back["value"] == original.value


def test_xpath_selectors_are_written_as_xpath():
    script = render_script(case([step("click", selector="//button[@id='pay']")]))
    assert "page.locator(\"xpath=//button[@id='pay']\").click()" in script
    assert parse_script(script)[0]["selector_strategy"] == "xpath"


def test_each_block_is_tagged_with_its_step():
    script = render_script(
        case(
            [
                step("navigate", value="https://shop.test/"),
                step("click", selector="//button[@id='pay']"),
            ]
        )
    )
    assert "# Step 1 - navigate" in script
    assert "# Step 2 - click" in script
    assert "# xpath: //button[@id='pay']" in script


def test_the_element_label_is_shown_beside_the_call():
    script = render_script(
        case(
            [
                step(
                    "click",
                    selector="//button[@id='pay']",
                    element_meta='{"tag": "button", "name": "Pay now"}',
                )
            ]
        )
    )
    assert "# on: Pay now" in script


def test_checks_round_trip_with_their_expected_value():
    checks = [
        step(
            "assert",
            selector="//h1",
            assertion_type="text_contains",
            expected_value="Thank you",
            is_exit_criteria=True,
        ),
        step(
            "assert",
            assertion_type="url_contains",
            expected_value="/receipt",
            is_exit_criteria=True,
            order_index=1,
        ),
        step(
            "assert",
            selector="//div[@id='state']",
            assertion_type="attribute_equals",
            expected_value="open",
            value="data-state",
            is_exit_criteria=True,
            order_index=2,
        ),
    ]
    parsed = parse_script(render_script(case(list(checks))))
    assert [p["is_exit_criteria"] for p in parsed] == [True, True, True]
    assert parsed[0]["assertion_type"] == "text_contains"
    assert parsed[0]["expected_value"] == "Thank you"
    assert parsed[1]["selector"] == ""
    assert parsed[2]["value"] == "data-state"


def test_a_step_inside_an_iframe_keeps_its_frame():
    inner = "https://app.test/embedded"
    parsed = parse_script(
        render_script(case([step("click", selector="//button", frame_url=inner)]))
    )
    assert parsed[0]["frame_url"] == inner


def test_exit_checks_are_kept_apart_from_the_flow():
    parsed = parse_script(
        render_script(
            case(
                [
                    step("click", selector="//button[@id='pay']"),
                    step(
                        "assert",
                        selector="//h1",
                        assertion_type="visible",
                        is_exit_criteria=True,
                    ),
                ]
            )
        )
    )
    assert [p["is_exit_criteria"] for p in parsed] == [False, True]
    assert [p["order_index"] for p in parsed] == [0, 0]


def test_a_quoted_label_does_not_break_the_script():
    tricky = "//button[normalize-space()=concat('Don', \"'\", 't \"save\"')]"
    parsed = parse_script(render_script(case([step("click", selector=tricky)])))
    assert parsed[0]["selector"] == tricky


@pytest.mark.parametrize(
    "source",
    [
        "def test_x():\n    page.frobnicate()\n",
        "def test_x():\n    page.locator('//b').frobnicate()\n",
        "def test_x():\n    x = 1\n",
        "def test_x():\n    page.goto(\n",
        "def test_x():\n    check(page)\n",
    ],
)
def test_a_line_that_is_not_a_step_is_reported_not_dropped(source):
    with pytest.raises(ScriptError) as raised:
        parse_script(source)
    assert "Line" in str(raised.value)


def test_a_script_error_answers_as_a_bad_request():
    assert issubclass(ScriptError, RewindError)


def test_the_fingerprint_is_kept_while_the_selector_is_unchanged():
    existing = [
        step(
            "click",
            selector="//button[@id='pay']",
            element_meta='{"tag": "button", "name": "Pay now"}',
        )
    ]
    parsed = parse_script(render_script(case(list(existing))))
    merged = carry_over(parsed, existing)
    assert merged[0]["element_meta"] == existing[0].element_meta


def test_an_edited_selector_drops_the_old_fingerprint():
    existing = [
        step(
            "click",
            selector="//button[@id='pay']",
            element_meta='{"tag": "button", "name": "Pay now"}',
        )
    ]
    edited = parse_script(
        render_script(case([step("click", selector="//button[@id='cancel']")]))
    )
    merged = carry_over(edited, existing)
    assert "element_meta" not in merged[0]
    assert merged[0]["id"] == existing[0].id
