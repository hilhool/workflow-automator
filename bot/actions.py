"""Действия бота: то, что происходит по команде или нажатию кнопки."""

from aiogram.types import InlineKeyboardMarkup

from bot.keyboards import item_buttons, workflow_buttons
from core.models import ItemDraft
from core.timeutil import format_local, local_now, parse_iso, to_local
from integrations.claude_runner import ClaudeRequest

Reply = tuple[str, InlineKeyboardMarkup | None]


class BotActions:
    """Вся прикладная логика бота — без разбора апдейтов Telegram."""

    def __init__(self, application):
        self._application = application

    @property
    def _timezone(self) -> str:
        return self._application.settings.timezone

    async def run_workflow(self, name: str) -> Reply:
        workflow = self._application.library.get(name)
        outcome = await self._application.engine.run(workflow, trigger="bot")
        if not outcome.ok:
            return f"Не получилось: {outcome.error}", None
        return outcome.last_text() or f"«{workflow.title}» отработал, сообщать нечего.", None

    async def items(self, kind: str, empty: str) -> Reply:
        rows = await self._application.services.items.list_open(kind, limit=30)
        if not rows:
            return empty, None
        lines = []
        for row in rows:
            due = f" — до {format_local(row['due_at'], self._timezone)}" if row["due_at"] else ""
            body = f"\n   {row['body']}" if row["body"] else ""
            lines.append(f"{row['id']}. {row['title']}{due}{body}")
        return "\n".join(lines), item_buttons(rows)

    async def today(self) -> Reply:
        """Пары и дедлайны на сегодня, по времени."""
        today = local_now(self._timezone).date()
        lessons = await self._application.services.items.list_open("lesson", limit=100)
        planned = [row for row in lessons if _is_on(row["due_at"], today, self._timezone)]
        homework = await self._application.services.items.list_open("homework", limit=50)
        due_today = [row for row in homework if _is_on(row["due_at"], today, self._timezone)]

        blocks = []
        if planned:
            planned.sort(key=lambda row: row["due_at"] or "")
            blocks.append("**Занятия**\n" + "\n".join(
                f"{format_local(row['due_at'], self._timezone, '%H:%M')} — {row['title']}"
                + (f" ({row['body']})" if row["body"] else "")
                for row in planned
            ))
        if due_today:
            blocks.append("**Сдать сегодня**\n" + "\n".join(
                f"• {row['title']}" for row in due_today
            ))
        if not blocks:
            return "На сегодня ничего не запланировано.", None
        return "\n\n".join(blocks), None

    async def add_task(self, text: str) -> Reply:
        item_id = await self._application.services.items.upsert(
            ItemDraft(kind="task", source="bot", title=text)
        )
        return f"Добавил задачу #{item_id}.", None

    async def complete(self, item_id: int) -> Reply:
        await self._application.services.items.set_status(item_id, "done")
        return f"Запись {item_id} закрыта.", None

    async def ask(self, question: str) -> Reply:
        response = await self._application.services.claude.run(
            ClaudeRequest(prompt=question, model="fast")
        )
        return response.text, None

    async def workflow_list(self) -> Reply:
        workflows = self._application.library.all()
        if not workflows:
            return "Воркфлоу пока нет.", None
        overview = self._application.scheduler.jobs_overview()
        lines = [
            f"• {item.title}" + (f" — след. {overview[name]}" if name in overview else "")
            for name, item in workflows.items()
        ]
        buttons = {name: item.title for name, item in workflows.items() if item.enabled}
        return "**Воркфлоу**\n" + "\n".join(lines), workflow_buttons(buttons)

    async def status(self) -> Reply:
        services = self._application.services
        runs = await services.runs.recent(limit=5)
        settings = self._application.settings
        lines = [
            f"Воркфлоу: {len(self._application.library.all())}",
            f"Аккаунт Telegram: {'подключён' if settings.has_telegram_account else 'нет'}",
            f"Moodle: {'настроен' if settings.has_moodle else 'нет'}",
            f"Почтовых ящиков: {len(services.mail_accounts)}",
        ]
        if self._application.library.errors:
            lines.append(f"Файлов с ошибками: {len(self._application.library.errors)}")
        lines.append("\n**Последние запуски**")
        lines += [
            f"#{run['id']} {run['workflow']} — {run['status']}"
            f" ({format_local(run['started_at'], self._timezone)})"
            for run in runs
        ] or ["запусков не было"]
        return "\n".join(lines), None


def _is_on(due_at: str | None, day, tz_name: str) -> bool:
    """Попадает ли срок на указанный местный день."""
    if not due_at:
        return False
    return to_local(parse_iso(due_at), tz_name).date() == day
