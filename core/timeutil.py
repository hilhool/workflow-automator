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
