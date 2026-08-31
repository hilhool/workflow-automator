"""Разбор писем: заголовки, кодировки, текстовая часть."""

import email

from integrations.mail_reader import _decode, _extract_body, _parse_date

MULTIPART = """From: =?utf-8?B?0JjQstCw0L0=?= <ivan@example.com>
Subject: =?utf-8?B?0JTQtdC00LvQsNC50L0=?=
Date: Fri, 29 Aug 2026 10:15:00 +0500
Content-Type: multipart/mixed; boundary="sep"

--sep
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 8bit

Привет, нужен ответ до пятницы.
--sep
Content-Type: application/pdf; name="doc.pdf"
Content-Disposition: attachment; filename="doc.pdf"

JVBERi0=
--sep--
"""


def parse(raw: str):
    """Как в бою: письмо приходит байтами, иначе кодировки разбираются неверно."""
    return email.message_from_bytes(raw.encode("utf-8"))


def test_decodes_encoded_headers():
    message = parse(MULTIPART)
    assert _decode(message.get("Subject")) == "Дедлайн"
    assert "Иван" in _decode(message.get("From"))


def test_extracts_plain_text_and_skips_attachments():
    body = _extract_body(parse(MULTIPART), limit=1000)
    assert body.startswith("Привет, нужен ответ")
    assert "JVBERi0" not in body


def test_body_is_truncated_to_limit():
    raw = "Subject: x\nContent-Type: text/plain; charset=utf-8\n\n" + "а" * 500
    assert len(_extract_body(parse(raw), limit=100)) == 100


def test_date_is_converted_to_utc_iso():
    assert _parse_date("Fri, 29 Aug 2026 10:15:00 +0500") == "2026-08-29T05:15:00Z"


def test_broken_date_gives_empty_string():
    assert _parse_date("вчера вечером") == ""


def test_message_without_text_part_gives_empty_body():
    raw = "Subject: x\nContent-Type: text/html; charset=utf-8\n\n<p>привет</p>"
    assert _extract_body(parse(raw), limit=100) == ""
