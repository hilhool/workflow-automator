"""Подстановка {{ ... }} в параметрах шагов.

Используется песочница Jinja2: шаблоны описывают данные, а не выполняют код.

Если значение целиком состоит из одного выражения, возвращается настоящий
объект, а не его текстовое представление: `chats: "{{ vars.channels }}"`
должен дать список, а не строку `"['@one']"`.
"""

import re
from typing import Any

from jinja2 import StrictUndefined, Undefined
from jinja2.exceptions import TemplateError as JinjaTemplateError
from jinja2.sandbox import SandboxedEnvironment

from core.errors import TemplateError
from core.timeutil import format_local

_environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
_environment.filters["local_time"] = format_local

_WHOLE_EXPRESSION = re.compile(r"^\s*\{\{(?P<body>.+?)\}\}\s*$", re.DOTALL)


def render_text(template: str, context: dict[str, Any]) -> str:
    """Разворачивает один шаблон в строку."""
    try:
        return _environment.from_string(template).render(**context)
    except JinjaTemplateError as error:
        raise TemplateError(
            "Не удалось развернуть шаблон",
            context={"template": template[:200], "reason": str(error)},
        ) from error


def render_expression(body: str, context: dict[str, Any]) -> Any:
    """Вычисляет одно выражение и возвращает результат как есть — список, число, строку."""
    try:
        evaluate = _environment.compile_expression(body.strip(), undefined_to_none=False)
        result = evaluate(**context)
    except JinjaTemplateError as error:
        raise TemplateError(
            "Не удалось вычислить выражение",
            context={"expression": body[:200], "reason": str(error)},
        ) from error
    if isinstance(result, Undefined):
        raise TemplateError(
            "В выражении используется неизвестная переменная",
            context={"expression": body.strip()[:200]},
        )
    return result


def render_params(value: Any, context: dict[str, Any]) -> Any:
    """Рекурсивно разворачивает шаблоны во всех строках структуры параметров."""
    if isinstance(value, str):
        if "{%" not in value:
            whole = _WHOLE_EXPRESSION.match(value)
            if whole:
                return render_expression(whole.group("body"), context)
        return render_text(value, context) if "{{" in value or "{%" in value else value
    if isinstance(value, dict):
        return {key: render_params(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_params(item, context) for item in value]
    return value


_FALSE_WORDS = {"", "false", "no", "0", "none", "null"}


def render_condition(expression: str, context: dict[str, Any]) -> bool:
    """Вычисляет условие шага `when`. Пустая строка и false-подобные значения — ложь."""
    wrapped = expression if "{{" in expression else "{{ " + expression + " }}"
    rendered = render_text(wrapped, context).strip().lower()
    return rendered not in _FALSE_WORDS
