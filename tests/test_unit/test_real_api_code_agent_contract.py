from __future__ import annotations

import json

from tablecodeagent.benchmark.real_api_code_agent import _schema_check_answer_json, _validate_answer_json


def test_schema_check_reports_missing_required_keys(tmp_path):
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps({"task_id": "demo"}), encoding="utf-8")

    contract = {
        "validation_mode": "pytest",
        "answer_json_required_keys": ["row_counts", "warnings"],
    }
    result = _schema_check_answer_json(answer_path, contract)

    assert result["passed"] is False
    assert result["missing_keys"] == ["row_counts", "warnings"]


def test_pytest_validation_mode_does_not_mark_answer_existence_as_passed(tmp_path):
    answer_path = tmp_path / "answer.json"
    expected_path = tmp_path / "expected.json"
    answer_path.write_text(json.dumps({"row_counts": {"demo": 1}}), encoding="utf-8")
    expected_path.write_text(json.dumps({"expected_required_warnings": ["demo"]}), encoding="utf-8")

    result = _validate_answer_json(
        answer_path,
        expected_path,
        {"validation_mode": "pytest"},
    )

    assert result["passed"] is None
    assert result["expected"] == "pytest is authoritative for this task"
