"""Работа со временем. Всё, что попадает в БД, хранится в UTC ISO-8601."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Строка UTC ISO-8601 с суффиксом Z."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_iso() -> str:
    return to_iso(utc_now())


def parse_iso(value: str) -> datetime:
    """Разбирает ISO-8601, в том числе с суффиксом Z. Наивное время считаем UTC."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def local_now(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def to_local(moment: datetime, tz_name: str) -> datetime:
    return moment.astimezone(ZoneInfo(tz_name))


def format_local(value: str | datetime, tz_name: str, pattern: str = "%d.%m %H:%M") -> str:
    """Человекочитаемое локальное время для интерфейсов."""
    moment = parse_iso(value) if isinstance(value, str) else value
    return to_local(moment, tz_name).strftime(pattern)


def normalize_due(value: str | None, tz_name: str) -> str | None:
    """Приводит срок из произвольного источника к UTC ISO-8601.

    Модель и Moodle отдают время по-разному: `2026-09-01T09:00:00` без зоны —
    это местное время пользователя, а не UTC. Раньше такой срок уезжал на
    величину смещения (в Екатеринбурге пара в 9:00 показывалась в 14:00).
    Значение с зоной или суффиксом Z остаётся как есть.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw  # не разобрали — сохраняем как пришло, шаг из-за этого не падает
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(tz_name))
    return to_iso(moment)
