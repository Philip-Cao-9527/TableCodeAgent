#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/python${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
import asyncio
import json
from pathlib import Path

from mini_claude.tools import execute_tool, get_active_tool_definitions


async def main() -> None:
    task_dir = Path("benchmarks/tasks/demo_table_001")
    data_path = str(task_dir / "data.csv")
    expected = json.loads((task_dir / "expected.json").read_text())

    tool_names = {tool["name"] for tool in get_active_tool_definitions()}
    required = {"load_table", "profile_table", "query_table", "validate_answer"}
    missing = required - tool_names
    assert not missing, f"missing table tools: {sorted(missing)}"

    profile = json.loads(await execute_tool("profile_table", {"csv_path": data_path}))
    assert profile["ok"] is True
    assert profile["result"]["column_count"] == 7
    assert profile["result"]["duplicate_row_count"] == 0

    query = json.loads(await execute_tool(
        "query_table",
        {
            "csv_path": data_path,
            "metric": "sum",
            "column": "revenue",
            "filters": {"region": "North"},
        },
    ))
    assert query["ok"] is True
    assert query["result"]["value"] == 32.5
    assert query["result"]["matched_row_count"] == 3

    validation = json.loads(await execute_tool(
        "validate_answer",
        {
            "actual": query["result"],
            "expected": expected["answer"],
            "tolerance": expected["tolerance"],
        },
    ))
    assert validation["ok"] is True
    assert validation["result"]["passed"] is True

    print("table tool schemas:", sorted(required))
    print("query:", query["result"])
    print("validation:", validation["result"])


asyncio.run(main())
PY
