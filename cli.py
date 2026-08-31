"""Командная строка для отладки без запуска всего сервиса.

Примеры:
    python cli.py list
    python cli.py nodes
    python cli.py run morning_digest
"""

import argparse
import asyncio
import sys

from core.application import Application
from core.config import get_settings
from core.errors import WorkflowError
from core.logging_setup import setup_logging
from core.registry import available_nodes


async def _with_application(action) -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    application = Application(settings)
    await application.startup(with_scheduler=False)
    try:
        return await action(application)
    finally:
        await application.shutdown()


async def _list(application) -> int:
    workflows = application.library.all()
    if not workflows:
        print("Воркфлоу не найдены в каталоге workflows/")
    for workflow in workflows.values():
        trigger = workflow.trigger
        schedule = trigger.cron or (f"каждые {trigger.minutes} мин" if trigger.minutes else "вручную")
        flag = "" if workflow.enabled else "  [выключен]"
        print(f"{workflow.name:<22} {schedule:<18} {workflow.title}{flag}")
    for filename, error in application.library.errors.items():
        print(f"ОШИБКА в {filename}: {error}", file=sys.stderr)
    return 0


async def _run(application, name: str) -> int:
    try:
        workflow = application.library.get(name)
    except WorkflowError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    outcome = await application.engine.run(workflow, trigger="cli")
    print(f"\nСтатус: {outcome.status}")
    if outcome.error:
        print(f"Ошибка: {outcome.error}", file=sys.stderr)
    text = outcome.last_text()
    if text:
        print(f"\n{text}")
    return 0 if outcome.ok else 1


def _nodes() -> int:
    for name, description in available_nodes().items():
        print(f"{name:<18} {description}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный автоматизатор")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="показать воркфлоу")
    subparsers.add_parser("nodes", help="показать доступные типы шагов")
    run_parser = subparsers.add_parser("run", help="выполнить воркфлоу")
    run_parser.add_argument("name")
    arguments = parser.parse_args()

    if arguments.command == "nodes":
        import nodes  # noqa: F401 — регистрация нод

        return _nodes()
    if arguments.command == "list":
        return asyncio.run(_with_application(_list))
    return asyncio.run(_with_application(lambda app: _run(app, arguments.name)))


if __name__ == "__main__":
    sys.exit(main())
