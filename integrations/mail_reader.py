"""Чтение почты по IMAP.

Ящик открывается только на чтение: письма не помечаются прочитанными
и не изменяются. Пароль нужен «для приложений», обычный пароль от аккаунта
современные сервисы для IMAP не принимают.
"""

import asyncio
import email
import imaplib
from dataclasses import dataclass
from datetime import timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime

from core.errors import MailAuthError, MailError
from core.timeutil import to_iso, utc_now
from integrations.mail_accounts import MailAccount

_TIMEOUT_SECONDS = 40


@dataclass
class MailMessage:
    """Письмо в виде, пригодном для сводки."""

    account: str
    uid: str
    sender: str
    subject: str
    date_iso: str
    body: str
    unread: bool

    def as_dict(self) -> dict:
        return {
            "account": self.account, "uid": self.uid, "sender": self.sender,
            "subject": self.subject, "date": self.date_iso, "unread": self.unread,
            "body": self.body,
        }


@dataclass
class MailRequest:
    """Что забирать из ящика."""

    since_hours: int = 24
    limit: int = 30
    unseen_only: bool = False
    body_chars: int = 1200


class MailReader:
    """Синхронный imaplib, вынесенный в поток, чтобы не блокировать цикл."""

    async def fetch(self, account: MailAccount, request: MailRequest) -> list[MailMessage]:
        return await asyncio.to_thread(self._fetch_sync, account, request)

    def _fetch_sync(self, account: MailAccount, request: MailRequest) -> list[MailMessage]:
        connection = self._connect(account)
        try:
            connection.select(account.folder, readonly=True)
            uids = self._search(connection, request)
            return [
                message
                for uid in uids[-request.limit:]
                if (message := self._load(connection, uid, account, request)) is not None
            ]
        except imaplib.IMAP4.error as error:
            raise MailError(
                "Не удалось прочитать ящик",
                context={"account": account.address, "reason": str(error)[:200]},
            ) from error
        finally:
            _close_quietly(connection)

    @staticmethod
    def _connect(account: MailAccount) -> imaplib.IMAP4_SSL:
        try:
            connection = imaplib.IMAP4_SSL(
                account.host, account.port, timeout=_TIMEOUT_SECONDS
            )
        except OSError as error:
            raise MailError(
                "Почтовый сервер недоступен",
                context={"host": account.host, "reason": str(error)[:200]},
            ) from error
        try:
            connection.login(account.address, account.password)
        except imaplib.IMAP4.error as error:
            _close_quietly(connection)
            raise MailAuthError(
                "Почта не приняла адрес или пароль",
                context={
                    "account": account.address,
                    "reason": str(error)[:200],
                    "hint": "нужен пароль приложения, а не обычный пароль",
                },
            ) from error
        return connection

    @staticmethod
    def _search(connection: imaplib.IMAP4_SSL, request: MailRequest) -> list[bytes]:
        since = (utc_now() - timedelta(hours=request.since_hours)).strftime("%d-%b-%Y")
        criteria = ["SINCE", since]
        if request.unseen_only:
            criteria.insert(0, "UNSEEN")
        status, data = connection.uid("SEARCH", None, *criteria)
        if status != "OK" or not data or data[0] is None:
            return []
        return data[0].split()

    def _load(
        self, connection: imaplib.IMAP4_SSL, uid: bytes,
        account: MailAccount, request: MailRequest,
    ) -> MailMessage | None:
        status, data = connection.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
        if status != "OK" or not data or not isinstance(data[0], tuple):
            return None
        flags = str(data[0][0])
        parsed = email.message_from_bytes(data[0][1])
        return MailMessage(
            account=account.name,
            uid=uid.decode(),
            sender=_decode(parsed.get("From", "")),
            subject=_decode(parsed.get("Subject", "")) or "(без темы)",
            date_iso=_parse_date(parsed.get("Date", "")),
            body=_extract_body(parsed, limit=request.body_chars),
            unread="\\Seen" not in flags,
        )


def _decode(raw: str) -> str:
    try:
        return str(make_header(decode_header(raw))).strip()
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw.strip()


def _parse_date(raw: str) -> str:
    try:
        return to_iso(parsedate_to_datetime(raw))
    except (TypeError, ValueError):
        return ""


def _extract_body(message: Message, *, limit: int) -> str:
    """Только текстовая часть письма, без вложений и HTML-обвязки."""
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_type() != "text/plain":
            continue
        if "attachment" in str(part.get("Content-Disposition", "")):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace").strip()
        return text[:limit]
    return ""


def _close_quietly(connection: imaplib.IMAP4_SSL) -> None:
    try:
        connection.logout()
    except (imaplib.IMAP4.error, OSError):
        pass
