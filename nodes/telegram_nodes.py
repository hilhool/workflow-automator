"""Ноды Telegram: чтение каналов и чатов, отправка сообщений."""

from typing import Any

from core.models import StepResult
from core.registry import register
from integrations.telegram_reader import ChatMessage, ReadRequest
from nodes.base import Node, NodeContext, as_bool, as_int, as_list, require

_CURSOR_KEY = "last_message_ids"


@register("telegram.read")
class TelegramReadNode(Node):
    """Читает сообщения из каналов и чатов от имени твоего аккаунта."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        chats = [str(chat) for chat in as_list(require(params, "chats"), param="chats")]
        track_cursor = as_bool(params, "track_cursor", default=True)
        cursors = await self._load_cursors(context) if track_cursor else {}
        request = ReadRequest(
            chats=chats,
            since_hours=as_int(params, "since_hours", 24),
            limit_per_chat=as_int(params, "limit_per_chat", 50),
            min_chars=as_int(params, "min_chars", 30),
            min_ids=cursors,
        )
        messages = await context.services.telegram_reader.read(request)
        if track_cursor and messages:
            await self._save_cursors(context, messages, cursors)
        return self._build_result(messages, chats)

    async def _load_cursors(self, context: NodeContext) -> dict[str, int]:
        stored = await context.services.kv.get(context.state_namespace, _CURSOR_KEY, {})
        return {str(chat): int(value) for chat, value in (stored or {}).items()}

    async def _save_cursors(
        self, context: NodeContext, messages: list[ChatMessage], cursors: dict[str, int]
    ) -> None:
        updated = dict(cursors)
        for message in messages:
            previous = updated.get(message.chat, 0)
            updated[message.chat] = max(previous, message.message_id)
        await context.services.kv.set(context.state_namespace, _CURSOR_KEY, updated)

    @staticmethod
    def _build_result(messages: list[ChatMessage], chats: list[str]) -> StepResult:
        blocks = [
            f"[{message.chat_title}] {message.text}" for message in messages
        ]
        return StepResult(
            ok=True,
            text="\n\n---\n\n".join(blocks),
            data={
                "count": len(messages),
                "chats": chats,
                "messages": [message.as_dict() for message in messages],
            },
        )


@register("telegram.send")
class TelegramSendNode(Node):
    """Отправляет текст тебе в Telegram через бота."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        text = str(require(params, "text"))
        header = params.get("header")
        body = f"{header}\n\n{text}" if header else text
        parts = await context.services.telegram_sender.send(
            body, chat_id=params.get("chat_id")
        )
        return StepResult(ok=True, text=body, data={"parts": parts})
