"""Чтение публичных каналов Telegram без авторизации.

Telegram отдаёт ленту публичного канала по адресу t.me/s/<канал> обычной
страницей. Ключи с my.telegram.org для этого не нужны — но и закрытые чаты
так не прочитать, для них нужен TelegramReader.
"""

from datetime import timedelta

import httpx
from bs4 import BeautifulSoup

from core.config import Settings
from core.errors import TelegramError
from core.net import http_client
from core.timeutil import parse_iso, to_iso, utc_now
from integrations.telegram_reader import ChatMessage, ReadRequest

_BASE_URL = "https://t.me/s"
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"


class TelegramWebReader:
    """Разбирает публичную веб-версию канала."""

    def __init__(self, settings: Settings, timeout_seconds: int = 30):
        self._settings = settings
        self._timeout = timeout_seconds

    async def read(self, request: ReadRequest) -> list[ChatMessage]:
        """Собирает сообщения из публичных каналов, новые — в конце списка."""
        since = utc_now() - timedelta(hours=request.since_hours)
        collected: list[ChatMessage] = []
        async with http_client(
            self._settings, timeout=self._timeout, headers={"User-Agent": _USER_AGENT},
        ) as client:
            for chat in request.chats:
                html = await self._fetch(client, chat)
                collected += _parse_channel(html, chat=chat, request=request, since=since)
        collected.sort(key=lambda message: message.date_iso)
        return collected

    async def _fetch(self, client: httpx.AsyncClient, chat: str) -> str:
        handle = chat.lstrip("@").strip("/")
        try:
            response = await client.get(f"{_BASE_URL}/{handle}")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise TelegramError(
                "Не удалось открыть публичную страницу канала",
                context={"chat": chat, "reason": str(error)[:200]},
            ) from error
        return response.text


def _parse_channel(html: str, *, chat: str, request: ReadRequest, since) -> list[ChatMessage]:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.tgme_widget_message[data-post]")
    if not blocks:
        raise TelegramError(
            "На странице канала нет сообщений — проверь имя, канал может быть закрытым",
            context={"chat": chat, "url": f"{_BASE_URL}/{chat.lstrip('@')}"},
        )
    title = _channel_title(soup, chat)
    min_id = request.min_ids.get(chat, 0)
    messages: list[ChatMessage] = []
    for block in blocks[-request.limit_per_chat:]:
        message = _parse_message(block, chat=chat, title=title)
        if message is None or message.message_id <= min_id:
            continue
        if len(message.text) < request.min_chars:
            continue
        if message.date_iso and parse_iso(message.date_iso) < since:
            continue
        messages.append(message)
    return messages


def _parse_message(block, *, chat: str, title: str) -> ChatMessage | None:
    post = block.get("data-post", "")
    _, _, raw_id = post.partition("/")
    if not raw_id.isdigit():
        return None
    text_node = block.select_one("div.tgme_widget_message_text.js-message_text")
    text = text_node.get_text("\n", strip=True) if text_node else ""
    if not text:
        return None
    time_node = block.select_one("time[datetime]")
    date_iso = to_iso(parse_iso(time_node["datetime"])) if time_node else ""
    return ChatMessage(
        chat=chat,
        chat_title=title,
        message_id=int(raw_id),
        date_iso=date_iso,
        text=text,
        link=f"https://t.me/{post}",
    )


def _channel_title(soup: BeautifulSoup, chat: str) -> str:
    node = soup.select_one("div.tgme_channel_info_header_title")
    if node:
        return node.get_text(strip=True)
    meta = soup.select_one('meta[property="og:title"]')
    return meta["content"] if meta and meta.get("content") else chat
