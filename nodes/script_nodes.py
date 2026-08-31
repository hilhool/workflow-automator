"""Нода запуска собственных скриптов.

Скрипты берутся только из data/scripts — так случайный путь из YAML
не превращается в запуск произвольного файла в системе.
"""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

from core.config import USER_SCRIPTS_DIR
from core.errors import DefinitionError, NodeExecutionError
from core.models import StepResult
from core.registry import register
from nodes.base import Node, NodeContext, as_int, as_list, require

_INTERPRETERS = {".py": [sys.executable], ".sh": ["bash"], ".js": ["node"]}


def _resolve_interpreter(suffix: str) -> list[str]:
    """Команда запуска для расширения, найденная в PATH.

    Путь ищется, а не берётся жёстко (`/bin/bash`): на Windows bash приезжает
    вместе с Git и лежит совсем в другом месте, а node ставится как node.cmd,
    которую CreateProcess сама не подставит.
    """
    interpreter = _INTERPRETERS.get(suffix)
    if interpreter is None:
        raise DefinitionError(
            "Неподдерживаемое расширение скрипта",
            context={"suffix": suffix, "supported": sorted(_INTERPRETERS)},
        )
    executable, *rest = interpreter
    if Path(executable).is_absolute():
        return interpreter
    found = shutil.which(executable)
    if found is None:
        raise DefinitionError(
            "Не найден интерпретатор для скрипта",
            context={"suffix": suffix, "need": executable},
        )
    return [found, *rest]


def _resolve_script(name: str) -> Path:
    """Проверяет, что скрипт действительно лежит внутри data/scripts."""
    candidate = (USER_SCRIPTS_DIR / name).resolve()
    scripts_root = USER_SCRIPTS_DIR.resolve()
    if not candidate.is_relative_to(scripts_root):
        raise DefinitionError(
            "Скрипт должен находиться в data/scripts", context={"script": name}
        )
    if not candidate.is_file():
        raise DefinitionError(
            "Скрипт не найден", context={"path": str(candidate)}
        )
    return candidate


@register("script.run")
class ScriptRunNode(Node):
    """Выполняет твой скрипт из data/scripts и возвращает его stdout."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        script = _resolve_script(str(require(params, "script")))
        interpreter = _resolve_interpreter(script.suffix)
        arguments = [str(item) for item in as_list(params.get("args"), param="args")]
        timeout = as_int(params, "timeout_seconds", 120)
        stdout, stderr, code = await self._execute(
            [*interpreter, str(script), *arguments], timeout
        )
        if code != 0:
            raise NodeExecutionError(
                "Скрипт завершился с ошибкой",
                context={"script": script.name, "code": code, "stderr": stderr[:500]},
            )
        return StepResult(
            ok=True, text=stdout.strip(), data={"stderr": stderr.strip(), "code": code}
        )

    @staticmethod
    async def _execute(command: list[str], timeout: int) -> tuple[str, str, int]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(USER_SCRIPTS_DIR),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as error:
            process.kill()
            await process.wait()
            raise NodeExecutionError(
                "Скрипт не уложился в таймаут", context={"timeout_seconds": timeout}
            ) from error
        return (
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
            process.returncode or 0,
        )
