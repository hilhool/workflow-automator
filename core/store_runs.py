"""Журнал запусков: сами запуски, их шаги и время последнего успеха."""

from core.db import Database
from core.timeutil import now_iso


class RunStore:
    """Пишет и читает историю выполнения воркфлоу."""

    def __init__(self, database: Database):
        self._db = database

    async def start_run(self, workflow: str, trigger: str) -> int:
        return await self._db.execute(
            "INSERT INTO runs (workflow, trigger, status, started_at) VALUES (?, ?, 'running', ?)",
            (workflow, trigger, now_iso()),
        )

    async def finish_run(
        self, run_id: int, status: str, *, error_code: str = "", error_message: str = ""
    ) -> None:
        await self._db.execute(
            """
            UPDATE runs SET status = ?, finished_at = ?, error_code = ?, error_message = ?
            WHERE id = ?
            """,
            (status, now_iso(), error_code or None, error_message or None, run_id),
        )

    async def start_step(self, run_id: int, step_id: str, node: str) -> int:
        return await self._db.execute(
            """
            INSERT INTO run_steps (run_id, step_id, node, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (run_id, step_id, node, now_iso()),
        )

    async def finish_step(
        self, row_id: int, status: str, *, output: str = "", error_message: str = ""
    ) -> None:
        await self._db.execute(
            """
            UPDATE run_steps SET status = ?, finished_at = ?, output = ?, error_message = ?
            WHERE id = ?
            """,
            (status, now_iso(), output, error_message or None, row_id),
        )

    async def recent(self, limit: int = 50, workflow: str | None = None) -> list[dict]:
        if workflow:
            return await self._db.query(
                "SELECT * FROM runs WHERE workflow = ? ORDER BY id DESC LIMIT ?",
                (workflow, limit),
            )
        return await self._db.query("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))

    async def get(self, run_id: int) -> dict | None:
        return await self._db.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))

    async def steps_of(self, run_id: int) -> list[dict]:
        return await self._db.query(
            "SELECT * FROM run_steps WHERE run_id = ? ORDER BY id", (run_id,)
        )

    async def last_finished_at(self, workflow: str) -> str | None:
        """Время последнего завершённого запуска — основа для догона пропусков."""
        row = await self._db.query_one(
            """
            SELECT finished_at FROM runs
            WHERE workflow = ? AND status IN ('success', 'failed') AND finished_at IS NOT NULL
            ORDER BY id DESC LIMIT 1
            """,
            (workflow,),
        )
        return row["finished_at"] if row else None

    async def mark_stale_as_failed(self) -> int:
        """Запуски, оборванные выключением машины, помечаются упавшими при старте."""
        return await self._db.execute(
            """
            UPDATE runs SET status = 'failed', finished_at = ?, error_code = 'INTERRUPTED',
                            error_message = 'Процесс был остановлен во время выполнения'
            WHERE status = 'running'
            """,
            (now_iso(),),
        )
