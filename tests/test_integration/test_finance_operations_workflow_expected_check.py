from __future__ import annotations

from pathlib import Path

from tablecodeagent.benchmark.answer_models import validate_answer_json_with_model
from tests.test_workflows.finance_operations import run_finance_operations


def test_finance_operations_workflow_matches_expected_fixture(tmp_path: Path) -> None:
    task_dir = Path("benchmarks/tasks/finance_operations_001")
    output_path = tmp_path / "answer.json"

    report = run_finance_operations(task_dir, output_path=output_path)

    assert output_path.exists()
    assert report["validation"]["passed"] is True
    assert report["summary"]["open_invoice_amount_by_currency"] == {"EUR": 1200.0, "USD": 3150.0}
    assert report["summary"]["unapplied_cash_amount_by_currency"] == {"USD": 1700.0}
    assert report["summary"]["expected_credit_loss_by_currency"] == {"EUR": 0.0, "USD": 232.75}
    assert report["summary"]["duplicate_invoice_count"] == 1
    assert report["summary"]["duplicate_payment_count"] == 1
    assert report["data_quality"]["duplicate_invoice_ids"] == ["INV-1002"]
    assert report["data_quality"]["duplicate_payment_ids"] == ["PAY-003"]
    assert report["data_quality"]["currency_mismatch_payment_ids"] == ["PAY-005"]
    assert report["data_quality"]["missing_due_date_invoice_ids"] == ["INV-1006"]
    assert report["data_quality"]["future_dated_payment_ids"] == ["PAY-009"]
    assert report["data_quality"]["non_posted_payment_ids"] == ["PAY-010"]
    assert report["data_quality"]["unmatched_adjustment_ids"] == ["ADJ-004"]
    assert report["data_quality"]["over_credit_limit_customer_ids"] == ["C002"]
    assert validate_answer_json_with_model(report, answer_model="finance_operations")["passed"] is True
