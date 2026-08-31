"""Нода «кто мне написал»: непрочитанные сообщения из личек и групп."""

from typing import Any

from core.models import StepResult
from core.registry import register
from integrations.telegram_reader import DialogUpdate, UnreadRequest
from nodes.base import Node, NodeContext, as_bool, as_int


@register("telegram.unread")
class TelegramUnreadNode(Node):
    """Собирает непрочитанное из личных переписок и групп."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        if not context.services.settings.has_telegram_account:
            return StepResult(
                ok=True, skipped=True,
                text="Доступ к аккаунту Telegram не настроен: нужны TELEGRAM_API_ID и TELEGRAM_API_HASH.",
                data={"count": 0, "dialogs": 0, "updates": []},
            )
        request = UnreadRequest(
            max_dialogs=as_int(params, "max_dialogs", 30),
            per_dialog=as_int(params, "per_dialog", 5),
            include_groups=as_bool(params, "include_groups", default=True),
            include_channels=as_bool(params, "include_channels", default=False),
        )
        updates = await context.services.telegram_reader.unread(request)
        return StepResult(
            ok=True,
            text=_format(updates),
            data={
                "count": sum(update.unread for update in updates),
                "dialogs": len(updates),
                "updates": [update.as_dict() for update in updates],
            },
        )


def _format(updates: list[DialogUpdate]) -> str:
    if not updates:
        return "Непрочитанных сообщений нет."
    blocks = []
    for update in updates:
        head = f"{update.title} ({update.kind}, непрочитанных: {update.unread})"
        body = "\n".join(f"  • {message.text}" for message in update.messages)
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)
