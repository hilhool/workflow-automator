"""Клавиатуры бота: постоянное меню внизу экрана и кнопки под списками."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BUTTON_DIGEST = "📰 Дайджест"
BUTTON_MESSAGES = "💬 Кто писал"
BUTTON_MAIL = "📬 Почта"
BUTTON_HOMEWORK = "📚 Домашка"
BUTTON_TODAY = "🗓 Сегодня"
BUTTON_TASKS = "✅ Задачи"

_LAYOUT = (
    (BUTTON_DIGEST, BUTTON_MESSAGES),
    (BUTTON_MAIL, BUTTON_TODAY),
    (BUTTON_HOMEWORK, BUTTON_TASKS),
)


def main_menu() -> ReplyKeyboardMarkup:
    """Постоянное меню — им закрывается почти вся ежедневная рутина."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=title) for title in row] for row in _LAYOUT
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def workflow_buttons(names: dict[str, str]) -> InlineKeyboardMarkup:
    """Кнопки запуска воркфлоу: имя -> заголовок."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"run:{name}")]
            for name, title in names.items()
        ]
    )


def item_buttons(items: list[dict]) -> InlineKeyboardMarkup:
    """Кнопки «закрыть запись» под списком дел."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✔︎ {item['title'][:40]}", callback_data=f"done:{item['id']}"
                )
            ]
            for item in items[:10]
        ]
    )
