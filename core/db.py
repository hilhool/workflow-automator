"""Доступ к SQLite: соединение, схема, низкоуровневые запросы.

Соединение одно на процесс, все обращения сериализуются блокировкой и
выносятся в поток, чтобы не блокировать event loop.
"""

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow, started_at DESC);

CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    node TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    output TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_steps_run ON run_steps(run_id, id);

CREATE TABLE IF NOT EXISTS kv (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (namespace, key)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    body TEXT,
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind, status, due_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_external
    ON items(kind, source, external_id) WHERE external_id IS NOT NULL;
"""


class Database:
    """Тонкая обёртка над sqlite3 с асинхронным интерфейсом."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.commit()
        self._connection = connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Database.connect() не был вызван")
        return self._connection

    def _execute_sync(self, sql: str, params: tuple) -> int:
        connection = self._require_connection()
        with self._lock:
            cursor = connection.execute(sql, params)
            connection.commit()
            return cursor.lastrowid or cursor.rowcount

    def _query_sync(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        connection = self._require_connection()
        with self._lock:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Выполняет запись, возвращает lastrowid (или число затронутых строк)."""
        return await asyncio.to_thread(self._execute_sync, sql, params)

    async def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Выполняет чтение, возвращает список словарей."""
        return await asyncio.to_thread(self._query_sync, sql, params)

    async def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = await self.query(sql, params)
        return rows[0] if rows else None
