"""Ноды почты: сбор писем из всех настроенных ящиков."""

from typing import Any

from core.models import StepResult
from core.registry import register
from core.timeutil import format_local
from integrations.mail_accounts import MailAccount
from integrations.mail_reader import MailMessage, MailRequest
from nodes.base import Node, NodeContext, as_bool, as_int, as_list

_CURSOR_KEY = "last_uids"


@register("mail.fetch")
class MailFetchNode(Node):
    """Забирает письма из всех ящиков, описанных в .env."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        accounts = self._select_accounts(params, context)
        if not accounts:
            return StepResult(
                ok=True, skipped=True,
                text="Почтовые ящики не настроены: добавь MAIL_1_EMAIL и MAIL_1_PASSWORD в .env.",
                data={"count": 0, "messages": [], "accounts": []},
            )
        request = MailRequest(
            since_hours=as_int(params, "since_hours", 24),
            limit=as_int(params, "limit", 30),
            unseen_only=as_bool(params, "unseen_only", default=False),
            body_chars=as_int(params, "body_chars", 1200),
        )
        track_cursor = as_bool(params, "track_cursor", default=True)
        cursors = await self._load_cursors(context) if track_cursor else {}
        messages, failures = await self._collect(accounts, request, cursors, context)
        if track_cursor and messages:
            await self._save_cursors(context, messages, cursors)
        return self._build_result(messages, accounts, failures, context)

    @staticmethod
    def _select_accounts(params: dict[str, Any], context: NodeContext) -> list[MailAccount]:
        wanted = [str(name) for name in as_list(params.get("accounts"), param="accounts")]
        available = context.services.mail_accounts
        if not wanted:
            return available
        return [
            account for account in available
            if account.name in wanted or account.address in wanted
        ]

    async def _collect(
        self, accounts: list[MailAccount], request: MailRequest,
        cursors: dict[str, str], context: NodeContext,
    ) -> tuple[list[MailMessage], list[str]]:
        """Недоступный ящик не должен ронять сводку по остальным."""
        collected: list[MailMessage] = []
        failures: list[str] = []
        for account in accounts:
            try:
                messages = await context.services.mail.fetch(account, request)
            except Exception as error:  # noqa: BLE001 — причина уходит в отчёт шага
                context.logger.warning("Ящик %s недоступен: %s", account.name, error)
                failures.append(f"{account.name}: {error}")
                continue
            last_uid = cursors.get(account.name, "")
            collected += [
                message for message in messages
                if not last_uid or int(message.uid) > int(last_uid)
            ]
        collected.sort(key=lambda message: message.date_iso)
        return collected, failures

    async def _load_cursors(self, context: NodeContext) -> dict[str, str]:
        stored = await context.services.kv.get(context.state_namespace, _CURSOR_KEY, {})
        return {str(name): str(uid) for name, uid in (stored or {}).items()}

    @staticmethod
    async def _save_cursors(
        context: NodeContext, messages: list[MailMessage], cursors: dict[str, str]
    ) -> None:
        updated = dict(cursors)
        for message in messages:
            previous = int(updated.get(message.account, 0) or 0)
            updated[message.account] = str(max(previous, int(message.uid)))
        await context.services.kv.set(context.state_namespace, _CURSOR_KEY, updated)

    @staticmethod
    def _build_result(
        messages: list[MailMessage], accounts: list[MailAccount],
        failures: list[str], context: NodeContext,
    ) -> StepResult:
        timezone = context.services.settings.timezone
        blocks = []
        for message in messages:
            when = format_local(message.date_iso, timezone) if message.date_iso else ""
            blocks.append(
                f"[{message.account}] {when}\n"
                f"От: {message.sender}\nТема: {message.subject}\n{message.body}"
            )
        return StepResult(
            ok=True,
            text="\n\n---\n\n".join(blocks),
            data={
                "count": len(messages),
                "messages": [message.as_dict() for message in messages],
                "accounts": [account.name for account in accounts],
                "failures": failures,
            },
        )
