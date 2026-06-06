from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mini_claude.tools import execute_tool, get_active_tool_definitions
from tablecodeagent.agent_tools import TABLE_TOOL_NAMES


def test_table_tools_are_registered_in_active_tool_definitions() -> None:
    active_names = {tool["name"] for tool in get_active_tool_definitions()}

    assert TABLE_TOOL_NAMES.issubset(active_names)


def test_execute_tool_routes_to_table_tool_adapter() -> None:
    task_dir = Path("benchmarks/tasks/demo_table_001")
    raw = asyncio.run(execute_tool(
        "query_table",
        {
            "csv_path": str(task_dir / "data.csv"),
            "metric": "sum",
            "column": "revenue",
            "filters": {"region": "North"},
        },
    ))
    payload = json.loads(raw)

    assert payload["ok"] is True
    assert payload["result"]["value"] == 32.5
