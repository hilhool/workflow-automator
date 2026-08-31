"""Загрузка и валидация YAML-описаний."""

import pytest

from core.errors import DefinitionError, NodeNotFoundError
from core.loader import WorkflowLibrary, load_workflow

VALID = """
name: sample
title: Пример
trigger:
  type: cron
  cron: "0 8 * * *"
steps:
  - id: one
    node: test.echo
    params:
      text: привет
"""


def write(tmp_path, content: str, filename: str = "flow.yaml"):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_valid_workflow(tmp_path):
    workflow = load_workflow(write(tmp_path, VALID))
    assert workflow.name == "sample"
    assert workflow.trigger.cron == "0 8 * * *"
    assert workflow.steps[0].node == "test.echo"


def test_rejects_unknown_node(tmp_path):
    content = VALID.replace("test.echo", "нет.такой.ноды")
    with pytest.raises(NodeNotFoundError):
        load_workflow(write(tmp_path, content))


def test_rejects_invalid_cron(tmp_path):
    content = VALID.replace('"0 8 * * *"', '"каждое утро"')
    with pytest.raises(DefinitionError):
        load_workflow(write(tmp_path, content))


def test_rejects_duplicate_step_ids(tmp_path):
    content = VALID + """
  - id: one
    node: test.echo
    params:
      text: дубль
"""
    with pytest.raises(DefinitionError):
        load_workflow(write(tmp_path, content))


def test_rejects_workflow_without_steps(tmp_path):
    with pytest.raises(DefinitionError):
        load_workflow(write(tmp_path, "name: empty\ntitle: Пусто\n"))


def test_library_survives_broken_file(tmp_path):
    write(tmp_path, VALID, "good.yaml")
    write(tmp_path, "name: bad\nsteps: не список\n", "bad.yaml")
    library = WorkflowLibrary(tmp_path)
    loaded = library.reload()
    assert list(loaded) == ["sample"]
    assert "bad.yaml" in library.errors
