from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProductWorkflowState:
    task_id: str
    task_dir: str
    workspace_path: str | None
    status: str
    next_action: str | None
    task_summary: dict[str, Any]
    tables: dict[str, str]
    context_package: dict[str, Any]
    tool_strategy: list[dict[str, Any]]
    code_generation_brief: dict[str, Any]
    attempts: list[dict[str, Any]] = field(default_factory=list)
    repair_history: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] | None = None
    schema_check: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    analysis_memory: list[dict[str, Any]] = field(default_factory=list)
    failure_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
