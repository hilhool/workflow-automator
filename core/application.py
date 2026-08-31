"""Сборка приложения целиком: сервисы, библиотека воркфлоу, движок, планировщик."""

import asyncio
import logging

import nodes  # noqa: F401 — импорт регистрирует ноды в реестре
from core.config import Settings, get_settings
from core.engine import Engine
from core.loader import WorkflowLibrary
from core.scheduler import Scheduler
from core.services import Services

logger = logging.getLogger(__name__)


class Application:
    """Единый объект приложения — им пользуются и веб-панель, и бот, и CLI."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.services = Services(self.settings)
        self.library = WorkflowLibrary()
        self.engine = Engine(self.services)
        self.scheduler = Scheduler(self.services, self.engine, self.library)
        self._catch_up_task: asyncio.Task | None = None

    async def startup(self, *, with_scheduler: bool = True) -> None:
        await self.services.startup()
        loaded = self.library.reload()
        logger.info("Загружено воркфлоу: %s", len(loaded))
        for filename, error in self.library.errors.items():
            logger.error("Файл %s пропущен: %s", filename, error)
        if with_scheduler:
            self.scheduler.start()
            self._catch_up_task = asyncio.create_task(self._catch_up_safely())

    async def _catch_up_safely(self) -> None:
        """Догон пропусков не должен ронять старт приложения."""
        try:
            launched = await self.scheduler.catch_up()
            if launched:
                logger.info("Догнано воркфлоу после простоя: %s", ", ".join(launched))
        except Exception:  # noqa: BLE001
            logger.exception("Догон пропущенных запусков не удался")

    def reload_workflows(self) -> int:
        """Перечитывает YAML и пересобирает расписание."""
        self.library.reload()
        return self.scheduler.sync()

    async def shutdown(self) -> None:
        if self._catch_up_task and not self._catch_up_task.done():
            self._catch_up_task.cancel()
        self.scheduler.shutdown()
        await self.services.shutdown()
