"""Действия бота поверх хранилища."""

from datetime import timedelta

import pytest

from bot.actions import BotActions
from core.models import ItemDraft
from core.timeutil import local_now, to_iso


class FakeApplication:
    """Приложение без планировщика и сети — нужен только доступ к данным."""

    def __init__(self, services):
        self.services = services
        self.settings = services.settings
        self.library = type("Library", (), {"all": staticmethod(dict), "errors": {}})()


@pytest.fixture
def actions(services) -> BotActions:
    return BotActions(FakeApplication(services))


async def test_today_shows_only_todays_lessons(services, actions):
    timezone = services.settings.timezone
    now = local_now(timezone)
    await services.items.upsert(ItemDraft(
        kind="lesson", source="tg", title="Матанализ, лекция", body="ауд. 301",
        due_at=to_iso(now.replace(hour=9, minute=0)), external_id="today-1",
    ))
    await services.items.upsert(ItemDraft(
        kind="lesson", source="tg", title="Физика, завтра",
        due_at=to_iso(now + timedelta(days=1)), external_id="tomorrow-1",
    ))
    text, _ = await actions.today()
    assert "Матанализ" in text
    assert "Физика" not in text


async def test_today_reports_homework_due_today(services, actions):
    now = local_now(services.settings.timezone)
    await services.items.upsert(ItemDraft(
        kind="homework", source="moodle", title="Сдать РГР",
        due_at=to_iso(now.replace(hour=23, minute=0)), external_id="hw-1",
    ))
    text, _ = await actions.today()
    assert "Сдать РГР" in text


async def test_today_is_explicit_when_empty(services, actions):
    text, markup = await actions.today()
    assert "ничего не запланировано" in text
    assert markup is None


async def test_items_list_has_buttons(services, actions):
    await services.items.upsert(ItemDraft(kind="task", source="bot", title="Купить хлеб"))
    text, markup = await actions.items("task", "Задач нет.")
    assert "Купить хлеб" in text
    assert markup is not None and len(markup.inline_keyboard) == 1


async def test_add_and_complete_task(services, actions):
    text, _ = await actions.add_task("Позвонить в деканат")
    item_id = int(text.split("#")[1].rstrip("."))
    await actions.complete(item_id)
    assert await services.items.list_open("task") == []
