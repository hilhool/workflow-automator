"""Импорт модулей нод регистрирует их в реестре."""

from nodes import (
    claude_nodes,
    http_nodes,
    items_nodes,
    mail_nodes,
    moodle_nodes,
    script_nodes,
    telegram_nodes,
    telegram_unread_nodes,
    telegram_web_nodes,
)

__all__ = [
    "claude_nodes",
    "http_nodes",
    "items_nodes",
    "mail_nodes",
    "moodle_nodes",
    "script_nodes",
    "telegram_nodes",
    "telegram_unread_nodes",
    "telegram_web_nodes",
]
