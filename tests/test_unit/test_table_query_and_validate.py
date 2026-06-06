from __future__ import annotations

import json
from pathlib import Path

from tablecodeagent.table_tools.core import query_multi_table, query_table
from tablecodeagent.validation.answer import validate_answer


TASK_ROOT = Path("benchmarks/tasks")


def _load_expected(task_id: str) -> dict:
    return json.loads((TASK_ROOT / task_id / "expected.json").read_text(encoding="utf-8"))


def test_query_table_and_validate_csv_task() -> None:
    task_dir = TASK_ROOT / "demo_table_001"
    expected = _load_expected("demo_table_001")

    actual = query_table(
        task_dir / "data.csv",
        metric="sum",
        column="revenue",
        filters={"region": "North"},
    )
    validation = validate_answer(actual, expected["answer"], expected["tolerance"])

    assert actual["value"] == 32.5
    assert validation["passed"] is True


def test_query_multi_table_and_validate_join_task() -> None:
    task_dir = TASK_ROOT / "multi_table_001"
    expected = _load_expected("multi_table_001")

    actual = query_multi_table(
        [
            {"name": "orders", "path": str(task_dir / "orders.csv")},
            {"name": "regions", "path": str(task_dir / "regions.csv")},
        ],
        join={"left_key": "region_id", "right_key": "region_id"},
        metric="sum",
        column="orders.revenue",
        filters={"regions.region": "North"},
    )
    validation = validate_answer(actual, expected["answer"], expected["tolerance"])

    assert actual["value"] == 32.5
    assert validation["passed"] is True
