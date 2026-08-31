"""Приведение сроков к UTC."""

from core.timeutil import format_local, normalize_due

TZ = "Asia/Yekaterinburg"  # UTC+5, без перехода на летнее время


def test_naive_value_is_local_time():
    """Модель отдаёт срок без зоны — это местное время, а не UTC."""
    assert normalize_due("2026-09-01T09:00:00", TZ) == "2026-09-01T04:00:00Z"


def test_naive_value_survives_round_trip():
    stored = normalize_due("2026-09-01T09:00:00", TZ)
    assert format_local(stored, TZ, "%H:%M") == "09:00"


def test_value_with_zone_is_kept():
    assert normalize_due("2026-09-01T09:00:00Z", TZ) == "2026-09-01T09:00:00Z"
    assert normalize_due("2026-09-01T09:00:00+03:00", TZ) == "2026-09-01T06:00:00Z"


def test_empty_and_missing_become_none():
    assert normalize_due(None, TZ) is None
    assert normalize_due("   ", TZ) is None


def test_unparsable_value_is_kept_as_is():
    """Разбор не удался — шаг из-за этого падать не должен."""
    assert normalize_due("на следующей неделе", TZ) == "на следующей неделе"
