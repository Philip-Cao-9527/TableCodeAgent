from __future__ import annotations

from pathlib import Path

from tablecodeagent.benchmark.answer_models import validate_answer_json_with_model
from tablecodeagent.workflows.credit_risk_scoring import run_credit_risk_scoring


def test_credit_risk_scoring_workflow_matches_expected_fixture(tmp_path):
    task_dir = Path("benchmarks/tasks/credit_risk_scoring_001")
    output_path = tmp_path / "answer.json"

    report = run_credit_risk_scoring(task_dir, output_path=output_path)

    assert output_path.exists()
    assert report["validation"]["passed"] is True
    assert report["data_quality"]["duplicate_keys"]["duplicate_key_count"] == 1
    assert report["data_quality"]["duplicate_customers"]["duplicate_key_count"] == 2
    assert report["data_quality"]["invalid_age_count"] == 1
    assert len(report["data_quality"]["field_type_issues"]) == 1
    assert "post_loan_collection_calls" in report["feature_processing"]["excluded_columns"]
    assert "post_loan_dpd_max" in report["feature_processing"]["excluded_columns"]
    assert report["business_rule_checks"]["label_window_declared"] is True
    assert report["business_rule_checks"]["feature_window_declared"] is True
    assert report["scoring_result"]["risk_band_counts"]["high"] >= 4
    assert validate_answer_json_with_model(report, answer_model="credit_risk_scoring")["passed"] is True
