"""Общие фикстуры: временная БД, тестовые ноды, готовое приложение."""

from pathlib import Path

import pytest

import nodes  # noqa: F401 — регистрация штатных нод
from core.config import Settings
from core.engine import Engine
from core.models import StepResult
from core.registry import register
from core.services import Services
from nodes.base import Node, NodeContext


@register("test.echo")
class EchoNode(Node):
    """Возвращает переданный текст."""

    async def run(self, params: dict, context: NodeContext) -> StepResult:
        return StepResult(
            ok=True, text=str(params.get("text", "")), data={"length": len(str(params.get("text", "")))}
        )


@register("test.fail")
class FailNode(Node):
    """Всегда падает — нужен для проверки обработки ошибок."""

    async def run(self, params: dict, context: NodeContext) -> StepResult:
        raise RuntimeError("так задумано")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        # без _env_file тесты подхватили бы личный .env: прокси оттуда уводил
        # запросы мимо подменённого транспорта.
        _env_file=None,
        telegram_proxy=None,   # и не из окружения: запросы идут в подменённый транспорт
        db_path=tmp_path / "test.db",
        telegram_session_path=tmp_path / "session",
        timezone="Asia/Yekaterinburg",
        moodle_url="https://moodle.example",
        moodle_username="student",
        moodle_password="secret",
    )


@pytest.fixture
async def services(settings: Settings):
    container = Services(settings)
    await container.startup()
    yield container
    await container.shutdown()


@pytest.fixture
def engine(services: Services) -> Engine:
    return Engine(services)
