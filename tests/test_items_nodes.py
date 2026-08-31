"""Ноды хранилища записей: что сохраняется и что уходит в уведомление."""

import json

from core.models import Step, Trigger, Workflow


def build_workflow(*steps: Step, name: str = "items_flow") -> Workflow:
    return Workflow(name=name, title="Тест", steps=steps, trigger=Trigger())


async def test_save_normalizes_naive_deadline_to_utc(engine, services):
    """Часовой пояс фикстур — UTC+5, значит 09:00 местного это 04:00 UTC."""
    data = json.dumps([{"title": "Матанализ", "due_at": "2026-09-01T09:00:00"}])
    workflow = build_workflow(
        Step(id="save", node="items.save", params={"kind": "homework", "data": data})
    )
    outcome = await engine.run(workflow)
    assert outcome.ok

    rows = await services.items.list_open("homework")
    assert rows[0]["due_at"] == "2026-09-01T04:00:00Z"


async def test_save_returns_readable_list_not_json(engine):
    """Текст шага уходит прямо в телеграм — сырой JSON там не нужен."""
    data = json.dumps([
        {"title": "Физика, лаба 3", "due_at": "2026-09-01T09:00:00"},
        {"title": "Английский, эссе"},
    ])
    workflow = build_workflow(
        Step(id="save", node="items.save", params={"kind": "homework", "data": data})
    )
    outcome = await engine.run(workflow)
    text = outcome.results["save"].text
    assert text.startswith("• Физика, лаба 3 (до 01.09 09:00)")
    assert "• Английский, эссе" in text
    assert "{" not in text


async def test_save_reports_nothing_to_save(engine):
    workflow = build_workflow(
        Step(id="save", node="items.save", params={"kind": "task", "data": "[]"})
    )
    outcome = await engine.run(workflow)
    assert outcome.results["save"].text == "Сохранять нечего."
    assert outcome.results["save"].data["count"] == 0


async def test_query_finds_item_by_deadline_window(engine, services):
    """Срок в местном времени должен попадать в окно due_within_days."""
    from core.timeutil import local_now, normalize_due
    from datetime import timedelta

    soon = (local_now("Asia/Yekaterinburg") + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    data = json.dumps([{"title": "Скоро сдавать", "due_at": soon}])
    workflow = build_workflow(
        Step(id="save", node="items.save", params={"kind": "homework", "data": data}),
        Step(id="soon", node="items.query",
             params={"kind": "homework", "due_within_days": 2}),
        Step(id="later", node="items.query",
             params={"kind": "homework", "due_within_days": 0}),
    )
    outcome = await engine.run(workflow)
    assert outcome.results["soon"].data["count"] == 1
    assert normalize_due(soon, "Asia/Yekaterinburg").endswith("Z")
