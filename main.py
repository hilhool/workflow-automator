"""Точка входа: планировщик, веб-панель и бот в одном процессе.

Запуск:  python main.py  (в окружении проекта: см. README)
"""

import asyncio
import contextlib
import logging
import os
import sys

import uvicorn

from bot.runner import BotService
from core.application import Application
from core.config import get_settings
from core.logging_setup import setup_logging
from web.app import create_web_app

logger = logging.getLogger("main")


def ensure_streams() -> None:
    """Даёт процессу stdout и stderr, если их нет.

    Автозапуск на Windows поднимает службу через pythonw.exe, у которого
    стандартные потоки равны None. uvicorn настраивает своё логирование на
    stdout и падает на этом ещё до старта панели.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    sink = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 — живёт до конца процесса
    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink


async def run_forever() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    application = Application(settings)
    await application.startup()

    bot_service = BotService(application)
    await bot_service.start()

    server = uvicorn.Server(
        uvicorn.Config(
            create_web_app(application),
            host=settings.web_host,
            port=settings.web_port,
            log_level="warning",
            access_log=False,
        )
    )
    logger.info("Панель: http://%s:%s", settings.web_host, settings.web_port)
    try:
        await server.serve()
    finally:
        await bot_service.stop()
        await application.shutdown()
        logger.info("Остановлено")


def main() -> None:
    ensure_streams()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_forever())


if __name__ == "__main__":
    main()
