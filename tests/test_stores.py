"""Хранилища записей и состояния."""

from core.models import ItemDraft


async def test_upsert_deduplicates_by_external_id(services):
    draft = ItemDraft(kind="homework", source="chat", title="Физика", external_id="phys-1")
    first_id = await services.items.upsert(draft)
    second_id = await services.items.upsert(
        ItemDraft(kind="homework", source="chat", title="Физика, лаба 1", external_id="phys-1")
    )
    rows = await services.items.list_open("homework")
    assert first_id == second_id
    assert len(rows) == 1
    assert rows[0]["title"] == "Физика, лаба 1"


async def test_items_without_external_id_are_separate(services):
    for _ in range(2):
        await services.items.upsert(ItemDraft(kind="task", source="bot", title="Купить хлеб"))
    assert len(await services.items.list_open("task")) == 2


async def test_completed_items_leave_open_list(services):
    item_id = await services.items.upsert(ItemDraft(kind="task", source="bot", title="Дело"))
    await services.items.set_status(item_id, "done")
    assert await services.items.list_open("task") == []


async def test_kv_round_trip(services):
    await services.kv.set("cursor", "chat", {"@one": 42})
    assert await services.kv.get("cursor", "chat") == {"@one": 42}
    assert await services.kv.get("cursor", "missing", "по умолчанию") == "по умолчанию"


async def test_interrupted_runs_marked_failed_on_startup(services):
    run_id = await services.runs.start_run("flow", "schedule")
    await services.runs.mark_stale_as_failed()
    run = await services.runs.get(run_id)
    assert run["status"] == "failed"
    assert run["error_code"] == "INTERRUPTED"
