from __future__ import annotations

import json
from typing import Any

from mini_claude.memory import save_memory


VALID_MEMORY_KINDS = {"reusable_knowledge", "failure_case", "how_to_do_differently"}


def build_analysis_memory(
    *,
    name: str,
    memory_kind: str,
    lesson_type: str,
    scope: dict[str, Any],
    evidence: dict[str, Any],
    content: str,
    invalidation: str,
) -> dict[str, Any]:
    if memory_kind not in VALID_MEMORY_KINDS:
        raise ValueError(f"Unsupported analysis memory kind: {memory_kind}")
    return {
        "name": name,
        "type": "project",
        "memory_kind": memory_kind,
        "lesson_type": lesson_type,
        "scope": scope,
        "evidence": evidence,
        "content": content,
        "invalidation": invalidation,
    }


def save_analysis_memory(memory: dict[str, Any]) -> str:
    description = f"{memory['memory_kind']} / {memory['lesson_type']}"
    body = json.dumps(memory, ensure_ascii=False, indent=2)
    return save_memory(
        name=memory["name"],
        description=description,
        type="project",
        content=body,
    )
