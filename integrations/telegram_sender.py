"""Доставка сообщений тебе в Telegram через бота."""

import html
import re

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from core.config import Settings
from core.errors import ConfigError, TelegramError
from integrations.markdown_html import markdown_to_telegram_html, split_message


class TelegramSender:
    """Отправляет текст владельцу бота, при сбое разметки — простым текстом."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._bot: Bot | None = None

    @property
    def bot(self) -> Bot:
        """Экземпляр бота создаётся при первом обращении."""
        if self._bot is None:
            if not self._settings.telegram_bot_token:
                raise ConfigError(
                    "Не задан TELEGRAM_BOT_TOKEN",
                    context={"fix": "создай бота у @BotFather и впиши токен в .env"},
                )
            proxy = self._settings.proxy_url
            self._bot = Bot(
                token=self._settings.telegram_bot_token,
                # Без явного прокси aiohttp пойдёт напрямую и упрётся в таймаут
                # там, где api.telegram.org закрыт провайдером.
                session=AiohttpSession(proxy=proxy) if proxy else None,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
        return self._bot

    async def close(self) -> None:
        if self._bot is not None:
            await self._bot.session.close()
            self._bot = None

    def _resolve_chat_id(self, chat_id: int | str | None) -> int | str:
        if chat_id:
            return chat_id
        if not self._settings.telegram_owner_id:
            raise ConfigError(
                "Не задан TELEGRAM_OWNER_ID",
                context={"fix": "напиши боту /start — он подскажет твой id"},
            )
        return self._settings.telegram_owner_id

    async def send(self, text: str, *, chat_id: int | str | None = None) -> int:
        """Отправляет текст, разбивая на части. Возвращает число сообщений."""
        target = self._resolve_chat_id(chat_id)
        if not text.strip():
            raise TelegramError("Пустое сообщение не отправляется")
        chunks = split_message(markdown_to_telegram_html(text))
        for chunk in chunks:
            await self._send_chunk(target, chunk)
        return len(chunks)

    async def _send_chunk(self, target: int | str, chunk: str) -> None:
        try:
            await self.bot.send_message(
                target, chunk, disable_web_page_preview=True
            )
        except TelegramAPIError as error:
            if "can't parse entities" not in str(error).lower():
                raise TelegramError(
                    "Telegram отклонил сообщение", context={"reason": str(error)[:300]}
                ) from error
            await self._send_plain(target, chunk, error)

    async def _send_plain(self, target: int | str, chunk: str, cause: Exception) -> None:
        """Запасной путь: если разметка не понравилась Telegram, шлём как есть."""
        plain = html.unescape(re.sub(r"<[^>]+>", "", chunk))
        try:
            await self.bot.send_message(
                target, plain, parse_mode=None, disable_web_page_preview=True
            )
        except TelegramAPIError as error:
            raise TelegramError(
                "Не удалось отправить сообщение даже без разметки",
                context={"reason": str(error)[:300], "original": str(cause)[:200]},
            ) from error
