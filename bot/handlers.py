"""Разбор апдейтов Telegram: команды, кнопки меню и свободный текст.

Бот отвечает только владельцу, чей id указан в .env.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import keyboards
from bot.actions import BotActions, Reply
from core.errors import WorkflowError
from integrations.markdown_html import markdown_to_telegram_html, split_message

logger = logging.getLogger(__name__)

HELP_TEXT = """**Кнопки внизу закрывают почти всё.** Ещё есть команды:

/today — занятия и дедлайны на сегодня
/hw — домашка, /tasks — задачи
/mail — сводка почты, /msg — кто писал
/list — все воркфлоу с кнопками запуска
/run <имя> — запустить воркфлоу
/add <текст> — добавить задачу
/done <id> — закрыть запись
/status — что настроено, а что нет

Любое другое сообщение — вопрос к Claude."""

_BUTTON_WORKFLOWS = {
    keyboards.BUTTON_DIGEST: "morning_digest",
    keyboards.BUTTON_MESSAGES: "messages_watch",
    keyboards.BUTTON_MAIL: "mail_digest",
}


def build_router(application) -> Router:
    """Роутер команд, замкнутый на приложение."""
    router = Router()
    actions = BotActions(application)
    owner_id = application.settings.telegram_owner_id

    async def answer(message: Message, reply: Reply) -> None:
        text, markup = reply
        chunks = split_message(markdown_to_telegram_html(text))
        for chunk in chunks[:-1]:
            await message.answer(chunk, disable_web_page_preview=True)
        await message.answer(
            chunks[-1], reply_markup=markup, disable_web_page_preview=True
        )

    async def guarded(message: Message, coroutine) -> None:
        """Ошибка одной команды не должна ронять бота."""
        try:
            await answer(message, await coroutine)
        except WorkflowError as error:
            await message.answer(f"Ошибка: {error}")
        except Exception as error:  # noqa: BLE001
            logger.exception("Обработка сообщения не удалась")
            await message.answer(f"Непредвиденная ошибка: {type(error).__name__}: {error}")

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        if not owner_id:
            # id уходит и в лог: так его можно забрать из data/logs, не переписывая руками.
            logger.info("Команда /start от неизвестного отправителя, id=%s",
                        message.from_user.id)
            await message.answer(
                f"Твой Telegram id: <code>{message.from_user.id}</code>\n"
                "Впиши его в .env как TELEGRAM_OWNER_ID и перезапусти сервис."
            )
            return
        if message.from_user.id != owner_id:
            return
        await message.answer(
            markdown_to_telegram_html(HELP_TEXT),
            reply_markup=keyboards.main_menu(),
        )

    async def reject_strangers(message: Message) -> None:
        logger.warning("Сообщение от постороннего id=%s", message.from_user.id)

    async def reject_stranger_callback(query: CallbackQuery) -> None:
        logger.warning("Нажатие кнопки от постороннего id=%s", query.from_user.id)
        await query.answer("Эта панель не для тебя", show_alert=True)

    if owner_id:
        # Фильтр ставится только когда владелец известен, иначе он отсечёт всех.
        # Кнопки фильтруются отдельно: сообщение с клавиатурой можно переслать.
        router.message.register(reject_strangers, F.from_user.id != owner_id)
        router.callback_query.register(
            reject_stranger_callback, F.from_user.id != owner_id
        )

    @router.message(Command("help", "menu"))
    async def help_command(message: Message) -> None:
        await message.answer(
            markdown_to_telegram_html(HELP_TEXT),
            reply_markup=keyboards.main_menu(),
        )

    @router.message(Command("today"))
    async def today(message: Message) -> None:
        await guarded(message, actions.today())

    @router.message(Command("hw"))
    async def homework(message: Message) -> None:
        await guarded(message, actions.items("homework", "Домашки нет."))

    @router.message(Command("tasks"))
    async def tasks(message: Message) -> None:
        await guarded(message, actions.items("task", "Задач нет."))

    @router.message(Command("list"))
    async def workflow_list(message: Message) -> None:
        await guarded(message, actions.workflow_list())

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        await guarded(message, actions.status())

    @router.message(Command("mail"))
    async def mail(message: Message) -> None:
        await message.answer("Собираю почту…")
        await guarded(message, actions.run_workflow("mail_digest"))

    @router.message(Command("msg"))
    async def messages(message: Message) -> None:
        await message.answer("Смотрю непрочитанное…")
        await guarded(message, actions.run_workflow("messages_watch"))

    @router.message(Command("run"))
    async def run_workflow(message: Message) -> None:
        _, _, name = (message.text or "").partition(" ")
        if not name.strip():
            await guarded(message, actions.workflow_list())
            return
        await message.answer(f"Запускаю {name.strip()}…")
        await guarded(message, actions.run_workflow(name.strip()))

    @router.message(Command("add"))
    async def add_task(message: Message) -> None:
        _, _, text = (message.text or "").partition(" ")
        if not text.strip():
            await message.answer("Напиши, что добавить: /add сдать лабу по физике")
            return
        await guarded(message, actions.add_task(text.strip()))

    @router.message(Command("done"))
    async def done(message: Message) -> None:
        _, _, raw_id = (message.text or "").partition(" ")
        if not raw_id.strip().isdigit():
            await message.answer("Нужен номер записи: /done 12")
            return
        await guarded(message, actions.complete(int(raw_id.strip())))

    @router.message(F.text.in_(_BUTTON_WORKFLOWS))
    async def button_workflow(message: Message) -> None:
        await message.answer("Секунду…")
        await guarded(message, actions.run_workflow(_BUTTON_WORKFLOWS[message.text]))

    @router.message(F.text == keyboards.BUTTON_TODAY)
    async def button_today(message: Message) -> None:
        await guarded(message, actions.today())

    @router.message(F.text == keyboards.BUTTON_HOMEWORK)
    async def button_homework(message: Message) -> None:
        await guarded(message, actions.items("homework", "Домашки нет."))

    @router.message(F.text == keyboards.BUTTON_TASKS)
    async def button_tasks(message: Message) -> None:
        await guarded(message, actions.items("task", "Задач нет."))

    @router.message(F.text)
    async def free_text(message: Message) -> None:
        await guarded(message, actions.ask(message.text))

    @router.callback_query(F.data.startswith("run:"))
    async def callback_run(query: CallbackQuery) -> None:
        name = query.data.removeprefix("run:")
        await query.answer(f"Запускаю {name}")
        await guarded(query.message, actions.run_workflow(name))

    @router.callback_query(F.data.startswith("done:"))
    async def callback_done(query: CallbackQuery) -> None:
        item_id = int(query.data.removeprefix("done:"))
        await query.answer("Закрыто")
        await guarded(query.message, actions.complete(item_id))

    return router
