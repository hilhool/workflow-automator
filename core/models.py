"""Модели предметной области: описание воркфлоу, шагов и результатов."""

from dataclasses import dataclass, field
from typing import Any, Literal

TriggerType = Literal["cron", "interval", "manual", "event"]
RunStatus = Literal["running", "success", "failed", "skipped"]


@dataclass(frozen=True)
class Trigger:
    """Когда запускать воркфлоу."""

    type: TriggerType = "manual"
    cron: str | None = None
    minutes: int | None = None
    event: str | None = None
    catch_up: bool = True


@dataclass(frozen=True)
class Step:
    """Один шаг воркфлоу — вызов ноды с параметрами."""

    id: str
    node: str
    params: dict[str, Any] = field(default_factory=dict)
    when: str | None = None
    continue_on_error: bool = False


@dataclass(frozen=True)
class Workflow:
    """Полное описание воркфлоу, загруженное из YAML."""

    name: str
    title: str
    steps: tuple[Step, ...]
    trigger: Trigger = field(default_factory=Trigger)
    description: str = ""
    enabled: bool = True
    vars: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


@dataclass
class StepResult:
    """Результат шага. Поле text — то, что подставляется в шаблоны по умолчанию."""

    ok: bool = True
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False

    def as_context(self) -> dict[str, Any]:
        """Представление для шаблонов: steps.<id>.<ключ>."""
        return {"ok": self.ok, "text": self.text, "skipped": self.skipped, **self.data}

    def preview(self, limit: int = 4000) -> str:
        if len(self.text) <= limit:
            return self.text
        return f"{self.text[:limit]}… (обрезано, всего {len(self.text)} символов)"


@dataclass
class ItemDraft:
    """Запись в универсальном хранилище: домашка, задача, пара, заметка."""

    kind: str
    source: str
    title: str
    body: str = ""
    due_at: str | None = None
    external_id: str | None = None
    status: str = "open"
    payload: dict[str, Any] = field(default_factory=dict)
