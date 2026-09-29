import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal, engine
from app.models.models import Project, TestCase, Step, ActionEnum, SelectorStrategyEnum
from app.models.base import Base


async def seed_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        project = Project(
            name="Rewind Demo",
            base_url="https://demo.playwright.dev/todomvc",
            description="Demo project for TodoMVC",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        tc1 = TestCase(
            project_id=project.id,
            name="Add and complete todo",
            description="Adds a new todo and marks it as complete.",
            start_url="https://demo.playwright.dev/todomvc/#/",
        )
        session.add(tc1)
        await session.commit()
        await session.refresh(tc1)

        steps1 = [
            Step(
                test_case_id=tc1.id,
                order_index=1,
                action=ActionEnum.fill,
                selector=".new-todo",
                selector_strategy=SelectorStrategyEnum.css,
                value="Buy milk",
            ),
            Step(
                test_case_id=tc1.id,
                order_index=2,
                action=ActionEnum.press_key,
                selector=".new-todo",
                selector_strategy=SelectorStrategyEnum.css,
                value="Enter",
            ),
            Step(
                test_case_id=tc1.id,
                order_index=3,
                action=ActionEnum.click,
                selector=".toggle",
                selector_strategy=SelectorStrategyEnum.css,
            ),
            # Exit criteria: what has to be true once the flow has run.
            Step(
                test_case_id=tc1.id,
                order_index=1,
                action=ActionEnum.assert_,
                selector=".todo-list li",
                selector_strategy=SelectorStrategyEnum.css,
                assertion_type="count_equals",
                expected_value="1",
                is_exit_criteria=True,
            ),
            Step(
                test_case_id=tc1.id,
                order_index=2,
                action=ActionEnum.assert_,
                selector=".todo-list li .toggle",
                selector_strategy=SelectorStrategyEnum.css,
                assertion_type="checked",
                is_exit_criteria=True,
            ),
        ]
        session.add_all(steps1)

        tc2 = TestCase(
            project_id=project.id,
            name="Filter active todos",
            description="Adds a todo and filters by Active.",
            start_url="https://demo.playwright.dev/todomvc/#/",
        )
        session.add(tc2)
        await session.commit()
        await session.refresh(tc2)

        steps2 = [
            Step(
                test_case_id=tc2.id,
                order_index=1,
                action=ActionEnum.fill,
                selector=".new-todo",
                selector_strategy=SelectorStrategyEnum.css,
                value="Learn Playwright",
            ),
            Step(
                test_case_id=tc2.id,
                order_index=2,
                action=ActionEnum.press_key,
                selector=".new-todo",
                selector_strategy=SelectorStrategyEnum.css,
                value="Enter",
            ),
            Step(
                test_case_id=tc2.id,
                order_index=3,
                action=ActionEnum.click,
                selector="Active",
                selector_strategy=SelectorStrategyEnum.text,
            ),
            Step(
                test_case_id=tc2.id,
                order_index=1,
                action=ActionEnum.assert_,
                selector="",
                selector_strategy=SelectorStrategyEnum.css,
                assertion_type="url_contains",
                expected_value="active",
                is_exit_criteria=True,
            ),
        ]
        session.add_all(steps2)

        await session.commit()
        print("Data seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_data())
