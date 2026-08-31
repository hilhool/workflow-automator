"""Единая точка создания HTTP-клиентов и окружения для подпроцессов.

Клиенты не читают прокси из окружения (`trust_env=False`), а получают его из
настроек. Иначе поведение зависит от того, из-под чего запущен процесс: в
сессии рабочего стола может лежать socks4-прокси от VPN-клиента, который httpx
не поддерживает, и тогда падает всё, что ходит в сеть, — а из терминала с
другим окружением то же самое работает.
"""

import os
from typing import Any

import httpx

from core.config import Settings

_PROXY_VARIABLES = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def http_client(settings: Settings, **kwargs: Any) -> httpx.AsyncClient:
    """Асинхронный клиент с прокси из настроек."""
    kwargs.setdefault("follow_redirects", True)
    return httpx.AsyncClient(proxy=settings.proxy_url, trust_env=False, **kwargs)


def subprocess_env(settings: Settings) -> dict[str, str]:
    """Окружение для дочернего процесса с согласованным прокси.

    Нужно для Claude CLI: он читает переменные окружения сам, и унаследованный
    socks4-адрес уводит его в никуда.
    """
    environment = dict(os.environ)
    proxy = settings.proxy_url
    if proxy is None:
        return environment
    for name in _PROXY_VARIABLES:
        environment.pop(name, None)
    environment["HTTP_PROXY"] = proxy
    environment["HTTPS_PROXY"] = proxy
    return environment
