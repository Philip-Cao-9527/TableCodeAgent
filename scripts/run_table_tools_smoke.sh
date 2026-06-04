#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/python${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
import json
from pathlib import Path

from tablecodeagent.table_tools.core import load_table, profile_table, query_table
from tablecodeagent.validation.answer import validate_answer

task_dir = Path("benchmarks/tasks/demo_table_001")
data_path = task_dir / "data.csv"
task = json.loads((task_dir / "task.json").read_text())
expected = json.loads((task_dir / "expected.json").read_text())

table = load_table(data_path)
profile = profile_table(data_path)
actual = query_table(data_path, **task["query"])
result = validate_answer(actual, expected["answer"], expected["tolerance"])

print("table:", {"columns": table["columns"], "row_count": table["row_count"]})
print("profile:", profile)
print("actual:", actual)
print("validation:", result)

assert table["row_count"] == 5
assert table["preview_row_count"] == 5
assert profile["column_count"] == 7
assert profile["duplicate_row_count"] == 0
assert actual["value"] == 32.5
assert actual["matched_row_count"] == 3
assert result["passed"] is True
PY
