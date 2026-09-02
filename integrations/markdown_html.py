"""Перевод markdown, который генерирует Claude, в подмножество HTML Telegram.

Telegram понимает только b, i, u, s, code, pre, a и blockquote. Всё остальное
экранируется, поэтому сообщение не может «сломать» разметку.

Отсюда правило для всего проекта: в YAML воркфлоу, промптах и ответах бота
пишем markdown, а не HTML. HTML из исходников доедет до Telegram видимыми
угловыми скобками — его экранирует то же правило, что защищает от инъекции.
"""

import html
import re

_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
_UNDERSCORE_ITALIC = re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
# Классы [ \t], а не \s: \s матчит и перевод строки, поэтому квантификатор
# отступа съедал пустую строку перед заголовком и абзацы слипались в стену.
_HEADING = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_NESTED_BULLET = re.compile(r"^[ \t]{2,}[-*+][ \t]+", re.MULTILINE)
_BULLET = re.compile(r"^[ \t]{0,1}[-*+][ \t]+", re.MULTILINE)


def _heading(level: int, title: str) -> str:
    """Telegram не знает уровней: первые два даём жирным, остальные курсивом."""
    return f"<b>{title}</b>" if level <= 2 else f"<i>{title}</i>"


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
    text = _HEADING.sub(
        lambda match: _heading(len(match.group(1)), match.group(2)), text
    )
    text = _BOLD.sub(lambda match: f"<b>{match.group(1)}</b>", text)
    text = _ITALIC.sub(lambda match: f"<i>{match.group(1)}</i>", text)
    text = _UNDERSCORE_ITALIC.sub(lambda match: f"<i>{match.group(1)}</i>", text)
    text = _NESTED_BULLET.sub("   ◦ ", text)
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
            current = ""
        pieces = _split_paragraph(paragraph, limit)
        if pieces:
            chunks += pieces[:-1]
            current = pieces[-1]
    if current:
        chunks.append(current)
    return chunks


def _split_paragraph(paragraph: str, limit: int) -> list[str]:
    """Абзац длиннее лимита режем по строкам, в крайнем случае — по словам."""
    pieces: list[str] = []
    current = ""
    for line in paragraph.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
        current = ""
        while len(line) > limit:
            cut = line.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            pieces.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        current = line
    if current:
        pieces.append(current)
    return pieces
