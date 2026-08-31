"""Извлечение JSON из ответа модели: она иногда оборачивает его в ```json."""

import json
import re
from typing import Any

from core.errors import NodeExecutionError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Возвращает первый разобравшийся JSON из текста. Бросает NodeExecutionError."""
    candidates = [match.group(1) for match in _FENCE.finditer(text)]
    candidates.append(text)
    candidates += _bracket_slices(text)
    for candidate in candidates:
        stripped = candidate.strip()
        if not stripped:
            continue
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            continue
    raise NodeExecutionError(
        "В ответе модели нет корректного JSON", context={"text": text[:400]}
    )


def _bracket_slices(text: str) -> list[str]:
    """Куски от первой скобки до последней парной — на случай болтовни вокруг JSON."""
    slices = []
    for opening, closing in (("[", "]"), ("{", "}")):
        start = text.find(opening)
        end = text.rfind(closing)
        if start != -1 and end > start:
            slices.append(text[start : end + 1])
    return slices
