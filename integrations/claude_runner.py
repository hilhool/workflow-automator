"""Вызов Claude через headless-режим CLI.

Используется подписка Claude Code, а не API-ключ: ключ нигде не нужен.
По умолчанию включён «экономный» режим — урезанный системный промпт,
отключённые инструменты и MCP-серверы. Это снижает расход контекста
примерно в девять раз (33k -> 3.6k токенов на вызов).
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Settings
from core.errors import ClaudeError

_BUILTIN_TOOLS = (
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    "Task", "TodoWrite", "NotebookEdit", "BashOutput", "KillShell", "SlashCommand", "Skill",
)

DEFAULT_SYSTEM_PROMPT = (
    "Ты — исполнительный модуль локального автоматизатора. "
    "Отвечай только результатом, без вступлений, пояснений и предложений помощи."
)


@dataclass
class ClaudeRequest:
    """Параметры одного вызова Claude."""

    prompt: str
    system: str = DEFAULT_SYSTEM_PROMPT
    model: str = "default"
    tools: list[str] = field(default_factory=list)
    max_turns: int = 1
    timeout_seconds: int | None = None
    working_dir: Path | None = None


@dataclass
class ClaudeResponse:
    """Ответ Claude вместе с телеметрией расхода."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0


class ClaudeRunner:
    """Запускает `claude -p` как подпроцесс и разбирает JSON-ответ."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def _resolve_model(self, alias: str) -> str:
        if alias == "fast":
            return self._settings.claude_fast_model
        if alias in ("default", "", None):
            return self._settings.claude_default_model
        return alias

    def _build_command(self, request: ClaudeRequest, model: str) -> list[str]:
        """Собирает аргументы CLI. Без инструментов — экономный режим."""
        command = [
            self._settings.claude_bin,
            "-p", request.prompt,
            "--output-format", "json",
            "--model", model,
            "--system-prompt", request.system,
            "--max-turns", str(request.max_turns),
        ]
        if request.tools:
            # MCP-коннекторы описаны в пользовательских настройках, их нужно прочитать.
            command += [
                "--setting-sources", "user",
                "--allowed-tools", *request.tools,
                "--disallowed-tools", *_BUILTIN_TOOLS,
            ]
        else:
            command += [
                "--setting-sources", "",
                "--strict-mcp-config",
                "--mcp-config", '{"mcpServers":{}}',
                "--allowed-tools", "",
                "--disallowed-tools", *_BUILTIN_TOOLS,
            ]
        return command

    async def run(self, request: ClaudeRequest) -> ClaudeResponse:
        """Выполняет запрос. Бросает ClaudeError при любом неуспехе."""
        model = self._resolve_model(request.model)
        command = self._build_command(request, model)
        timeout = request.timeout_seconds or self._settings.claude_timeout_seconds
        raw = await self._spawn(command, timeout=timeout, cwd=request.working_dir)
        return self._parse(raw, model=model)

    async def _spawn(self, command: list[str], *, timeout: int, cwd: Path | None) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError as error:
            raise ClaudeError(
                "Не найден исполняемый файл Claude CLI",
                context={"bin": self._settings.claude_bin},
            ) from error
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as error:
            process.kill()
            await process.wait()
            raise ClaudeError(
                "Claude не ответил за отведённое время",
                context={"timeout_seconds": timeout},
            ) from error
        if process.returncode != 0:
            raise ClaudeError(
                "Claude CLI завершился с ошибкой",
                context={
                    "returncode": process.returncode,
                    "stderr": stderr.decode("utf-8", "replace")[:500],
                },
            )
        return stdout.decode("utf-8", "replace")

    def _parse(self, raw: str, *, model: str) -> ClaudeResponse:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ClaudeError(
                "Не удалось разобрать ответ Claude CLI", context={"raw": raw[:500]}
            ) from error
        if payload.get("is_error"):
            raise ClaudeError(
                "Claude вернул ошибку",
                context={"result": str(payload.get("result"))[:500]},
            )
        usage = payload.get("usage", {})
        return ClaudeResponse(
            text=(payload.get("result") or "").strip(),
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_tokens=usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0),
            duration_ms=payload.get("duration_api_ms", 0),
            cost_usd=payload.get("total_cost_usd", 0.0),
        )
