"""Превращение страницы Moodle в компактный текст.

Отдавать модели сырой HTML расточительно: страница курса весит сотни килобайт,
из которых полезны единицы процентов. Здесь остаётся только видимый текст.
"""

import re

from bs4 import BeautifulSoup

_DROP_TAGS = ("script", "style", "noscript", "svg", "head", "nav", "footer", "form")
_BLANK_LINES = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]{2,}")


def html_to_text(html: str, *, limit: int = 20000) -> str:
    """Видимый текст страницы, схлопнутый по пробелам и обрезанный до лимита."""
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = _SPACES.sub(" ", _BLANK_LINES.sub("\n\n", text))
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n… (страница обрезана)"


def find_input_value(html: str, name: str) -> str | None:
    """Значение скрытого поля формы — нужно для logintoken при входе."""
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("input", attrs={"name": name})
    if field is None:
        return None
    value = field.get("value")
    return str(value) if value else None


def has_text(html: str, needle: str) -> bool:
    return needle.lower() in html.lower()
