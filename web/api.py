"""JSON API веб-панели. Используется и фронтендом, и вручную из терминала."""

from fastapi import APIRouter, HTTPException, Request

from core.errors import WorkflowError


def build_api_router(application) -> APIRouter:
    """Создаёт роутер, замкнутый на конкретный экземпляр приложения."""
    router = APIRouter(prefix="/api")

    @router.get("/status")
    async def status() -> dict:
        settings = application.settings
        return {
            "workflows": len(application.library.all()),
            "broken_files": application.library.errors,
            "next_runs": application.scheduler.jobs_overview(),
            "telegram_account": settings.has_telegram_account,
            "telegram_bot": settings.has_telegram_bot,
            "timezone": settings.timezone,
        }

    @router.post("/workflows/{name}/run")
    async def run_workflow(name: str, request: Request) -> dict:
        try:
            workflow = application.library.get(name)
        except WorkflowError as error:
            raise HTTPException(status_code=404, detail=error.to_dict()) from error
        variables = await _read_variables(request)
        outcome = await application.engine.run(
            workflow, trigger="manual", variables=variables
        )
        return {
            "run_id": outcome.run_id,
            "status": outcome.status,
            "error": outcome.error,
            "text": outcome.last_text()[:4000],
        }

    @router.post("/reload")
    async def reload() -> dict:
        planned = application.reload_workflows()
        return {"workflows": len(application.library.all()), "scheduled": planned,
                "errors": application.library.errors}

    @router.get("/runs")
    async def runs(limit: int = 50, workflow: str | None = None) -> dict:
        return {"runs": await application.services.runs.recent(limit, workflow)}

    @router.get("/runs/{run_id}")
    async def run_details(run_id: int) -> dict:
        run = await application.services.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Запуск не найден")
        return {"run": run, "steps": await application.services.runs.steps_of(run_id)}

    @router.get("/items")
    async def items(limit: int = 100) -> dict:
        return {"items": await application.services.items.list_recent(limit)}

    @router.post("/items/{item_id}/status")
    async def set_item_status(item_id: int, request: Request) -> dict:
        payload = await _read_json(request)
        status_value = str(payload.get("status") or "done")
        await application.services.items.set_status(item_id, status_value)
        return {"id": item_id, "status": status_value}

    @router.get("/usage")
    async def usage() -> dict:
        return {"daily": await application.services.kv.all_in("usage")}

    return router


async def _read_json(request: Request) -> dict:
    try:
        payload = await request.json()
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


async def _read_variables(request: Request) -> dict:
    payload = await _read_json(request)
    variables = payload.get("vars")
    return variables if isinstance(variables, dict) else {}
