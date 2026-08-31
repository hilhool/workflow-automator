"""Описание почтовых ящиков и автоопределение IMAP-сервера по адресу.

Ящики задаются в .env нумерованными группами, чтобы пароли не попадали
в YAML и в репозиторий:

    MAIL_1_EMAIL=ivan@gmail.com
    MAIL_1_PASSWORD=пароль-приложения
    MAIL_2_EMAIL=ivan@yandex.ru
    MAIL_2_PASSWORD=пароль-приложения
"""

import os
import re
from dataclasses import dataclass

from core.errors import ConfigError

_ENV_PATTERN = re.compile(r"^MAIL_(?P<index>\d+)_EMAIL$")

KNOWN_SERVERS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "yandex.ru": "imap.yandex.ru",
    "yandex.com": "imap.yandex.ru",
    "ya.ru": "imap.yandex.ru",
    "mail.ru": "imap.mail.ru",
    "bk.ru": "imap.mail.ru",
    "inbox.ru": "imap.mail.ru",
    "list.ru": "imap.mail.ru",
    "internet.ru": "imap.mail.ru",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "rambler.ru": "imap.rambler.ru",
    "proton.me": "127.0.0.1",
    "protonmail.com": "127.0.0.1",
}


@dataclass(frozen=True)
class MailAccount:
    """Один почтовый ящик."""

    name: str
    address: str
    password: str
    host: str
    port: int = 993
    folder: str = "INBOX"


def guess_host(address: str) -> str | None:
    """IMAP-сервер по домену адреса. None — домен незнакомый, нужен явный host."""
    _, _, domain = address.partition("@")
    return KNOWN_SERVERS.get(domain.lower().strip())


def load_accounts(environ: dict[str, str] | None = None) -> list[MailAccount]:
    """Собирает ящики из переменных окружения MAIL_<N>_*."""
    source = dict(environ if environ is not None else os.environ)
    indexes = sorted(
        int(match.group("index"))
        for key in source
        if (match := _ENV_PATTERN.match(key)) and source[key].strip()
    )
    return [_build_account(index, source) for index in indexes]


def _build_account(index: int, source: dict[str, str]) -> MailAccount:
    prefix = f"MAIL_{index}_"
    address = source[f"{prefix}EMAIL"].strip()
    password = source.get(f"{prefix}PASSWORD", "").strip()
    if not password:
        raise ConfigError(
            "Для ящика не задан пароль",
            context={"account": address, "variable": f"{prefix}PASSWORD"},
        )
    host = source.get(f"{prefix}HOST", "").strip() or guess_host(address)
    if not host:
        raise ConfigError(
            "Не удалось определить IMAP-сервер по адресу",
            context={"account": address, "variable": f"{prefix}HOST"},
        )
    return MailAccount(
        name=source.get(f"{prefix}NAME", "").strip() or address,
        address=address,
        password=password,
        host=host,
        port=int(source.get(f"{prefix}PORT", "993") or 993),
        folder=source.get(f"{prefix}FOLDER", "").strip() or "INBOX",
    )
