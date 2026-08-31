"""Перевод markdown, который генерирует Claude, в подмножество HTML Telegram.

Telegram понимает только b, i, u, s, code, pre, a и blockquote. Всё остальное
экранируется, поэтому сообщение не может «сломать» разметку.
"""

import html
import re

_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
_UNDERSCORE_ITALIC = re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+)$", re.MULTILINE)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+", re.MULTILINE)


def markdown_to_telegram_html(text: str) -> str:
    """Возвращает строку, безопасную для parse_mode=HTML."""
    placeholders: list[str] = []

    def stash(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_BLOCK.sub(
        lambda match: stash(f"<pre>{html.escape(match.group(1))}</pre>"), text
    )
    text = _INLINE_CODE.sub(
        lambda match: stash(f"<code>{html.escape(match.group(1))}</code>"), text
    )
    text = _LINK.sub(
        lambda match: stash(
            f'<a href="{html.escape(match.group(2), quote=True)}">'
            f"{html.escape(match.group(1))}</a>"
        ),
        text,
    )

    text = html.escape(text)
    text = _HEADING.sub(lambda match: f"<b>{match.group(1)}</b>", text)
    text = _BOLD.sub(lambda match: f"<b>{match.group(1)}</b>", text)
    text = _ITALIC.sub(lambda match: f"<i>{match.group(1)}</i>", text)
    text = _UNDERSCORE_ITALIC.sub(lambda match: f"<i>{match.group(1)}</i>", text)
    text = _BULLET.sub("• ", text)

    for index, rendered in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", rendered)
    return text.strip()


def split_message(text: str, limit: int = 3900) -> list[str]:
    """Режет длинный текст по границам абзацев под лимит Telegram."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks
