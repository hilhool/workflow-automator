"""Сборка контекста для шаблонов {{ ... }} внутри шагов."""

from datetime import datetime
from typing import Any

from core.models import Workflow
from core.timeutil import local_now, to_iso

WEEKDAYS = (
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
)
MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def describe_moment(moment: datetime) -> dict[str, Any]:
    """Дата в удобном для промптов виде, с русскими названиями."""
    return {
        "iso": to_iso(moment),
        "date": moment.strftime("%Y-%m-%d"),
        "time": moment.strftime("%H:%M"),
        "day": moment.day,
        "month": moment.month,
        "year": moment.year,
        "weekday": WEEKDAYS[moment.weekday()],
        "weekday_index": moment.weekday() + 1,
        "human": f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}",
    }


def build_context(workflow: Workflow, variables: dict[str, Any], tz_name: str) -> dict:
    """Начальный контекст запуска: переменные, время и описание воркфлоу."""
    return {
        "vars": {**workflow.vars, **variables},
        "steps": {},
        "now": describe_moment(local_now(tz_name)),
        "workflow": {"name": workflow.name, "title": workflow.title},
    }
