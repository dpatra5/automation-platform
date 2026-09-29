"""The exit-criteria vocabulary: every check the GUIs offer must be runnable."""

from unittest.mock import AsyncMock

import pytest

from app.execution import assertions
from app.execution.step_handlers import registry
from app.models.models import ActionEnum, SelectorStrategyEnum, Step


def _check(assertion_type, expected=None, selector="element", value=None):
    return Step(
        action=ActionEnum.assert_,
        selector=selector,
        selector_strategy=SelectorStrategyEnum.css,
        assertion_type=assertion_type,
        expected_value=expected,
        value=value,
    )


def test_every_published_check_has_an_implementation():
    """The catalogue is what the dashboard and the recorder render."""
    published = {entry["key"] for entry in assertions.catalogue()}
    assert published, "the catalogue must not be empty"
    assert published <= set(assertions._CHECKS), (
        "a picker option with no runner behind it"
    )
    assert set(assertions._CHECKS) == published, (
        "a runnable check missing from the catalogue"
    )


def test_catalogue_entries_are_grouped_and_labelled():
    for entry in assertions.catalogue():
        assert entry["label"] and entry["group"], entry["key"]


@pytest.mark.asyncio
async def test_unknown_check_is_rejected_clearly(mock_page):
    with pytest.raises(assertions.AssertionCheckError, match="Unknown check"):
        await registry.execute(_check("no_such_check", "x"), mock_page)


@pytest.mark.asyncio
async def test_text_length_check(mock_page):
    mock_page.locator_mock.inner_text.return_value = "12345"
    await registry.execute(_check("text_length_equals", "5"), mock_page)

    with pytest.raises(AssertionError, match="found 5"):
        await registry.execute(_check("text_length_equals", "9"), mock_page)


@pytest.mark.asyncio
async def test_text_matches_pattern(mock_page):
    mock_page.locator_mock.inner_text.return_value = "Order 1841 confirmed"
    await registry.execute(_check("text_matches", r"^Order \d+ confirmed$"), mock_page)

    with pytest.raises(AssertionError):
        await registry.execute(_check("text_matches", r"^Cancelled"), mock_page)


@pytest.mark.asyncio
async def test_a_broken_pattern_says_so_rather_than_failing_the_page(mock_page):
    mock_page.locator_mock.inner_text.return_value = "anything"
    with pytest.raises(assertions.AssertionCheckError, match="not a valid pattern"):
        await registry.execute(_check("text_matches", "([unclosed"), mock_page)


@pytest.mark.asyncio
async def test_input_value_checks(mock_page):
    mock_page.locator_mock.input_value.return_value = "42"
    await registry.execute(_check("value_equals", "42"), mock_page)
    await registry.execute(_check("value_number_at_least", "40"), mock_page)
    await registry.execute(_check("value_not_empty"), mock_page)

    with pytest.raises(AssertionError, match="at most"):
        await registry.execute(_check("value_number_at_most", "10"), mock_page)


@pytest.mark.asyncio
async def test_number_check_on_a_non_numeric_field(mock_page):
    mock_page.locator_mock.input_value.return_value = "not a number"
    with pytest.raises(AssertionError, match="to hold a number"):
        await registry.execute(_check("value_number_equals", "1"), mock_page)


@pytest.mark.asyncio
async def test_count_checks_use_the_whole_match(mock_page):
    mock_page.locator_mock.count.return_value = 3
    await registry.execute(_check("count_equals", "3"), mock_page)
    await registry.execute(_check("count_at_least", "2"), mock_page)
    await registry.execute(_check("exists"), mock_page)

    with pytest.raises(AssertionError, match="at most"):
        await registry.execute(_check("count_at_most", "1"), mock_page)


@pytest.mark.asyncio
async def test_not_exists_passes_when_nothing_matches(mock_page):
    mock_page.locator_mock.count.return_value = 0
    await registry.execute(_check("not_exists"), mock_page)


@pytest.mark.asyncio
async def test_attribute_check_needs_the_attribute_name(mock_page):
    mock_page.locator_mock.get_attribute.return_value = "/orders/1"
    await registry.execute(
        _check("attribute_equals", "/orders/1", value="href"), mock_page
    )

    with pytest.raises(assertions.AssertionCheckError, match="attribute name"):
        await registry.execute(_check("attribute_equals", "/orders/1"), mock_page)


@pytest.mark.asyncio
async def test_class_checks_read_the_class_list(mock_page):
    mock_page.locator_mock.get_attribute.return_value = "row selected dense"
    await registry.execute(_check("has_class", "selected"), mock_page)
    await registry.execute(_check("not_has_class", "disabled"), mock_page)

    with pytest.raises(AssertionError):
        await registry.execute(_check("has_class", "disabled"), mock_page)


@pytest.mark.asyncio
async def test_dropdown_selection_check(mock_page):
    mock_page.locator_mock.evaluate.return_value = ["Express delivery"]
    await registry.execute(
        _check("selected_label_equals", "Express delivery"), mock_page
    )

    with pytest.raises(AssertionError):
        await registry.execute(_check("selected_label_equals", "Standard"), mock_page)


@pytest.mark.asyncio
async def test_page_level_checks_need_no_element(mock_page):
    mock_page.url = "https://app.test/orders/1841?ok=1"
    mock_page.title = AsyncMock(return_value="Order 1841")

    await registry.execute(_check("url_contains", "/orders/", selector=""), mock_page)
    await registry.execute(_check("title_equals", "Order 1841", selector=""), mock_page)

    with pytest.raises(AssertionError, match="Expected the URL to contain"):
        await registry.execute(
            _check("url_contains", "/invoices/", selector=""), mock_page
        )
