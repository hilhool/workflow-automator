"""Исполнитель воркфлоу: разворачивает шаблоны, вызывает ноды, пишет журнал."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.context import build_context
from core.errors import WorkflowError
from core.models import Step, StepResult, Workflow
from core.registry import get_node_class
from core.services import Services
from core.template import render_condition, render_params
from nodes.base import NodeContext

logger = logging.getLogger(__name__)


@dataclass
class RunOutcome:
    """Итог запуска воркфлоу."""

    run_id: int
    workflow: str
    status: str
    results: dict[str, StepResult] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def last_text(self) -> str:
        """Текст последнего результативного шага — удобно для ручного запуска."""
        for result in reversed(list(self.results.values())):
            if result.text:
                return result.text
        return ""


class Engine:
    """Запускает воркфлоу. Один воркфлоу не выполняется параллельно сам с собой."""

    def __init__(self, services: Services):
        self._services = services
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def run(
        self, workflow: Workflow, *, trigger: str = "manual",
        variables: dict[str, Any] | None = None,
    ) -> RunOutcome:
        """Выполняет шаги по порядку. Исключения наружу не выходят."""
        async with self._locks[workflow.name]:
            return await self._run_unlocked(workflow, trigger, variables or {})

    async def _run_unlocked(
        self, workflow: Workflow, trigger: str, variables: dict[str, Any]
    ) -> RunOutcome:
        runs = self._services.runs
        run_id = await runs.start_run(workflow.name, trigger)
        context = build_context(workflow, variables, self._services.settings.timezone)
        outcome = RunOutcome(run_id=run_id, workflow=workflow.name, status="success")
        logger.info("Запуск %s (#%s, триггер: %s)", workflow.name, run_id, trigger)

        for step in workflow.steps:
            result, failure = await self._run_step(step, context, run_id, workflow)
            outcome.results[step.id] = result
            context["steps"][step.id] = result.as_context()
            if failure and not step.continue_on_error:
                outcome.status = "failed"
                outcome.error = failure
                await runs.finish_run(
                    run_id, "failed", error_code="STEP_FAILED", error_message=failure
                )
                logger.error("Воркфлоу %s остановлен на шаге %s: %s",
                             workflow.name, step.id, failure)
                return outcome

        await runs.finish_run(run_id, "success")
        logger.info("Воркфлоу %s завершён (#%s)", workflow.name, run_id)
        return outcome

    async def _run_step(
        self, step: Step, context: dict, run_id: int, workflow: Workflow
    ) -> tuple[StepResult, str]:
        """Выполняет один шаг. Возвращает результат и текст ошибки (пустой при успехе)."""
        runs = self._services.runs
        if step.when and not self._condition_holds(step, context):
            row_id = await runs.start_step(run_id, step.id, step.node)
            await runs.finish_step(row_id, "skipped", output="Условие when не выполнено")
            return StepResult(ok=True, skipped=True, text=""), ""

        row_id = await runs.start_step(run_id, step.id, step.node)
        try:
            result = await self._invoke_node(step, context, run_id, workflow)
        except WorkflowError as error:
            await runs.finish_step(row_id, "failed", error_message=str(error))
            return StepResult(ok=False, text=""), str(error)
        except Exception as error:  # noqa: BLE001 — сбой ноды не должен ронять процесс
            logger.exception("Непредвиденная ошибка в шаге %s", step.id)
            message = f"{type(error).__name__}: {error}"
            await runs.finish_step(row_id, "failed", error_message=message)
            return StepResult(ok=False, text=""), message

        await runs.finish_step(row_id, "success", output=result.preview())
        return result, ""

    def _condition_holds(self, step: Step, context: dict) -> bool:
        try:
            return render_condition(step.when or "", context)
        except WorkflowError as error:
            logger.warning("Условие шага %s не вычислено (%s) — шаг пропущен", step.id, error)
            return False

    async def _invoke_node(
        self, step: Step, context: dict, run_id: int, workflow: Workflow
    ) -> StepResult:
        params = render_params(step.params, context)
        node = get_node_class(step.node)()
        node_context = NodeContext(
            services=self._services,
            workflow=workflow,
            step_id=step.id,
            run_id=run_id,
            logger=logging.getLogger(f"node.{step.node}"),
        )
        return await node.run(params, node_context)
