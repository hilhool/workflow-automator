"""Диагностика подключения к Moodle.

Запуск:  python scripts/moodle_check.py  (в окружении проекта)
Показывает, каким путём система сможет получать дедлайны: через веб-сервисы
или через обычный вход на сайт.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import get_settings  # noqa: E402
from core.db import Database  # noqa: E402
from core.errors import MoodleError, MoodleWebServiceUnavailable  # noqa: E402
from core.store_kv import KeyValueStore  # noqa: E402
from integrations.moodle_client import MoodleClient  # noqa: E402
from integrations.moodle_scraper import MoodleScraper  # noqa: E402


async def check() -> int:
    settings = get_settings()
    if not settings.has_moodle:
        print("Заполни в .env: MOODLE_URL, MOODLE_USERNAME, MOODLE_PASSWORD")
        return 1
    print(f"Сайт: {settings.moodle_base_url}")

    database = Database(settings.db_path)
    database.connect()
    client = MoodleClient(settings, KeyValueStore(database))
    try:
        return await _try_web_service(client, settings)
    except MoodleWebServiceUnavailable as error:
        print(f"\nВеб-сервисы закрыты ({error.context.get('answer', '')}).")
        print("Пробую обычный вход на сайт…")
        return await _try_site(settings)
    except MoodleError as error:
        print(f"\nОшибка: {error}")
        return 1
    finally:
        database.close()


async def _try_web_service(client: MoodleClient, settings) -> int:
    info = await client.site_info()
    print(f"Веб-сервисы работают. Вошёл как {info.get('fullname')} "
          f"({info.get('username')}), сайт «{info.get('sitename')}».")
    courses = await client.courses()
    print(f"\nКурсов: {len(courses)}")
    for course in courses[:10]:
        print(f"  • {course.get('fullname')}")
    events = await client.upcoming(days=30)
    print(f"\nДедлайнов на 30 дней: {len(events)}")
    for event in events[:10]:
        print(f"  • {event.course}: {event.name} — {event.due_iso}")
    print("\nГотово: moodle_sync будет работать через API, разбор Claude не нужен.")
    return 0


async def _try_site(settings) -> int:
    scraper = MoodleScraper(settings)
    try:
        text = await scraper.fetch_text()
    except MoodleError as error:
        print(f"Вход на сайт тоже не удался: {error}")
        return 1
    finally:
        await scraper.close()
    print("Вход на сайт удался. Первые строки страницы предстоящих событий:\n")
    print("\n".join(text.splitlines()[:25]))
    print("\nГотово: moodle_sync будет разбирать эту страницу через Claude.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check()))
