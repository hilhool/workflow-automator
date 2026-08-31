"""Нода чтения публичных каналов без авторизации."""

from typing import Any

from core.models import StepResult
from core.registry import register
from integrations.telegram_reader import ReadRequest
from integrations.telegram_web import TelegramWebReader
from nodes.base import Node, NodeContext, as_bool, as_int, as_list, require

_CURSOR_KEY = "last_message_ids"


@register("telegram.web")
class TelegramWebReadNode(Node):
    """Читает публичные каналы через t.me — без api_id и без входа в аккаунт."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        chats = [str(chat) for chat in as_list(require(params, "chats"), param="chats")]
        track_cursor = as_bool(params, "track_cursor", default=True)
        cursors = await self._load_cursors(context) if track_cursor else {}
        request = ReadRequest(
            chats=chats,
            since_hours=as_int(params, "since_hours", 24),
            limit_per_chat=as_int(params, "limit_per_chat", 40),
            min_chars=as_int(params, "min_chars", 30),
            min_ids=cursors,
        )
        reader = TelegramWebReader(
            context.services.settings,
            timeout_seconds=as_int(params, "timeout_seconds", 30),
        )
        messages = await reader.read(request)
        if track_cursor and messages:
            await self._save_cursors(context, messages, cursors)
        return StepResult(
            ok=True,
            text="\n\n---\n\n".join(
                f"[{message.chat_title}] {message.text}" for message in messages
            ),
            data={
                "count": len(messages),
                "chats": chats,
                "messages": [message.as_dict() for message in messages],
            },
        )

    async def _load_cursors(self, context: NodeContext) -> dict[str, int]:
        stored = await context.services.kv.get(context.state_namespace, _CURSOR_KEY, {})
        return {str(chat): int(value) for chat, value in (stored or {}).items()}

    @staticmethod
    async def _save_cursors(context: NodeContext, messages, cursors: dict[str, int]) -> None:
        updated = dict(cursors)
        for message in messages:
            updated[message.chat] = max(updated.get(message.chat, 0), message.message_id)
        await context.services.kv.set(context.state_namespace, _CURSOR_KEY, updated)
