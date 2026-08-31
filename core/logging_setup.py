"""Настройка логов: человекочитаемо в консоль, с ротацией в файл."""

import logging
from logging.handlers import RotatingFileHandler

from core.config import LOGS_DIR

_FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


def setup_logging(level: str = "INFO") -> None:
    """Вызывается один раз при старте процесса."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level.upper())

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOGS_DIR / "workflow.log", maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    for noisy in ("telethon", "aiogram.event", "httpx", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
