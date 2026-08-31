"""Разбор настроек из .env."""

from core.config import Settings


def test_empty_values_are_treated_as_unset():
    settings = Settings(
        _env_file=None, telegram_api_id="", telegram_api_hash="",
        telegram_bot_token="", telegram_owner_id="",
    )
    assert settings.telegram_api_id is None
    assert settings.has_telegram_account is False
    assert settings.has_telegram_bot is False


def test_filled_values_enable_features():
    settings = Settings(
        _env_file=None, telegram_api_id="123", telegram_api_hash="hash",
        telegram_bot_token="token", telegram_owner_id="42",
    )
    assert settings.telegram_api_id == 123
    assert settings.has_telegram_account is True
    assert settings.has_telegram_bot is True
