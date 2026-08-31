"""Показывает диалоги аккаунта, чтобы взять точные имена каналов для YAML.

Запуск:  ./.venv/bin/python scripts/list_chats.py [подстрока]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient  # noqa: E402

from core.config import get_settings  # noqa: E402


async def show(needle: str = "") -> int:
    settings = get_settings()
    client = TelegramClient(
        str(settings.telegram_session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
    await client.connect()
    if not await client.is_user_authorized():
        print("Нет сессии. Сначала: ./.venv/bin/python scripts/tg_login.py")
        await client.disconnect()
        return 1
    async for dialog in client.iter_dialogs():
        title = dialog.name or ""
        if needle and needle.lower() not in title.lower():
            continue
        username = getattr(dialog.entity, "username", None)
        handle = f"@{username}" if username else str(dialog.id)
        kind = "канал" if dialog.is_channel else ("группа" if dialog.is_group else "личка")
        print(f"{handle:<28} {kind:<8} {title}")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(show(sys.argv[1] if len(sys.argv) > 1 else "")))
