"""Настройки приложения. Единственный источник конфигурации — .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
USER_SCRIPTS_DIR = DATA_DIR / "scripts"


class Settings(BaseSettings):
    """Конфигурация, читаемая из .env. Секретов в коде нет по определению."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_bot_token: str | None = None
    telegram_owner_id: int | None = None

    moodle_url: str | None = None
    moodle_username: str | None = None
    moodle_password: str | None = None
    moodle_token: str | None = None
    moodle_service: str = "moodle_mobile_app"

    claude_bin: str = "claude"
    claude_default_model: str = "claude-sonnet-5"
    claude_fast_model: str = "claude-haiku-4-5-20251001"
    claude_timeout_seconds: int = 300

    web_host: str = "127.0.0.1"
    web_port: int = 8765

    timezone: str = "Asia/Yekaterinburg"
    catch_up_grace_minutes: int = 720

    log_level: str = "INFO"
    db_path: Path = Field(default=DATA_DIR / "workflow.db")
    telegram_session_path: Path = Field(default=DATA_DIR / "telegram")

    @field_validator(
        "telegram_api_id", "telegram_api_hash", "telegram_bot_token", "telegram_owner_id",
        "moodle_url", "moodle_username", "moodle_password", "moodle_token",
        mode="before",
    )
    @classmethod
    def empty_string_means_not_set(cls, value: object) -> object:
        """В .env незаполненный параметр выглядит как `KEY=` — это значит «не задано»."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def has_telegram_account(self) -> bool:
        return bool(self.telegram_api_id and self.telegram_api_hash)

    @property
    def has_telegram_bot(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_owner_id)

    @property
    def has_moodle(self) -> bool:
        credentials = self.moodle_token or (self.moodle_username and self.moodle_password)
        return bool(self.moodle_url and credentials)

    @property
    def moodle_base_url(self) -> str:
        """URL без завершающего слэша — к нему приклеиваются пути."""
        return (self.moodle_url or "").rstrip("/")


def env_mapping() -> dict[str, str]:
    """Переменные из .env, поверх которых наложено окружение процесса.

    Нужна для настроек с произвольным числом записей — например почтовых
    ящиков MAIL_1_*, MAIL_2_*, которые не описать полями модели.
    """
    import os

    values: dict[str, str] = {}
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    values.update(os.environ)
    return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки читаются один раз за процесс."""
    for directory in (DATA_DIR, LOGS_DIR, WORKFLOWS_DIR, USER_SCRIPTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    return Settings()
