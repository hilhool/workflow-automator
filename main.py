"""Точка входа: планировщик, веб-панель и бот в одном процессе.

Запуск:  ./.venv/bin/python main.py
"""

import asyncio
import contextlib
import logging

import uvicorn

from bot.runner import BotService
from core.application import Application
from core.config import get_settings
from core.logging_setup import setup_logging
from web.app import create_web_app

logger = logging.getLogger("main")


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
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_forever())


if __name__ == "__main__":
    main()
