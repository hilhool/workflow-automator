"""Одноразовый вход в Telegram-аккаунт: создаёт локальную сессию.

Запуск:  python scripts/tg_login.py  (в окружении проекта)
Спросит номер телефона, код из Telegram и пароль двухфакторки, если он есть.
Сессия сохраняется в data/telegram.session и больше не запрашивается.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient  # noqa: E402

from core.config import get_settings  # noqa: E402


async def login() -> int:
    settings = get_settings()
    if not settings.has_telegram_account:
        print("Сначала заполни TELEGRAM_API_ID и TELEGRAM_API_HASH в .env.")
        print("Значения выдаёт https://my.telegram.org -> API development tools")
        return 1
    client = TelegramClient(
        str(settings.telegram_session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.start()
    me = await client.get_me()
    print(f"Готово. Вошёл как {me.first_name} (@{me.username or 'без ника'}).")
    print(f"Сессия: {settings.telegram_session_path}.session")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(login()))
