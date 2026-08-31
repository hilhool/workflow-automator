"""Запасной путь к Moodle: обычный вход через форму и чтение страниц.

Нужен, когда администратор закрыл веб-сервисы. Данные приходят текстом
страницы — разбирать их дальше будет Claude.
"""

import httpx

from core.config import Settings
from core.errors import MoodleAuthError, MoodleError
from core.net import http_client
from integrations.html_text import find_input_value, html_to_text

LOGIN_PATH = "/login/index.php"
UPCOMING_PATH = "/calendar/view.php?view=upcoming"
_FAILURE_MARKERS = ("invalid login", "неверный логин", "loginerrors", "incorrect username")


class MoodleScraper:
    """Держит сессию с cookies и отдаёт страницы уже в виде текста."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_credentials(self) -> tuple[str, str]:
        settings = self._settings
        if not (settings.moodle_username and settings.moodle_password):
            raise MoodleAuthError(
                "Для входа на сайт нужны MOODLE_USERNAME и MOODLE_PASSWORD",
                context={"fix": "заполни .env"},
            )
        return settings.moodle_username, settings.moodle_password

    async def _session(self) -> httpx.AsyncClient:
        """Возвращает залогиненную сессию, при первом обращении выполняя вход."""
        if self._client is not None:
            return self._client
        username, password = self._require_credentials()
        base = self._settings.moodle_base_url
        client = http_client(self._settings, timeout=45)
        try:
            page = await client.get(f"{base}{LOGIN_PATH}")
            response = await client.post(
                f"{base}{LOGIN_PATH}",
                data={
                    "username": username,
                    "password": password,
                    "logintoken": find_input_value(page.text, "logintoken") or "",
                    "anchor": "",
                },
            )
        except httpx.HTTPError as error:
            await client.aclose()
            raise MoodleError("Сайт Moodle недоступен",
                              context={"url": base, "reason": str(error)[:200]}) from error
        if _login_failed(response.text):
            await client.aclose()
            raise MoodleAuthError("Moodle не принял логин или пароль",
                                  context={"url": f"{base}{LOGIN_PATH}"})
        self._client = client
        return client

    async def fetch_text(self, path: str = UPCOMING_PATH, *, limit: int = 20000) -> str:
        """Текст страницы Moodle по относительному пути."""
        client = await self._session()
        url = f"{self._settings.moodle_base_url}{path}"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise MoodleError("Страница Moodle не открылась",
                              context={"url": url, "reason": str(error)[:200]}) from error
        return html_to_text(response.text, limit=limit)


def _login_failed(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _FAILURE_MARKERS)
