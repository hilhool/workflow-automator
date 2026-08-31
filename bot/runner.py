"""Запуск бота в общем event loop приложения."""

import asyncio
import logging

from aiogram import Dispatcher

from bot.handlers import build_router

logger = logging.getLogger(__name__)


class BotService:
    """Long polling бота как фоновая задача. Без токена просто не стартует."""

    def __init__(self, application):
        self._application = application
        self._dispatcher: Dispatcher | None = None
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._application.settings.telegram_bot_token)

    async def start(self) -> None:
        if not self.enabled:
            logger.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
            return
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(self._application))
        self._dispatcher = dispatcher
        bot = self._application.services.telegram_sender.bot
        await bot.delete_webhook(drop_pending_updates=True)
        self._task = asyncio.create_task(self._poll(dispatcher, bot))
        logger.info("Бот запущен")

    async def _poll(self, dispatcher: Dispatcher, bot) -> None:
        try:
            await dispatcher.start_polling(bot, handle_signals=False)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — падение бота не должно ронять планировщик
            logger.exception("Опрос Telegram прерван")

    async def stop(self) -> None:
        if self._dispatcher is not None:
            await self._dispatcher.stop_polling()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
