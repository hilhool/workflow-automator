"""Планировщик: cron-запуски и догон того, что было пропущено во сне машины."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.engine import Engine
from core.loader import WorkflowLibrary
from core.models import Workflow
from core.services import Services
from core.timeutil import parse_iso

logger = logging.getLogger(__name__)


def last_missed_fire(
    trigger: CronTrigger, since: datetime, now: datetime
) -> datetime | None:
    """Последнее срабатывание cron в интервале (since, now]. None — пропусков не было."""
    fire = trigger.get_next_fire_time(None, since)
    latest = None
    guard = 0
    while fire is not None and fire <= now and guard < 5000:
        latest = fire
        fire = trigger.get_next_fire_time(fire, fire + timedelta(seconds=1))
        guard += 1
    return latest


class Scheduler:
    """Держит расписание в актуальном состоянии и переживает сон/выключение."""

    def __init__(self, services: Services, engine: Engine, library: WorkflowLibrary):
        self._services = services
        self._engine = engine
        self._library = library
        self._timezone = ZoneInfo(services.settings.timezone)
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)

    def start(self) -> None:
        self._scheduler.start()
        self.sync()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync(self) -> int:
        """Пересобирает задания по текущему набору воркфлоу. Возвращает их число."""
        self._scheduler.remove_all_jobs()
        planned = 0
        for workflow in self._library.all().values():
            if not workflow.enabled or workflow.trigger.type not in ("cron", "interval"):
                continue
            self._scheduler.add_job(
                self._fire,
                trigger=self._build_trigger(workflow),
                args=[workflow.name],
                id=workflow.name,
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
            planned += 1
        logger.info("В расписании заданий: %s", planned)
        return planned

    def _build_trigger(self, workflow: Workflow):
        if workflow.trigger.type == "interval":
            return IntervalTrigger(
                minutes=int(workflow.trigger.minutes or 60), timezone=self._timezone
            )
        return CronTrigger.from_crontab(workflow.trigger.cron, timezone=self._timezone)

    async def _fire(self, workflow_name: str) -> None:
        workflow = self._library.get(workflow_name)
        await self._engine.run(workflow, trigger="schedule")

    def jobs_overview(self) -> dict[str, str]:
        """Имя воркфлоу -> ближайшее срабатывание. Для веб-панели."""
        overview = {}
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            overview[job.id] = next_run.strftime("%d.%m %H:%M") if next_run else "—"
        return overview

    async def catch_up(self) -> list[str]:
        """Запускает воркфлоу, чьё время наступило, пока машина была выключена."""
        now = datetime.now(self._timezone)
        grace = timedelta(minutes=self._services.settings.catch_up_grace_minutes)
        launched: list[str] = []
        for workflow in self._library.all().values():
            if not self._is_catchable(workflow):
                continue
            since = await self._catch_up_since(workflow.name, now, grace)
            trigger = CronTrigger.from_crontab(workflow.trigger.cron, timezone=self._timezone)
            missed = last_missed_fire(trigger, since, now)
            if missed is None or now - missed > grace:
                continue
            logger.info("Догоняю пропущенный запуск %s (план был %s)",
                        workflow.name, missed.strftime("%d.%m %H:%M"))
            await self._engine.run(workflow, trigger="catch_up")
            launched.append(workflow.name)
        return launched

    @staticmethod
    def _is_catchable(workflow: Workflow) -> bool:
        return (
            workflow.enabled
            and workflow.trigger.type == "cron"
            and workflow.trigger.catch_up
            and bool(workflow.trigger.cron)
        )

    async def _catch_up_since(
        self, workflow_name: str, now: datetime, grace: timedelta
    ) -> datetime:
        """Точка отсчёта: последний запуск, но не глубже окна догона."""
        last_finished = await self._services.runs.last_finished_at(workflow_name)
        floor = now - grace
        if last_finished is None:
            return floor
        return max(parse_iso(last_finished).astimezone(self._timezone), floor)
