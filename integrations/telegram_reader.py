"""Чтение каналов и чатов от имени твоего аккаунта (Telethon).

Боты не видят каналы, на которые ты подписан, поэтому для сбора новостей
и домашки из чата нужен именно клиент аккаунта. Сессия лежит локально
в data/telegram.session и никуда не передаётся.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from telethon import TelegramClient
from telethon.errors import RPCError

from core.config import Settings
from core.errors import TelegramAuthError, TelegramError
from core.timeutil import to_iso, utc_now


@dataclass
class ChatMessage:
    """Одно сообщение из канала или чата."""

    chat: str
    chat_title: str
    message_id: int
    date_iso: str
    text: str
    link: str

    def as_dict(self) -> dict:
        return {
            "chat": self.chat,
            "chat_title": self.chat_title,
            "message_id": self.message_id,
            "date": self.date_iso,
            "text": self.text,
            "link": self.link,
        }


@dataclass
class DialogUpdate:
    """Диалог, в котором есть непрочитанные сообщения."""

    chat_id: int
    title: str
    kind: str
    unread: int
    messages: list[ChatMessage] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "chat_id": self.chat_id, "title": self.title, "kind": self.kind,
            "unread": self.unread,
            "messages": [message.as_dict() for message in self.messages],
        }


@dataclass
class UnreadRequest:
    """Параметры обхода диалогов с непрочитанным."""

    max_dialogs: int = 30
    per_dialog: int = 5
    include_groups: bool = True
    include_channels: bool = False


@dataclass
class ReadRequest:
    """Что и откуда читать."""

    chats: list[str]
    since_hours: int = 24
    limit_per_chat: int = 50
    min_chars: int = 30
    min_ids: dict[str, int] = field(default_factory=dict)


class TelegramReader:
    """Обёртка над Telethon с ленивым подключением."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: TelegramClient | None = None

    def _build_client(self) -> TelegramClient:
        if not self._settings.has_telegram_account:
            raise TelegramAuthError(
                "Не заданы TELEGRAM_API_ID и TELEGRAM_API_HASH",
                context={"fix": "заполни .env, значения берутся на my.telegram.org"},
            )
        return TelegramClient(
            str(self._settings.telegram_session_path),
            self._settings.telegram_api_id,
            self._settings.telegram_api_hash,
        )

    async def start(self) -> None:
        """Подключается к Telegram. Интерактивный вход здесь не запрашивается."""
        if self._client is not None:
            return
        client = self._build_client()
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise TelegramAuthError(
                "Сессия Telegram не авторизована",
                context={"fix": "запусти: ./.venv/bin/python scripts/tg_login.py"},
            )
        self._client = client

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def read(self, request: ReadRequest) -> list[ChatMessage]:
        """Собирает сообщения из указанных чатов, новые — в конце списка."""
        await self.start()
        since = utc_now() - timedelta(hours=request.since_hours)
        collected: list[ChatMessage] = []
        for chat in request.chats:
            collected += await self._read_one(chat, request, since)
        collected.sort(key=lambda message: message.date_iso)
        return collected

    async def _read_one(self, chat: str, request: ReadRequest, since) -> list[ChatMessage]:
        assert self._client is not None
        try:
            entity = await self._client.get_entity(chat)
        except (ValueError, RPCError) as error:
            raise TelegramError(
                "Не удалось открыть чат", context={"chat": chat, "reason": str(error)}
            ) from error
        title = getattr(entity, "title", None) or getattr(entity, "username", chat)
        min_id = request.min_ids.get(chat, 0)
        messages: list[ChatMessage] = []
        async for message in self._client.iter_messages(
            entity, limit=request.limit_per_chat, min_id=min_id
        ):
            if message.date < since:
                break
            text = (message.text or "").strip()
            if len(text) < request.min_chars:
                continue
            messages.append(
                ChatMessage(
                    chat=chat,
                    chat_title=str(title),
                    message_id=message.id,
                    date_iso=to_iso(message.date),
                    text=text,
                    link=self._build_link(entity, message.id),
                )
            )
        return messages

    async def unread(self, request: UnreadRequest) -> list[DialogUpdate]:
        """Диалоги с непрочитанными сообщениями: кто написал и что именно."""
        await self.start()
        assert self._client is not None
        updates: list[DialogUpdate] = []
        async for dialog in self._client.iter_dialogs(limit=request.max_dialogs):
            if not dialog.unread_count or not _wanted(dialog, request):
                continue
            updates.append(await self._describe_dialog(dialog, request))
        return updates

    async def _describe_dialog(self, dialog, request: UnreadRequest) -> DialogUpdate:
        assert self._client is not None
        count = min(dialog.unread_count, request.per_dialog)
        messages = []
        async for message in self._client.iter_messages(dialog.entity, limit=count):
            text = (message.text or "").strip()
            if not text:
                text = "[вложение без текста]"
            messages.append(
                ChatMessage(
                    chat=str(dialog.id),
                    chat_title=dialog.name or "",
                    message_id=message.id,
                    date_iso=to_iso(message.date),
                    text=text,
                    link=self._build_link(dialog.entity, message.id),
                )
            )
        messages.reverse()
        return DialogUpdate(
            chat_id=dialog.id,
            title=dialog.name or "без названия",
            kind=_dialog_kind(dialog),
            unread=dialog.unread_count,
            messages=messages,
        )

    @staticmethod
    def _build_link(entity, message_id: int) -> str:
        username = getattr(entity, "username", None)
        if username:
            return f"https://t.me/{username}/{message_id}"
        return ""


def _dialog_kind(dialog) -> str:
    if dialog.is_user:
        return "личка"
    if dialog.is_group:
        return "группа"
    return "канал"


def _wanted(dialog, request: UnreadRequest) -> bool:
    """Каналы обычно шумят, поэтому по умолчанию считаем только людей и группы."""
    if dialog.is_user:
        return True
    if dialog.is_group:
        return request.include_groups
    return request.include_channels
