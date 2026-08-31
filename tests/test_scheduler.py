"""Догон запусков, пропущенных пока машина была выключена."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from core.scheduler import last_missed_fire

TZ = ZoneInfo("Asia/Yekaterinburg")
MORNING = CronTrigger.from_crontab("0 8 * * *", timezone=TZ)


def moment(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=TZ)


def test_detects_missed_morning_run():
    missed = last_missed_fire(MORNING, since=moment(10, 22), now=moment(11, 10))
    assert missed == moment(11, 8)


def test_returns_none_when_nothing_was_missed():
    assert last_missed_fire(MORNING, since=moment(11, 9), now=moment(11, 12)) is None


def test_returns_only_the_latest_of_several_missed():
    missed = last_missed_fire(MORNING, since=moment(8, 12), now=moment(11, 10))
    assert missed == moment(11, 8)


def test_interval_shorter_than_period_gives_nothing():
    assert last_missed_fire(MORNING, since=moment(11, 8, 1), now=moment(11, 8, 30)) is None


def test_fire_exactly_at_now_counts_as_missed():
    assert last_missed_fire(MORNING, since=moment(11, 7), now=moment(11, 8)) == moment(11, 8)


def test_grace_window_is_caller_side():
    """Функция возвращает факт пропуска; решение о давности принимает вызывающий."""
    missed = last_missed_fire(MORNING, since=moment(1, 0), now=moment(11, 10))
    assert missed is not None and moment(11, 10) - missed < timedelta(days=1)
