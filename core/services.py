"""Контейнер зависимостей: одна точка сборки всех подсистем."""

import logging

from core.config import Settings, env_mapping, get_settings
from core.db import Database
from core.store_items import ItemStore
from core.store_kv import KeyValueStore
from core.store_runs import RunStore
from integrations.claude_runner import ClaudeRunner
from integrations.mail_accounts import MailAccount, load_accounts
from integrations.mail_reader import MailReader
from integrations.moodle_client import MoodleClient
from integrations.moodle_scraper import MoodleScraper
from integrations.telegram_reader import TelegramReader
from integrations.telegram_sender import TelegramSender

logger = logging.getLogger(__name__)


class Services:
    """Собирает хранилища и интеграции; ноды получают их через контекст шага."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.db_path)
        self.runs = RunStore(self.db)
        self.items = ItemStore(self.db)
        self.kv = KeyValueStore(self.db)
        self.claude = ClaudeRunner(self.settings)
        self.telegram_reader = TelegramReader(self.settings)
        self.telegram_sender = TelegramSender(self.settings)
        self.moodle = MoodleClient(self.settings, self.kv)
        self.moodle_site = MoodleScraper(self.settings)
        self.mail = MailReader()
        self._mail_accounts: list[MailAccount] | None = None

    @property
    def mail_accounts(self) -> list[MailAccount]:
        """Почтовые ящики из .env, разобранные один раз за процесс."""
        if self._mail_accounts is None:
            self._mail_accounts = load_accounts(env_mapping())
        return self._mail_accounts

    async def startup(self) -> None:
        """Открывает БД и закрывает «висящие» запуски прошлой сессии."""
        self.db.connect()
        interrupted = await self.runs.mark_stale_as_failed()
        if interrupted:
            logger.info("Помечено прерванных запусков: %s", interrupted)

    async def shutdown(self) -> None:
        await self.telegram_reader.stop()
        await self.telegram_sender.close()
        await self.moodle_site.close()
        self.db.close()
