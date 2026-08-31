"""Клиент Moodle и ноды поверх него."""

import json

import httpx
import pytest

from core.errors import MoodleAuthError, MoodleError, MoodleWebServiceUnavailable
from core.models import Trigger, Workflow
from integrations.html_text import find_input_value, html_to_text
from integrations.moodle_client import MoodleClient
from nodes.base import NodeContext
from nodes.moodle_nodes import MoodleDeadlinesNode

WORKFLOW = Workflow(name="moodle_test", title="Тест", steps=(), trigger=Trigger())


@pytest.fixture
def http_routes(monkeypatch):
    """Подменяет httpx.AsyncClient транспортом с ответами из словаря."""
    routes: dict[str, object] = {}
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, payload in routes.items():
            if fragment in str(request.url):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return routes


def make_client(services) -> MoodleClient:
    return MoodleClient(services.settings, services.kv)


async def test_token_is_requested_and_cached(services, http_routes):
    http_routes["login/token.php"] = {"token": "abc123"}
    client = make_client(services)
    assert await client.token() == "abc123"
    assert await services.kv.get("moodle", "token") == "abc123"


async def test_disabled_web_services_raise_dedicated_error(services, http_routes):
    http_routes["login/token.php"] = {
        "error": "Web services are disabled", "errorcode": "enablewsdescription"
    }
    with pytest.raises(MoodleWebServiceUnavailable):
        await make_client(services).token()


async def test_wrong_password_raises_auth_error(services, http_routes):
    http_routes["login/token.php"] = {
        "error": "Invalid login, please try again", "errorcode": "invalidlogin"
    }
    with pytest.raises(MoodleAuthError):
        await make_client(services).token()


async def test_upcoming_parses_events(services, http_routes):
    http_routes["login/token.php"] = {"token": "abc123"}
    http_routes["webservice/rest/server.php"] = {
        "events": [
            {
                "id": 77,
                "name": "Лабораторная 3",
                "timesort": 1788000000,
                "course": {"fullname": "Физика"},
                "url": "https://moodle.example/mod/assign/view.php?id=5",
                "modulename": "assign",
            }
        ]
    }
    events = await make_client(services).upcoming(days=14)
    assert len(events) == 1
    item = events[0].as_item()
    assert item["external_id"] == "moodle-77"
    assert item["title"] == "Физика: Лабораторная 3"
    assert item["due_at"].endswith("Z")


async def test_web_service_exception_becomes_moodle_error(services, http_routes):
    http_routes["login/token.php"] = {"token": "abc123"}
    http_routes["webservice/rest/server.php"] = {
        "exception": "dml_exception", "errorcode": "dmlreadexception", "message": "сломалось"
    }
    with pytest.raises(MoodleError):
        await make_client(services).courses()


async def test_deadlines_node_returns_valid_items_json(services, http_routes):
    http_routes["login/token.php"] = {"token": "abc123"}
    http_routes["webservice/rest/server.php"] = {
        "events": [
            {"id": 1, "name": "Тест", "timesort": 1788000000, "course": {"fullname": "Матан"}}
        ]
    }
    context = NodeContext(services=services, workflow=WORKFLOW, step_id="deadlines")
    result = await MoodleDeadlinesNode().run({"days": 7}, context)
    assert result.data["mode"] == "api"
    assert json.loads(result.data["items_json"])[0]["title"] == "Матан: Тест"


async def test_deadlines_node_falls_back_to_site(services, http_routes, monkeypatch):
    http_routes["login/token.php"] = {
        "error": "Web services are disabled", "errorcode": "enablewsdescription"
    }

    async def fake_fetch(path, **kwargs):
        return "Предстоящие события\nМатан: сдать РГР до 12 мая"

    monkeypatch.setattr(services.moodle_site, "fetch_text", fake_fetch)
    context = NodeContext(services=services, workflow=WORKFLOW, step_id="deadlines")
    result = await MoodleDeadlinesNode().run({}, context)
    assert result.data["mode"] == "html"
    assert "РГР" in result.text
    assert result.data["items_json"] == "[]"


def test_html_to_text_drops_scripts_and_keeps_content():
    html = "<html><head><style>.a{}</style></head><body><script>x=1</script>" \
           "<h1>Задания</h1><p>Сдать до 5 мая</p></body></html>"
    text = html_to_text(html)
    assert "Задания" in text and "Сдать до 5 мая" in text
    assert "x=1" not in text and ".a{}" not in text


def test_html_to_text_respects_limit():
    text = html_to_text("<p>" + "слово " * 5000 + "</p>", limit=200)
    assert len(text) < 300 and text.endswith("(страница обрезана)")


def test_login_token_is_extracted():
    html = '<form><input type="hidden" name="logintoken" value="zx9"></form>'
    assert find_input_value(html, "logintoken") == "zx9"
    assert find_input_value(html, "nonexistent") is None


async def test_node_is_quiet_when_moodle_not_configured(services):
    services.settings.moodle_url = None
    context = NodeContext(services=services, workflow=WORKFLOW, step_id="deadlines")
    result = await MoodleDeadlinesNode().run({}, context)
    assert result.ok and result.skipped
    assert result.data["mode"] == "off"
