"""Поведение исполнителя воркфлоу."""

from core.models import Step, Trigger, Workflow


def build_workflow(*steps: Step, name: str = "test_flow") -> Workflow:
    return Workflow(name=name, title="Тест", steps=steps, trigger=Trigger())


async def test_passes_result_of_previous_step_forward(engine):
    workflow = build_workflow(
        Step(id="first", node="test.echo", params={"text": "привет"}),
        Step(id="second", node="test.echo", params={"text": "{{ steps.first.text }} мир"}),
    )
    outcome = await engine.run(workflow)
    assert outcome.ok
    assert outcome.results["second"].text == "привет мир"


async def test_stops_on_failed_step(engine):
    workflow = build_workflow(
        Step(id="boom", node="test.fail"),
        Step(id="never", node="test.echo", params={"text": "не должно выполниться"}),
    )
    outcome = await engine.run(workflow)
    assert outcome.status == "failed"
    assert "never" not in outcome.results


async def test_continues_when_step_allows_failure(engine):
    workflow = build_workflow(
        Step(id="boom", node="test.fail", continue_on_error=True),
        Step(id="after", node="test.echo", params={"text": "живой"}),
    )
    outcome = await engine.run(workflow)
    assert outcome.ok
    assert outcome.results["after"].text == "живой"


async def test_skips_step_when_condition_is_false(engine):
    workflow = build_workflow(
        Step(id="source", node="test.echo", params={"text": ""}),
        Step(
            id="guarded",
            node="test.echo",
            params={"text": "не нужно"},
            when="{{ steps.source.text }}",
        ),
    )
    outcome = await engine.run(workflow)
    assert outcome.results["guarded"].skipped is True


async def test_writes_run_journal(engine, services):
    workflow = build_workflow(Step(id="only", node="test.echo", params={"text": "ок"}))
    outcome = await engine.run(workflow, trigger="cli")
    run = await services.runs.get(outcome.run_id)
    steps = await services.runs.steps_of(outcome.run_id)
    assert run["status"] == "success"
    assert run["trigger"] == "cli"
    assert [step["status"] for step in steps] == ["success"]


async def test_unknown_variable_in_params_fails_run(engine):
    workflow = build_workflow(
        Step(id="bad", node="test.echo", params={"text": "{{ steps.nope.text }}"})
    )
    outcome = await engine.run(workflow)
    assert outcome.status == "failed"
    assert "steps.nope" in outcome.error
