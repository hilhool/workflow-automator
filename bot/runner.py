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
        try:
            # Создание бота тоже может упасть — например если для прокси
            # не хватает aiohttp-socks. Поэтому оно внутри try, а не снаружи.
            bot = self._application.services.telegram_sender.bot
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception as error:  # noqa: BLE001 — бот не главный, планировщик важнее
            # Чаще всего это закрытый провайдером api.telegram.org: пропиши
            # TELEGRAM_PROXY в .env. Ронять из-за этого расписание и панель нельзя.
            logger.error("Бот не поднялся (%s) — планировщик и панель работают без него",
                         error)
            await self._application.services.telegram_sender.close()
            return
        self._dispatcher = dispatcher
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
