from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from tablecodeagent.benchmark.answer_models import validate_answer_json_with_model
from tablecodeagent.runtime.sandbox import run_tests_in_sandbox
from tests.test_workflows.finance_operations import run_finance_operations


TASK_DIR = Path("benchmarks/tasks/finance_operations_001")


def _workspace(tmp_path: Path, answer: dict) -> Path:
    workspace = tmp_path / "finance_candidate"
    shutil.copytree(TASK_DIR, workspace)
    (workspace / "answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return workspace


def _pytest_exit_code(tmp_path: Path, answer: dict) -> int | None:
    workspace = _workspace(tmp_path, answer)
    result = run_tests_in_sandbox(
        workspace_dir=workspace,
        test_path="tests/test_solution.py",
        timeout_seconds=30,
    )
    return result["exit_code"]


def _correct_answer() -> dict:
    return run_finance_operations(TASK_DIR)


def test_simulated_correct_finance_answer_passes_schema_and_pytest(tmp_path: Path) -> None:
    answer = _correct_answer()

    assert validate_answer_json_with_model(answer, answer_model="finance_operations")["passed"] is True
    assert _pytest_exit_code(tmp_path, answer) == 0


def test_simulated_aging_boundary_error_is_caught_by_pytest(tmp_path: Path) -> None:
    answer = copy.deepcopy(_correct_answer())
    for row in answer["invoice_reconciliation"]:
        if row["invoice_id"] == "INV-1003":
            row["aging_bucket"] = "31-60"
    for row in answer["aging_buckets"]:
        if row["currency"] == "USD" and row["bucket"] == "61-90":
            row["open_amount"] = 0.0
            row["expected_credit_loss"] = 0.0
        if row["currency"] == "USD" and row["bucket"] == "31-60":
            row["open_amount"] = 700.0

    assert validate_answer_json_with_model(answer, answer_model="finance_operations")["passed"] is True
    assert _pytest_exit_code(tmp_path, answer) != 0


def test_simulated_payment_matching_error_is_caught_by_pytest(tmp_path: Path) -> None:
    answer = copy.deepcopy(_correct_answer())
    answer["summary"]["unapplied_cash_amount_by_currency"]["USD"] = 1500.0
    for row in answer["exceptions"]:
        if row["exception_type"] == "overpayment":
            row["amount_by_currency"]["USD"] = 0.0
    for row in answer["invoice_reconciliation"]:
        if row["invoice_id"] == "INV-1001":
            row["overpayment_amount"] = 0.0
            row["exception_tags"] = []

    assert validate_answer_json_with_model(answer, answer_model="finance_operations")["passed"] is True
    assert _pytest_exit_code(tmp_path, answer) != 0


def test_simulated_adjustment_and_allowance_error_is_caught_by_pytest(tmp_path: Path) -> None:
    answer = copy.deepcopy(_correct_answer())
    answer["summary"]["expected_credit_loss_by_currency"]["USD"] = 0.0
    for row in answer["invoice_reconciliation"]:
        if row["invoice_id"] == "INV-1003":
            row["approved_adjustment_amount"] = 0.0
            row["open_amount"] = 500.0
            row["exception_tags"] = [tag for tag in row["exception_tags"] if tag != "approved_credit_memo"]
    for row in answer["exceptions"]:
        if row["exception_type"] == "approved_credit_memo":
            row["amount_by_currency"]["USD"] = 0.0

    assert validate_answer_json_with_model(answer, answer_model="finance_operations")["passed"] is True
    assert _pytest_exit_code(tmp_path, answer) != 0


def test_simulated_enum_case_error_is_caught_by_schema() -> None:
    answer = copy.deepcopy(_correct_answer())
    answer["customer_risk"][0]["risk_band"] = "High"
    answer["exceptions"][0]["exception_type"] = "Duplicate_Invoice"

    result = validate_answer_json_with_model(answer, answer_model="finance_operations")

    assert result["passed"] is False
    assert any(error["path"].endswith(".risk_band") for error in result["errors"])
    assert any(error["path"].endswith(".exception_type") for error in result["errors"])


def test_simulated_missing_field_and_type_error_is_caught_by_schema() -> None:
    answer = copy.deepcopy(_correct_answer())
    answer.pop("data_quality")
    answer["summary"]["open_invoice_amount_by_currency"]["USD"] = "3150.00"

    result = validate_answer_json_with_model(answer, answer_model="finance_operations")

    assert result["passed"] is False
    assert any(error["path"] == "$.data_quality" for error in result["errors"])
    assert any(error["path"] == "$.summary.open_invoice_amount_by_currency.USD" for error in result["errors"])


def test_simulated_nested_json_shape_error_is_caught_by_schema() -> None:
    answer = copy.deepcopy(_correct_answer())
    answer["data_quality"]["duplicate_invoice_ids"] = [{"invoice_id": "INV-1001", "count": 2}]

    result = validate_answer_json_with_model(answer, answer_model="finance_operations")

    assert result["passed"] is False
    assert any(error["path"].startswith("$.data_quality.duplicate_invoice_ids") for error in result["errors"])


def test_simulated_duplicate_count_semantics_error_is_caught_by_pytest(tmp_path: Path) -> None:
    answer = copy.deepcopy(_correct_answer())
    answer["summary"]["duplicate_invoice_count"] = 0
    answer["data_quality"]["duplicate_invoice_ids"] = []

    assert validate_answer_json_with_model(answer, answer_model="finance_operations")["passed"] is True
    assert _pytest_exit_code(tmp_path, answer) != 0


def test_simulated_nan_due_date_string_is_caught_by_schema() -> None:
    answer = copy.deepcopy(_correct_answer())
    for row in answer["invoice_reconciliation"]:
        if row["invoice_id"] == "INV-1006":
            row["due_date"] = "nan"

    result = validate_answer_json_with_model(answer, answer_model="finance_operations")

    assert result["passed"] is False
    assert any(error["path"].endswith(".due_date") for error in result["errors"])
