"""Ноды Moodle: дедлайны, курсы и произвольные страницы.

Каждая нода сначала пробует веб-сервисы. Если они закрыты администратором,
она молча переходит на вход через форму и возвращает текст страницы —
в поле mode видно, каким путём получены данные.
"""

import json
from typing import Any

from core.errors import MoodleWebServiceUnavailable
from core.models import StepResult
from core.registry import register
from core.timeutil import format_local
from integrations.moodle_client import MoodleEvent
from integrations.moodle_scraper import UPCOMING_PATH
from nodes.base import Node, NodeContext, as_int, require


def _not_configured() -> StepResult:
    """Пока Moodle не прописан в .env, шаг тихо ничего не делает."""
    return StepResult(
        ok=True,
        skipped=True,
        text="Moodle не настроен: заполни MOODLE_URL, MOODLE_USERNAME и MOODLE_PASSWORD.",
        data={"mode": "off", "count": 0, "events": [], "items_json": "[]"},
    )


def _format_events(events: list[MoodleEvent], timezone: str) -> str:
    if not events:
        return "Дедлайнов в Moodle нет."
    lines = []
    for event in events:
        due = format_local(event.due_iso, timezone) if event.due_iso else "без срока"
        course = f"{event.course}: " if event.course else ""
        lines.append(f"• {course}{event.name} — до {due}")
    return "\n".join(lines)


@register("moodle.deadlines")
class MoodleDeadlinesNode(Node):
    """Ближайшие дедлайны из календаря Moodle."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        if not context.services.settings.has_moodle:
            return _not_configured()
        days = as_int(params, "days", 21)
        limit = as_int(params, "limit", 50)
        try:
            events = await context.services.moodle.upcoming(days=days, limit=limit)
        except MoodleWebServiceUnavailable:
            context.logger.info("Веб-сервисы Moodle закрыты — читаю сайт как страницу")
            return await self._fallback(context, days)
        timezone = context.services.settings.timezone
        return StepResult(
            ok=True,
            text=_format_events(events, timezone),
            data={
                "mode": "api",
                "count": len(events),
                "events": [event.as_item() for event in events],
                "items_json": json.dumps(
                    [event.as_item() for event in events], ensure_ascii=False
                ),
            },
        )

    @staticmethod
    async def _fallback(context: NodeContext, days: int) -> StepResult:
        text = await context.services.moodle_site.fetch_text(UPCOMING_PATH)
        return StepResult(
            ok=True,
            text=text,
            data={"mode": "html", "count": 0, "events": [], "items_json": "[]",
                  "days": days},
        )


@register("moodle.courses")
class MoodleCoursesNode(Node):
    """Список курсов, на которые ты записан."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        if not context.services.settings.has_moodle:
            return _not_configured()
        try:
            courses = await context.services.moodle.courses()
        except MoodleWebServiceUnavailable:
            text = await context.services.moodle_site.fetch_text("/my/")
            return StepResult(ok=True, text=text, data={"mode": "html", "count": 0})
        names = [str(course.get("fullname") or course.get("shortname")) for course in courses]
        return StepResult(
            ok=True,
            text="\n".join(f"• {name}" for name in names) or "Курсов не найдено.",
            data={"mode": "api", "count": len(names), "courses": names},
        )


@register("moodle.page")
class MoodlePageNode(Node):
    """Открывает любую страницу Moodle и возвращает её текст."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        path = str(require(params, "path"))
        limit = as_int(params, "limit", 20000)
        text = await context.services.moodle_site.fetch_text(path, limit=limit)
        return StepResult(ok=True, text=text, data={"path": path, "length": len(text)})
