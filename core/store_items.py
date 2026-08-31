"""Хранилище прикладных записей: домашка, задачи, пары, заметки."""

import json

from core.db import Database
from core.models import ItemDraft
from core.timeutil import now_iso


class ItemStore:
    """CRUD поверх таблицы items с дедупликацией по external_id."""

    def __init__(self, database: Database):
        self._db = database

    async def upsert(self, draft: ItemDraft) -> int:
        """Добавляет запись; повтор с тем же external_id обновляет существующую."""
        moment = now_iso()
        payload = json.dumps(draft.payload, ensure_ascii=False)
        if draft.external_id:
            existing = await self._db.query_one(
                "SELECT id FROM items WHERE kind = ? AND source = ? AND external_id = ?",
                (draft.kind, draft.source, draft.external_id),
            )
            if existing:
                await self._update_existing(existing["id"], draft, payload, moment)
                return existing["id"]
        return await self._db.execute(
            """
            INSERT INTO items
                (kind, source, external_id, title, body, due_at, status, payload,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.kind, draft.source, draft.external_id, draft.title, draft.body,
                draft.due_at, draft.status, payload, moment, moment,
            ),
        )

    async def _update_existing(
        self, item_id: int, draft: ItemDraft, payload: str, moment: str
    ) -> None:
        await self._db.execute(
            """
            UPDATE items SET title = ?, body = ?, due_at = ?, payload = ?, updated_at = ?
            WHERE id = ?
            """,
            (draft.title, draft.body, draft.due_at, payload, moment, item_id),
        )

    async def list_open(self, kind: str, limit: int = 50) -> list[dict]:
        return await self._db.query(
            """
            SELECT * FROM items WHERE kind = ? AND status = 'open'
            ORDER BY due_at IS NULL, due_at, id DESC LIMIT ?
            """,
            (kind, limit),
        )

    async def list_recent(self, limit: int = 100) -> list[dict]:
        return await self._db.query(
            "SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,)
        )

    async def set_status(self, item_id: int, status: str) -> None:
        await self._db.execute(
            "UPDATE items SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), item_id),
        )

    async def due_before(self, kind: str, deadline_iso: str) -> list[dict]:
        return await self._db.query(
            """
            SELECT * FROM items
            WHERE kind = ? AND status = 'open' AND due_at IS NOT NULL AND due_at <= ?
            ORDER BY due_at
            """,
            (kind, deadline_iso),
        )
