"""Ноды Claude: текстовая обработка и агентские вызовы с инструментами."""

from typing import Any

from core.models import StepResult
from core.registry import register
from core.timeutil import local_now
from integrations.claude_runner import DEFAULT_SYSTEM_PROMPT, ClaudeRequest, ClaudeResponse
from nodes.base import Node, NodeContext, as_int, require

_USAGE_NAMESPACE = "usage"


async def _record_usage(context: NodeContext, response: ClaudeResponse) -> None:
    """Копит суточный расход, чтобы видеть нагрузку на лимиты подписки."""
    day = local_now(context.services.settings.timezone).strftime("%Y-%m-%d")
    stats = await context.services.kv.get(_USAGE_NAMESPACE, day, {}) or {}
    stats["calls"] = stats.get("calls", 0) + 1
    stats["input_tokens"] = stats.get("input_tokens", 0) + response.input_tokens
    stats["output_tokens"] = stats.get("output_tokens", 0) + response.output_tokens
    stats["cache_tokens"] = stats.get("cache_tokens", 0) + response.cache_tokens
    stats["cost_usd"] = round(stats.get("cost_usd", 0.0) + response.cost_usd, 4)
    await context.services.kv.set(_USAGE_NAMESPACE, day, stats)


def _result_from(response: ClaudeResponse) -> StepResult:
    return StepResult(
        ok=True,
        text=response.text,
        data={
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cache_tokens": response.cache_tokens,
            "duration_ms": response.duration_ms,
            "cost_usd": response.cost_usd,
        },
    )


@register("claude.prompt")
class ClaudePromptNode(Node):
    """Обрабатывает текст без инструментов — сводка, извлечение, переформулировка."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        request = ClaudeRequest(
            prompt=str(require(params, "prompt")),
            system=str(params.get("system") or DEFAULT_SYSTEM_PROMPT),
            model=str(params.get("model") or "default"),
            timeout_seconds=as_int(
                params, "timeout_seconds", context.services.settings.claude_timeout_seconds
            ),
        )
        response = await context.services.claude.run(request)
        await _record_usage(context, response)
        context.logger.info(
            "claude.prompt: %s токенов на вход, %s на выход",
            response.input_tokens, response.output_tokens,
        )
        return _result_from(response)


@register("claude.agent")
class ClaudeAgentNode(Node):
    """Вызывает Claude с инструментами: MCP-коннекторы, поиск, файлы."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        tools = params.get("tools") or []
        if isinstance(tools, str):
            tools = [tools]
        request = ClaudeRequest(
            prompt=str(require(params, "prompt")),
            system=str(params.get("system") or DEFAULT_SYSTEM_PROMPT),
            model=str(params.get("model") or "default"),
            tools=[str(tool) for tool in tools],
            max_turns=as_int(params, "max_turns", 12),
            timeout_seconds=as_int(params, "timeout_seconds", 600),
        )
        response = await context.services.claude.run(request)
        await _record_usage(context, response)
        return _result_from(response)
