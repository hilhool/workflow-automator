"""Загрузка воркфлоу из YAML и их валидация."""

import logging
from pathlib import Path

import yaml
from apscheduler.triggers.cron import CronTrigger

from core.config import WORKFLOWS_DIR
from core.errors import DefinitionError
from core.models import Step, Trigger, Workflow
from core.registry import get_node_class

logger = logging.getLogger(__name__)


def load_workflow(path: Path) -> Workflow:
    """Читает один YAML-файл и превращает его в объект Workflow."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise DefinitionError(
            "Файл воркфлоу не разбирается как YAML",
            context={"path": str(path), "reason": str(error)[:300]},
        ) from error
    if not isinstance(raw, dict):
        raise DefinitionError("Воркфлоу должен быть словарём", context={"path": str(path)})

    name = str(raw.get("name") or path.stem)
    steps = _build_steps(raw.get("steps"), path)
    return Workflow(
        name=name,
        title=str(raw.get("title") or name),
        description=str(raw.get("description") or ""),
        enabled=bool(raw.get("enabled", True)),
        vars=dict(raw.get("vars") or {}),
        trigger=_build_trigger(raw.get("trigger"), path),
        steps=steps,
        source_path=str(path),
    )


def _build_steps(raw_steps, path: Path) -> tuple[Step, ...]:
    if not isinstance(raw_steps, list) or not raw_steps:
        raise DefinitionError(
            "У воркфлоу должен быть непустой список steps", context={"path": str(path)}
        )
    steps: list[Step] = []
    seen: set[str] = set()
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise DefinitionError("Шаг должен быть словарём", context={"index": index})
        step_id = str(raw_step.get("id") or f"step_{index + 1}")
        if step_id in seen:
            raise DefinitionError("Идентификаторы шагов должны быть уникальны",
                                  context={"id": step_id, "path": str(path)})
        seen.add(step_id)
        node_name = str(raw_step.get("node") or "")
        get_node_class(node_name)
        steps.append(
            Step(
                id=step_id,
                node=node_name,
                params=dict(raw_step.get("params") or {}),
                when=raw_step.get("when"),
                continue_on_error=bool(raw_step.get("continue_on_error", False)),
            )
        )
    return tuple(steps)


def _build_trigger(raw_trigger, path: Path) -> Trigger:
    if raw_trigger is None:
        return Trigger()
    if not isinstance(raw_trigger, dict):
        raise DefinitionError("trigger должен быть словарём", context={"path": str(path)})
    trigger_type = str(raw_trigger.get("type") or "manual")
    cron = raw_trigger.get("cron")
    if trigger_type == "cron":
        if not cron:
            raise DefinitionError("Для trigger.type=cron нужно поле cron",
                                  context={"path": str(path)})
        _validate_cron(str(cron), path)
    if trigger_type == "interval" and not raw_trigger.get("minutes"):
        raise DefinitionError("Для trigger.type=interval нужно поле minutes",
                              context={"path": str(path)})
    return Trigger(
        type=trigger_type,
        cron=str(cron) if cron else None,
        minutes=raw_trigger.get("minutes"),
        event=raw_trigger.get("event"),
        catch_up=bool(raw_trigger.get("catch_up", True)),
    )


def _validate_cron(expression: str, path: Path) -> None:
    try:
        CronTrigger.from_crontab(expression)
    except ValueError as error:
        raise DefinitionError(
            "Некорректное cron-выражение",
            context={"cron": expression, "path": str(path), "reason": str(error)},
        ) from error


class WorkflowLibrary:
    """Набор воркфлоу из каталога с возможностью перечитать их на лету."""

    def __init__(self, directory: Path = WORKFLOWS_DIR):
        self._directory = directory
        self._workflows: dict[str, Workflow] = {}
        self.errors: dict[str, str] = {}

    def reload(self) -> dict[str, Workflow]:
        """Перечитывает каталог. Битые файлы не роняют остальные."""
        workflows: dict[str, Workflow] = {}
        errors: dict[str, str] = {}
        for path in sorted(self._directory.glob("*.y*ml")):
            try:
                workflow = load_workflow(path)
            except DefinitionError as error:
                errors[path.name] = str(error)
                logger.error("Воркфлоу %s не загружен: %s", path.name, error)
                continue
            workflows[workflow.name] = workflow
        self._workflows = workflows
        self.errors = errors
        return workflows

    def all(self) -> dict[str, Workflow]:
        return dict(self._workflows)

    def get(self, name: str) -> Workflow:
        if name not in self._workflows:
            raise DefinitionError("Воркфлоу не найден", context={"name": name})
        return self._workflows[name]
