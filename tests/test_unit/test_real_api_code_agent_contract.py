from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tablecodeagent.benchmark.answer_models import validate_answer_json_with_model
from tablecodeagent.benchmark.real_api_code_agent import (
    _is_api_timeout_error,
    _public_output_contract,
    _schema_check_answer_json,
    _validate_answer_json,
)
from tablecodeagent.tracing.logger import result_from_trace


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
    assert result["errors"]


def test_pydantic_schema_check_reports_nested_errors(tmp_path):
    task = json.loads(Path("benchmarks/tasks/credit_risk_scoring_001/task.json").read_text(encoding="utf-8"))
    contract = _public_output_contract(task)
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps({"row_counts": {"applications": 1}}), encoding="utf-8")

    result = _schema_check_answer_json(answer_path, contract)

    assert result["passed"] is False
    assert result["schema_source"] == "pydantic"
    assert result["answer_model"] == "credit_risk_scoring"
    assert any(error["path"].startswith("$.data_quality") for error in result["errors"])


def test_no_helper_task_contracts_do_not_expose_project_helpers():
    task_paths = [
        Path("benchmarks/tasks/growth_campaign_audit_001/task.json"),
        Path("benchmarks/tasks/credit_risk_scoring_001/task.json"),
        Path("benchmarks/tasks/finance_operations_001/task.json"),
    ]
    forbidden = ("implementation_hints", "allowed_project_helpers", "solve_py_suggestion", "build_", "tablecodeagent.workflows")

    for task_path in task_paths:
        text = task_path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden), task_path
        task = json.loads(text)
        contract = _public_output_contract(task)
        assert contract["schema_source"] == "pydantic"
        assert "answer_json_schema" in contract
        assert contract["allowed_libraries"]


def test_credit_task_contract_requires_warning_tags_and_lowercase_risk_bands():
    task = json.loads(Path("benchmarks/tasks/credit_risk_scoring_001/task.json").read_text(encoding="utf-8"))
    contract = _public_output_contract(task)

    assert contract["risk_band_allowed_values"] == ["low", "medium", "high"]
    assert contract["risk_band_counts_required_keys"] == ["low", "medium", "high"]
    assert "at least 4" in contract["risk_band_business_rule"]
    assert "unique application rows" in contract["duplicate_count_semantics"]["duplicate_customers.duplicate_key_count"]
    assert "missing or blank age" in contract["invalid_age_count_semantics"]
    assert "default_90d" in contract["field_type_issue_semantics"]
    assert "duplicate_application_id" in contract["required_warning_tags"]
    assert "high_risk_applications" in contract["required_warning_tags"]

    answer = {
        "row_counts": {"total_rows": 1},
        "field_summary": {},
        "data_quality": {
            "required_columns": [],
            "missing_required_columns": [],
            "missing_values": {},
            "duplicate_keys": {"key_columns": ["application_id"], "duplicate_key_count": 0},
            "duplicate_customers": {"key_columns": ["user_id"], "duplicate_key_count": 0},
            "invalid_age_count": 0,
            "leakage_columns_present": [],
            "field_type_issues": [],
        },
        "feature_processing": {
            "pre_loan_numeric_features": [],
            "pre_loan_categorical_features": [],
            "excluded_columns": [],
            "exclusion_reasons": {},
            "feature_window": {},
            "label_window": {},
            "time_split_column": "application_time",
        },
        "scoring_result": {
            "method": "demo",
            "scored_rows": [{"application_id": "a1", "user_id": "u1", "risk_score": 1.0, "risk_band": "High"}],
            "risk_band_counts": {"Low": 0, "Medium": 0, "High": 1},
        },
        "business_rule_checks": {
            "target_not_used_as_feature": True,
            "leakage_columns_excluded": True,
            "label_window_declared": True,
            "feature_window_declared": True,
            "duplicate_application_check_completed": True,
            "customer_uniqueness_check_completed": True,
            "field_type_checks_completed": True,
            "requires_manual_review_for_high_risk": True,
        },
        "explanations": [],
        "warnings": [],
        "how_to_do_differently": [],
        "validation": {},
    }

    result = validate_answer_json_with_model(answer, answer_model="credit_risk_scoring")

    assert result["passed"] is False
    assert any("$.scoring_result.scored_rows[0].risk_band" == error["path"] for error in result["errors"])
    assert any("$.scoring_result.risk_band_counts.low" == error["path"] for error in result["errors"])


def test_finance_task_contract_publishes_business_rules_and_schema():
    task = json.loads(Path("benchmarks/tasks/finance_operations_001/task.json").read_text(encoding="utf-8"))
    contract = _public_output_contract(task)
    finance_contract = contract["finance_contract"]

    assert contract["answer_model"] == "finance_operations"
    assert contract["schema_source"] == "pydantic"
    assert "answer_json_schema" in contract
    assert "Use policy.reference_date exactly" in finance_contract["reference_date"]
    assert "invoice_id is the business key" in finance_contract["invoice_uniqueness"]
    assert "payment_id is the business key" in finance_contract["payment_uniqueness"]
    assert "pandas NaN/NaT" in finance_contract["missing_value_normalization"]
    assert "due_date=null" in finance_contract["aging_boundaries"]
    assert "po_number is missing" in finance_contract["terms_and_documentation"]
    assert "cap applied_amount at invoice_amount" in finance_contract["overpayment"]
    assert "Open disputed invoices remain in aging" in finance_contract["disputes"]
    assert "0-30 includes 0 and 30" in finance_contract["aging_boundaries"]
    assert "Do not convert currencies" in finance_contract["currency"]
    assert "duplicate_invoice" in contract["required_exception_types"]
    assert "review_customer_status" in contract["required_action_tags"]


def test_finance_answer_schema_rejects_enum_case_and_missing_nested_fields():
    bad_answer = {
        "summary": {
            "reference_date": "2026-05-31",
            "base_currency": "USD",
            "invoice_row_count": 1,
            "unique_invoice_count": 1,
            "duplicate_invoice_count": 0,
            "payment_row_count": 1,
            "duplicate_payment_count": 0,
            "total_invoice_amount_by_currency": {"USD": 100.0},
            "applied_payment_amount_by_currency": {"USD": 0.0},
            "open_invoice_amount_by_currency": {"USD": 100.0},
            "unapplied_cash_amount_by_currency": {},
            "disputed_open_amount_by_currency": {},
        },
        "customer_risk": [
            {
                "customer_id": "C001",
                "customer_name": "Apex",
                "status": "active",
                "risk_band": "High",
                "open_amount_by_currency": {"USD": 100.0},
                "overdue_amount_by_currency": {"USD": 100.0},
                "disputed_open_amount_by_currency": {},
                "risk_amount_excluding_disputed_by_currency": {"USD": 100.0},
                "max_days_overdue": 1,
                "action_tags": [],
                "rationale": [],
            }
        ],
        "invoice_reconciliation": [],
        "aging_buckets": [],
        "exceptions": [{"exception_type": "OverPayment", "severity": "warning", "count": 1, "amount_by_currency": {"USD": 1.0}, "related_ids": [], "description": "bad"}],
        "recommended_actions": [],
        "data_quality": {
            "required_columns": {},
            "missing_required_columns": {},
            "duplicate_invoice_ids": [],
            "duplicate_payment_ids": [],
            "invalid_invoice_ids": [],
            "unmatched_payment_ids": [],
            "currency_mismatch_payment_ids": [],
            "missing_due_date_invoice_ids": [],
        },
        "audit_notes": [],
        "validation": {},
    }

    result = validate_answer_json_with_model(bad_answer, answer_model="finance_operations")

    assert result["passed"] is False
    assert any(error["path"] == "$.customer_risk[0].risk_band" for error in result["errors"])
    assert any(error["path"] == "$.exceptions[0].exception_type" for error in result["errors"])


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


def test_api_timeout_detection_includes_asyncio_timeout():
    assert _is_api_timeout_error(asyncio.TimeoutError())


def test_result_from_trace_exposes_run_python_summary():
    result = result_from_trace({
        "task_id": "demo",
        "mode": "real_api_code_agent",
        "provider": "deepseek",
        "model_name": "demo-model",
        "api_called": True,
        "skipped": False,
        "benchmark_profile": "no_helper",
        "helper_hints_exposed": False,
        "validation": {"passed": None},
        "failure_type": "code_execution_failed",
        "run_python": {
            "exit_code": 1,
            "stderr_summary": "UnicodeEncodeError",
            "stdout_summary": "answer.json saved",
        },
        "run_python_exit_code": 1,
        "run_python_stderr_summary": "UnicodeEncodeError",
        "run_python_stdout_summary": "answer.json saved",
    })

    assert result["benchmark_profile"] == "no_helper"
    assert result["helper_hints_exposed"] is False
    assert result["run_python"]["exit_code"] == 1
    assert result["run_python_exit_code"] == 1
    assert result["run_python_stderr_summary"] == "UnicodeEncodeError"
