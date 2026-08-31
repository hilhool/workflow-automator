"""Хранилище состояния между запусками: курсоры, отметки времени, флаги."""

import json
from typing import Any

from core.db import Database
from core.timeutil import now_iso


class KeyValueStore:
    """Простое хранилище namespace -> key -> JSON-значение."""

    def __init__(self, database: Database):
        self._db = database

    async def get(self, namespace: str, key: str, default: Any = None) -> Any:
        row = await self._db.query_one(
            "SELECT value FROM kv WHERE namespace = ? AND key = ?", (namespace, key)
        )
        if row is None:
            return default
        return json.loads(row["value"])

    async def set(self, namespace: str, key: str, value: Any) -> None:
        await self._db.execute(
            """
            INSERT INTO kv (namespace, key, value, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value,
                                                      updated_at = excluded.updated_at
            """,
            (namespace, key, json.dumps(value, ensure_ascii=False), now_iso()),
        )

    async def delete(self, namespace: str, key: str) -> None:
        await self._db.execute(
            "DELETE FROM kv WHERE namespace = ? AND key = ?", (namespace, key)
        )

    async def all_in(self, namespace: str) -> dict[str, Any]:
        rows = await self._db.query(
            "SELECT key, value FROM kv WHERE namespace = ?", (namespace,)
        )
        return {row["key"]: json.loads(row["value"]) for row in rows}
