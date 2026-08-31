"""Клиент Moodle через веб-сервисы (REST API мобильного приложения).

Это основной путь: он отдаёт структурированные данные и не ломается от смены
вёрстки. Если администратор закрыл веб-сервисы, бросается
MoodleWebServiceUnavailable — вызывающий переходит на обычный вход через форму.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.config import Settings
from core.errors import MoodleAuthError, MoodleError, MoodleWebServiceUnavailable
from core.timeutil import to_iso, utc_now

_TOKEN_NAMESPACE = "moodle"
_TOKEN_KEY = "token"
_WS_DISABLED_CODES = {"enablewsdescription", "servicenotavailable", "accessexception"}


@dataclass
class MoodleEvent:
    """Событие календаря: сдача задания, тест, дедлайн."""

    event_id: int
    name: str
    course: str
    due_iso: str
    url: str
    module: str

    def as_item(self) -> dict:
        """Формат, который понимает нода items.save."""
        return {
            "external_id": f"moodle-{self.event_id}",
            "title": f"{self.course}: {self.name}" if self.course else self.name,
            "body": self.url,
            "due_at": self.due_iso,
            "module": self.module,
        }


class MoodleClient:
    """Ходит в /webservice/rest/server.php, кеширует токен между запусками."""

    def __init__(self, settings: Settings, kv_store):
        self._settings = settings
        self._kv = kv_store
        self._token: str | None = settings.moodle_token

    async def token(self) -> str:
        """Токен из настроек, из кеша или полученный по логину и паролю."""
        if self._token:
            return self._token
        cached = await self._kv.get(_TOKEN_NAMESPACE, _TOKEN_KEY)
        if cached:
            self._token = str(cached)
            return self._token
        self._token = await self._request_token()
        await self._kv.set(_TOKEN_NAMESPACE, _TOKEN_KEY, self._token)
        return self._token

    async def forget_token(self) -> None:
        """Сбрасывает протухший токен, чтобы следующий вызов получил новый."""
        self._token = self._settings.moodle_token
        await self._kv.delete(_TOKEN_NAMESPACE, _TOKEN_KEY)

    async def _request_token(self) -> str:
        settings = self._settings
        if not (settings.moodle_username and settings.moodle_password):
            raise MoodleAuthError(
                "Не заданы MOODLE_USERNAME и MOODLE_PASSWORD",
                context={"fix": "заполни .env"},
            )
        payload = {
            "username": settings.moodle_username,
            "password": settings.moodle_password,
            "service": settings.moodle_service,
        }
        data = await self._post(f"{settings.moodle_base_url}/login/token.php", payload)
        if "token" in data:
            return str(data["token"])
        error_code = str(data.get("errorcode", ""))
        message = str(data.get("error") or data.get("message") or "неизвестная ошибка")
        if error_code in _WS_DISABLED_CODES or "web service" in message.lower():
            raise MoodleWebServiceUnavailable(
                "Веб-сервисы Moodle недоступны", context={"answer": message}
            )
        raise MoodleAuthError("Moodle не принял логин или пароль",
                              context={"answer": message, "code": error_code})

    async def call(self, function: str, params: dict[str, Any] | None = None) -> Any:
        """Вызов функции веб-сервиса. Протухший токен обновляется один раз."""
        try:
            return await self._call_once(function, params or {})
        except MoodleAuthError:
            await self.forget_token()
            return await self._call_once(function, params or {})

    async def _call_once(self, function: str, params: dict[str, Any]) -> Any:
        payload = {
            "wstoken": await self.token(),
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **_flatten(params),
        }
        url = f"{self._settings.moodle_base_url}/webservice/rest/server.php"
        data = await self._post(url, payload)
        if isinstance(data, dict) and data.get("exception"):
            code = str(data.get("errorcode", ""))
            message = str(data.get("message", ""))
            if code in {"invalidtoken", "accessexception"}:
                raise MoodleAuthError("Токен Moodle недействителен",
                                      context={"code": code, "message": message})
            raise MoodleError("Moodle вернул ошибку",
                              context={"function": function, "code": code, "message": message})
        return data

    async def _post(self, url: str, payload: dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.post(url, data=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as error:
            raise MoodleError("Moodle недоступен",
                              context={"url": url, "reason": str(error)[:200]}) from error
        except ValueError as error:
            raise MoodleError("Moodle ответил не JSON — проверь MOODLE_URL",
                              context={"url": url}) from error

    async def site_info(self) -> dict:
        return await self.call("core_webservice_get_site_info")

    async def courses(self) -> list[dict]:
        info = await self.site_info()
        result = await self.call(
            "core_enrol_get_users_courses", {"userid": info.get("userid")}
        )
        return result if isinstance(result, list) else []

    async def upcoming(self, days: int = 21, limit: int = 50) -> list[MoodleEvent]:
        """Ближайшие дедлайны из календаря."""
        now = utc_now()
        result = await self.call(
            "core_calendar_get_action_events_by_timesort",
            {
                "timesortfrom": int(now.timestamp()),
                "timesortto": int((now + timedelta(days=days)).timestamp()),
                "limitnum": limit,
            },
        )
        events = result.get("events", []) if isinstance(result, dict) else []
        return [_build_event(raw) for raw in events]


def _build_event(raw: dict) -> MoodleEvent:
    course = raw.get("course") or {}
    timestamp = int(raw.get("timesort") or raw.get("timestart") or 0)
    return MoodleEvent(
        event_id=int(raw.get("id", 0)),
        name=str(raw.get("name", "Без названия")),
        course=str(course.get("fullname") or course.get("shortname") or ""),
        due_iso=to_iso(datetime.fromtimestamp(timestamp, tz=timezone.utc)) if timestamp else "",
        url=str(raw.get("url") or raw.get("viewurl") or ""),
        module=str(raw.get("modulename") or ""),
    )


def _flatten(params: dict[str, Any]) -> dict[str, Any]:
    """Moodle ждёт списки в виде name[0]=value — разворачиваем их."""
    flat: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                flat[f"{key}[{index}]"] = item
        else:
            flat[key] = value
    return flat
