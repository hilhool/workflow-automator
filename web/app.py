"""Веб-панель: список воркфлоу, журнал запусков, записи. Только localhost."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.timeutil import format_local
from web.api import build_api_router

WEB_DIR = Path(__file__).resolve().parent


def create_web_app(application) -> FastAPI:
    """Собирает FastAPI поверх готового Application."""
    app = FastAPI(title="Локальный автоматизатор", docs_url="/api/docs")
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    timezone = application.settings.timezone
    templates.env.filters["local"] = lambda value: (
        format_local(value, timezone) if value else "—"
    )
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    app.include_router(build_api_router(application))

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        runs = await application.services.runs.recent(limit=20)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "workflows": sorted(
                    application.library.all().values(), key=lambda item: item.title
                ),
                "next_runs": application.scheduler.jobs_overview(),
                "runs": runs,
                "errors": application.library.errors,
                "settings": application.settings,
            },
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_page(request: Request, run_id: int) -> HTMLResponse:
        run = await application.services.runs.get(run_id)
        steps = await application.services.runs.steps_of(run_id) if run else []
        return templates.TemplateResponse(
            request=request,
            name="run.html",
            context={"run": run, "steps": steps},
        )

    @app.get("/items", response_class=HTMLResponse)
    async def items_page(request: Request) -> HTMLResponse:
        items = await application.services.items.list_recent(limit=200)
        return templates.TemplateResponse(
            request=request,
            name="items.html",
            context={"items": items},
        )

    @app.get("/usage", response_class=HTMLResponse)
    async def usage_page(request: Request) -> HTMLResponse:
        daily = await application.services.kv.all_in("usage")
        return templates.TemplateResponse(
            request=request,
            name="usage.html",
            context={"daily": dict(sorted(daily.items(), reverse=True))},
        )

    return app
