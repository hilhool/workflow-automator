"""Извлечение JSON из ответов модели."""

import pytest

from core.errors import NodeExecutionError
from core.jsonparse import extract_json


def test_parses_plain_json():
    assert extract_json('[{"title": "лаба"}]') == [{"title": "лаба"}]


def test_parses_fenced_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parses_json_surrounded_by_text():
    assert extract_json('Вот результат:\n[{"a": 1}]\nГотово.') == [{"a": 1}]


def test_raises_when_no_json_present():
    with pytest.raises(NodeExecutionError):
        extract_json("совсем не json")
