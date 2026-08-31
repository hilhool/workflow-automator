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


def test_unsupported_proxy_scheme_is_ignored():
    """socks4 не умеют ни httpx, ни aiohttp — такой прокси хуже, чем никакого."""
    settings = Settings(_env_file=None, telegram_proxy="socks4://127.0.0.1:10808")
    assert settings.proxy_url is None


def test_supported_proxy_schemes_pass_through():
    for value in ("http://user:pass@host:3128", "socks5://127.0.0.1:1080"):
        assert Settings(_env_file=None, telegram_proxy=value).proxy_url == value


def test_proxy_is_optional():
    assert Settings(_env_file=None, telegram_proxy=None).proxy_url is None
    assert Settings(_env_file=None, telegram_proxy="  ").proxy_url is None
