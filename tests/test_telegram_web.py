"""Чтение публичных каналов через t.me без авторизации."""

import httpx
import pytest

from core.errors import TelegramError
from core.models import Trigger, Workflow
from core.timeutil import to_iso, utc_now
from datetime import timedelta
from integrations.telegram_reader import ReadRequest
from integrations.telegram_web import TelegramWebReader
from nodes.base import NodeContext
from nodes.telegram_web_nodes import TelegramWebReadNode

WORKFLOW = Workflow(name="web_test", title="Тест", steps=(), trigger=Trigger())


def build_page(*, fresh_iso: str, old_iso: str) -> str:
    return f"""
    <html><body>
      <div class="tgme_channel_info_header_title">Медуза — LIVE</div>
      <div class="tgme_widget_message" data-post="meduzalive/100">
        <div class="tgme_widget_message_text js-message_text">
          Старая новость, которая уже не нужна в дайджесте
        </div>
        <time datetime="{old_iso}"></time>
      </div>
      <div class="tgme_widget_message" data-post="meduzalive/101">
        <div class="tgme_widget_message_text js-message_reply_text">Ответ на пост</div>
        <div class="tgme_widget_message_text js-message_text">
          Свежая новость достаточной длины для попадания в сводку
        </div>
        <time datetime="{fresh_iso}"></time>
      </div>
      <div class="tgme_widget_message" data-post="meduzalive/102">
        <div class="tgme_widget_message_text js-message_text">Коротко</div>
        <time datetime="{fresh_iso}"></time>
      </div>
    </body></html>
    """


@pytest.fixture
def page_html(monkeypatch):
    """Отдаёт подготовленную страницу вместо похода в сеть."""
    fresh = to_iso(utc_now() - timedelta(hours=2))
    old = to_iso(utc_now() - timedelta(days=5))
    html = build_page(fresh_iso=fresh, old_iso=old)
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if "/nonexistent" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, text=html)

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return html


async def test_reads_fresh_messages_only(page_html):
    messages = await TelegramWebReader().read(
        ReadRequest(chats=["@meduzalive"], since_hours=24, min_chars=30)
    )
    assert [message.message_id for message in messages] == [101]
    assert messages[0].chat_title == "Медуза — LIVE"
    assert messages[0].link == "https://t.me/meduzalive/101"


async def test_skips_messages_shorter_than_minimum(page_html):
    messages = await TelegramWebReader().read(
        ReadRequest(chats=["@meduzalive"], since_hours=24, min_chars=200)
    )
    assert messages == []


async def test_cursor_prevents_repeats(page_html):
    messages = await TelegramWebReader().read(
        ReadRequest(chats=["@meduzalive"], since_hours=24, min_chars=30,
                    min_ids={"@meduzalive": 101})
    )
    assert messages == []


async def test_missing_channel_raises_telegram_error(page_html):
    with pytest.raises(TelegramError):
        await TelegramWebReader().read(ReadRequest(chats=["@nonexistent"]))


async def test_node_saves_cursor_between_runs(services, page_html):
    context = NodeContext(services=services, workflow=WORKFLOW, step_id="news")
    node = TelegramWebReadNode()
    first = await node.run({"chats": ["@meduzalive"], "min_chars": 30}, context)
    second = await node.run({"chats": ["@meduzalive"], "min_chars": 30}, context)
    assert first.data["count"] == 1
    assert second.data["count"] == 0
    assert await services.kv.get("web_test:news", "last_message_ids") == {"@meduzalive": 101}
