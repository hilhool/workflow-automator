"""Разбор описаний почтовых ящиков из окружения."""

import pytest

from core.errors import ConfigError
from integrations.mail_accounts import guess_host, load_accounts


def test_loads_several_accounts_in_order():
    accounts = load_accounts({
        "MAIL_2_EMAIL": "second@yandex.ru", "MAIL_2_PASSWORD": "b",
        "MAIL_1_EMAIL": "first@gmail.com", "MAIL_1_PASSWORD": "a",
    })
    assert [account.address for account in accounts] == ["first@gmail.com", "second@yandex.ru"]
    assert accounts[0].host == "imap.gmail.com"
    assert accounts[1].host == "imap.yandex.ru"


def test_empty_environment_gives_no_accounts():
    assert load_accounts({}) == []


def test_blank_email_is_ignored():
    assert load_accounts({"MAIL_1_EMAIL": "   ", "MAIL_1_PASSWORD": "x"}) == []


def test_missing_password_is_a_config_error():
    with pytest.raises(ConfigError):
        load_accounts({"MAIL_1_EMAIL": "a@gmail.com"})


def test_unknown_domain_requires_explicit_host():
    with pytest.raises(ConfigError):
        load_accounts({"MAIL_1_EMAIL": "a@corp.local", "MAIL_1_PASSWORD": "x"})


def test_explicit_host_overrides_guess():
    accounts = load_accounts({
        "MAIL_1_EMAIL": "a@corp.local", "MAIL_1_PASSWORD": "x",
        "MAIL_1_HOST": "mail.corp.local", "MAIL_1_PORT": "1993",
        "MAIL_1_NAME": "Работа", "MAIL_1_FOLDER": "Inbox",
    })
    assert accounts[0].host == "mail.corp.local"
    assert accounts[0].port == 1993
    assert accounts[0].name == "Работа"
    assert accounts[0].folder == "Inbox"


def test_guess_host_is_case_insensitive():
    assert guess_host("Ivan@Yandex.RU") == "imap.yandex.ru"
    assert guess_host("ivan@unknown.tld") is None
