import pytest
from unittest.mock import AsyncMock
from app.models.models import Step, ActionEnum, SelectorStrategyEnum
from app.execution.step_handlers import registry


@pytest.mark.asyncio
async def test_all_actions_registered():
    for action in ActionEnum:
        assert action in registry.handlers, f"Handler for {action} is missing"


@pytest.mark.asyncio
async def test_unknown_action_raises_error(mock_page):
    step = Step(
        action="invalid_action",  # type: ignore
        selector="test",
        selector_strategy=SelectorStrategyEnum.test_id,
    )
    with pytest.raises(ValueError, match="No handler registered for action"):
        await registry.execute(step, mock_page)


@pytest.mark.asyncio
async def test_navigate_handler(mock_page):
    step = Step(
        action=ActionEnum.navigate,
        selector="",
        selector_strategy=SelectorStrategyEnum.css,
        value="https://test.com",
    )
    await registry.execute(step, mock_page)
    mock_page.goto.assert_called_once_with("https://test.com")


@pytest.mark.asyncio
async def test_click_handler(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector="submit-btn",
        selector_strategy=SelectorStrategyEnum.test_id,
    )
    await registry.execute(step, mock_page)
    mock_page.get_by_test_id.assert_called_once_with("submit-btn")
    mock_page.locator_mock.click.assert_called_once()


@pytest.mark.asyncio
async def test_fill_handler(mock_page):
    step = Step(
        action=ActionEnum.fill,
        selector="input-field",
        selector_strategy=SelectorStrategyEnum.test_id,
        value="test data",
    )
    await registry.execute(step, mock_page)
    mock_page.locator_mock.fill.assert_called_once_with("test data")


@pytest.mark.asyncio
async def test_wait_handler(mock_page):
    step = Step(
        action=ActionEnum.wait,
        selector="",
        selector_strategy=SelectorStrategyEnum.css,
        value="2000",
    )
    await registry.execute(step, mock_page)
    mock_page.wait_for_timeout.assert_called_once_with(2000)


@pytest.mark.asyncio
async def test_select_handler(mock_page):
    step = Step(
        action=ActionEnum.select,
        selector="dropdown",
        selector_strategy=SelectorStrategyEnum.css,
        value="option-1",
    )
    await registry.execute(step, mock_page)
    mock_page.locator_mock.select_option.assert_called_once_with("option-1")


@pytest.mark.asyncio
async def test_hover_handler(mock_page):
    step = Step(
        action=ActionEnum.hover,
        selector="menu",
        selector_strategy=SelectorStrategyEnum.css,
    )
    await registry.execute(step, mock_page)
    mock_page.locator_mock.hover.assert_called_once()


@pytest.mark.asyncio
async def test_press_key_handler(mock_page):
    step = Step(
        action=ActionEnum.press_key,
        selector="",
        selector_strategy=SelectorStrategyEnum.css,
        value="Enter",
    )
    await registry.execute(step, mock_page)
    mock_page.keyboard.press.assert_called_once_with("Enter")


@pytest.mark.asyncio
async def test_assert_handler(mock_page):
    step = Step(
        action=ActionEnum.assert_,
        selector="element",
        selector_strategy=SelectorStrategyEnum.css,
        expected_value="expected text",
    )
    mock_page.locator_mock.inner_text.return_value = "this is the expected text here"
    await registry.execute(step, mock_page)
    mock_page.locator_mock.inner_text.assert_called_once()

    mock_page.locator_mock.inner_text.return_value = "something else"
    with pytest.raises(AssertionError, match="to contain 'expected text'"):
        await registry.execute(step, mock_page)
