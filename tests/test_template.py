"""Шаблоны в параметрах шагов."""

import pytest

from core.errors import TemplateError
from core.template import render_condition, render_params, render_text

CONTEXT = {"steps": {"news": {"count": 3, "text": "привет"}}, "vars": {"chat": "@one"}}


def test_renders_nested_structures():
    params = {"chats": ["{{ vars.chat }}"], "opts": {"text": "{{ steps.news.text }}"}}
    assert render_params(params, CONTEXT) == {"chats": ["@one"], "opts": {"text": "привет"}}


def test_leaves_plain_values_untouched():
    assert render_params({"limit": 40, "flag": True}, CONTEXT) == {"limit": 40, "flag": True}


def test_condition_true_when_count_positive():
    assert render_condition("{{ steps.news.count > 0 }}", CONTEXT) is True


def test_condition_false_for_empty_text():
    context = {"steps": {"news": {"text": ""}}}
    assert render_condition("{{ steps.news.text }}", context) is False


def test_condition_accepts_bare_expression():
    assert render_condition("steps.news.count > 2", CONTEXT) is True


def test_unknown_variable_raises_template_error():
    with pytest.raises(TemplateError):
        render_text("{{ steps.missing.text }}", CONTEXT)


def test_whole_expression_keeps_native_list():
    """Список в vars должен приходить в ноду списком, а не текстом."""
    context = {"vars": {"channels": ["@one", "@two"]}}
    assert render_params("{{ vars.channels }}", context) == ["@one", "@two"]


def test_whole_expression_keeps_native_number():
    assert render_params("{{ steps.news.count }}", CONTEXT) == 3


def test_expression_inside_text_still_gives_string():
    assert render_params("каналов: {{ steps.news.count }}", CONTEXT) == "каналов: 3"


def test_whole_expression_with_unknown_variable_raises():
    with pytest.raises(TemplateError):
        render_params("{{ vars.missing }}", CONTEXT)
