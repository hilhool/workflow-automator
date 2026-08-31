"""Ноды хранилища записей: сохранение и выборка домашки, задач, пар."""

from datetime import timedelta
from typing import Any

from core.jsonparse import extract_json
from core.models import ItemDraft, StepResult
from core.registry import register
from core.timeutil import format_local, normalize_due, to_iso, utc_now
from nodes.base import Node, NodeContext, as_int, require


def _coerce_items(raw: Any) -> list[dict]:
    """Принимает список, словарь или JSON-текст от модели."""
    parsed = extract_json(raw) if isinstance(raw, str) else raw
    if isinstance(parsed, dict):
        for key in ("items", "tasks", "homework", "data", "result"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


@register("items.save")
class ItemsSaveNode(Node):
    """Сохраняет записи (домашка, задачи, пары) с дедупликацией по внешнему id."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        kind = str(require(params, "kind"))
        source = str(params.get("source") or context.workflow.name)
        entries = _coerce_items(require(params, "data"))
        timezone = context.services.settings.timezone
        saved: list[int] = []
        titles: list[str] = []
        for entry in entries:
            draft = ItemDraft(
                kind=kind,
                source=source,
                title=str(entry.get("title") or entry.get("name") or "Без названия")[:300],
                body=str(entry.get("body") or entry.get("description") or ""),
                due_at=normalize_due(
                    entry.get("due_at") or entry.get("deadline"), timezone
                ),
                external_id=self._external_id(entry),
                payload={
                    key: value
                    for key, value in entry.items()
                    if key not in {"title", "body", "due_at", "external_id"}
                },
            )
            saved.append(await context.services.items.upsert(draft))
            titles.append(self._describe(draft, timezone))
        return StepResult(
            ok=True,
            text="\n".join(titles) or "Сохранять нечего.",
            data={"count": len(saved), "ids": saved, "titles": titles},
        )

    @staticmethod
    def _describe(draft: ItemDraft, timezone: str) -> str:
        """Строка для уведомления: то же, что увидит человек в телеграме."""
        due = f" (до {format_local(draft.due_at, timezone)})" if draft.due_at else ""
        body = f" — {draft.body}" if draft.body else ""
        return f"• {draft.title}{due}{body}"

    @staticmethod
    def _external_id(entry: dict) -> str | None:
        value = entry.get("external_id") or entry.get("id") or entry.get("source_id")
        return str(value) if value is not None else None


@register("items.query")
class ItemsQueryNode(Node):
    """Достаёт открытые записи нужного вида и форматирует их списком."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        kind = str(require(params, "kind"))
        days = as_int(params, "due_within_days", 0)
        store = context.services.items
        if days > 0:
            deadline = to_iso(utc_now() + timedelta(days=days))
            rows = await store.due_before(kind, deadline)
        else:
            rows = await store.list_open(kind, limit=as_int(params, "limit", 50))
        timezone = context.services.settings.timezone
        return StepResult(
            ok=True,
            text=self._format(rows, timezone),
            data={"count": len(rows), "items": rows},
        )

    @staticmethod
    def _format(rows: list[dict], timezone: str) -> str:
        if not rows:
            return "Записей нет."
        lines = []
        for row in rows:
            due = f" (до {format_local(row['due_at'], timezone)})" if row["due_at"] else ""
            body = f" — {row['body']}" if row["body"] else ""
            lines.append(f"• {row['title']}{due}{body}")
        return "\n".join(lines)


@register("items.complete")
class ItemsCompleteNode(Node):
    """Помечает запись выполненной по её id."""

    async def run(self, params: dict[str, Any], context: NodeContext) -> StepResult:
        item_id = as_int(params, "id", 0)
        if not item_id:
            return StepResult(ok=False, text="Не указан id записи")
        await context.services.items.set_status(item_id, "done")
        return StepResult(ok=True, text=f"Запись {item_id} закрыта", data={"id": item_id})
