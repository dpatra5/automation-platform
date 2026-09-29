import pytest
from app.models.models import Step, ActionEnum, SelectorStrategyEnum
from app.execution.step_handlers import registry


@pytest.mark.asyncio
async def test_selector_test_id(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector="my-test-id",
        selector_strategy=SelectorStrategyEnum.test_id,
    )
    await registry.execute(step, mock_page)
    mock_page.get_by_test_id.assert_called_once_with("my-test-id")


@pytest.mark.asyncio
async def test_selector_role(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector="button",
        selector_strategy=SelectorStrategyEnum.role,
    )
    await registry.execute(step, mock_page)
    mock_page.get_by_role.assert_called_once_with("button")


@pytest.mark.asyncio
async def test_selector_text(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector="Submit",
        selector_strategy=SelectorStrategyEnum.text,
    )
    await registry.execute(step, mock_page)
    # Short text is looked up whole: "Submit" must not answer to "Submit order".
    mock_page.get_by_text.assert_called_once_with("Submit", exact=True)


@pytest.mark.asyncio
async def test_selector_css(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector=".btn-primary",
        selector_strategy=SelectorStrategyEnum.css,
    )
    await registry.execute(step, mock_page)
    mock_page.locator.assert_called_once_with(".btn-primary")


@pytest.mark.asyncio
async def test_selector_xpath(mock_page):
    step = Step(
        action=ActionEnum.click,
        selector="//div/button",
        selector_strategy=SelectorStrategyEnum.xpath,
    )
    await registry.execute(step, mock_page)
    mock_page.locator.assert_called_once_with("xpath=//div/button")
