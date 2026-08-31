"""Реестр нод. Нода регистрируется декоратором и доступна по имени из YAML."""

from collections.abc import Callable
from typing import TypeVar

from core.errors import NodeNotFoundError

_registry: dict[str, type] = {}

NodeT = TypeVar("NodeT", bound=type)


def register(name: str) -> Callable[[NodeT], NodeT]:
    """Регистрирует класс ноды под именем, используемым в YAML (`node: telegram.read`)."""

    def decorator(node_class: NodeT) -> NodeT:
        if name in _registry:
            raise RuntimeError(f"Нода {name!r} уже зарегистрирована")
        node_class.name = name
        _registry[name] = node_class
        return node_class

    return decorator


def get_node_class(name: str) -> type:
    if name not in _registry:
        raise NodeNotFoundError(
            "Неизвестный тип шага",
            context={"node": name, "available": sorted(_registry)},
        )
    return _registry[name]


def available_nodes() -> dict[str, str]:
    """Имя ноды -> первая строка её докстроки. Используется веб-панелью."""
    result = {}
    for name, node_class in sorted(_registry.items()):
        doc = (node_class.__doc__ or "").strip().splitlines()
        result[name] = doc[0] if doc else ""
    return result
