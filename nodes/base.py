"""Базовый класс ноды и утилиты разбора параметров."""

import logging
from dataclasses import dataclass
from typing import Any

from core.errors import DefinitionError
from core.models import StepResult, Workflow
from core.services import Services


@dataclass
class NodeContext:
    """Всё, что нода знает о своём окружении."""

    services: Services
    workflow: Workflow
    step_id: str
    run_id: int | None = None
    logger: logging.Logger = logging.getLogger("node")

    @property
    def state_namespace(self) -> str:
        """Пространство имён для состояния конкретного шага конкретного воркфлоу."""
        return f"{self.workflow.name}:{self.step_id}"


class Node:
    """Единица работы. Наследники регистрируются декоратором @register."""

    name: str = ""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        raise NotImplementedError


def require(params: dict[str, Any], key: str) -> Any:
    """Обязательный параметр шага."""
    if key not in params or params[key] in (None, ""):
        raise DefinitionError(
            "В шаге не хватает обязательного параметра",
            context={"param": key, "given": sorted(params)},
        )
    return params[key]


def as_list(value: Any, *, param: str) -> list:
    """Принимает и одиночное значение, и список — в YAML удобно писать по-разному."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, int)):
        return [value]
    raise DefinitionError(
        "Ожидался список", context={"param": param, "type": type(value).__name__}
    )


def as_int(params: dict[str, Any], key: str, default: int) -> int:
    value = params.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise DefinitionError(
            "Параметр должен быть числом", context={"param": key, "value": value}
        ) from error


def as_bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}
