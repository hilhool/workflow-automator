"""Нода HTTP-запроса — источник данных из любого веб-API или страницы."""

from typing import Any

import httpx

from core.errors import NodeExecutionError
from core.models import StepResult
from core.registry import register
from nodes.base import Node, NodeContext, as_int, require

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}


@register("http.request")
class HttpRequestNode(Node):
    """Делает HTTP-запрос и возвращает тело ответа."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        url = str(require(params, "url"))
        method = str(params.get("method", "GET")).upper()
        if method not in _ALLOWED_METHODS:
            raise NodeExecutionError("Метод не поддерживается", context={"method": method})
        timeout = as_int(params, "timeout_seconds", 30)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(
                    method,
                    url,
                    headers=params.get("headers"),
                    json=params.get("json"),
                    data=params.get("body"),
                    params=params.get("query"),
                )
        except httpx.HTTPError as error:
            raise NodeExecutionError(
                "Запрос не выполнен", context={"url": url, "reason": str(error)[:300]}
            ) from error
        if response.status_code >= 400:
            raise NodeExecutionError(
                "Сервер вернул ошибку",
                context={"url": url, "status": response.status_code},
            )
        return StepResult(
            ok=True,
            text=response.text,
            data={"status": response.status_code, "headers": dict(response.headers)},
        )
