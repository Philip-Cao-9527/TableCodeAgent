from __future__ import annotations

import json
from pathlib import Path


BUCKET_ORDER = ["not_due", "0-30", "31-60", "61-90", "90+", "missing_due_date"]


def _load_answer() -> dict:
    answer_path = Path("answer.json")
    assert answer_path.exists(), "answer.json must exist"
    return json.loads(answer_path.read_text(encoding="utf-8"))


def _load_expected() -> dict:
    return json.loads(Path("expected.json").read_text(encoding="utf-8"))


def _amounts_close(actual: dict, expected: dict) -> None:
    assert set(expected).issubset(actual), {"actual": actual, "expected": expected}
    for currency, amount in expected.items():
        assert round(float(actual[currency]), 2) == round(float(amount), 2), (currency, actual, expected)


def test_finance_operations_answer_contract_and_business_findings() -> None:
    answer = _load_answer()
    expected = _load_expected()

    assert set(expected["expected_top_level_keys"]).issubset(answer), sorted(set(expected["expected_top_level_keys"]) - set(answer))

    summary = answer["summary"]
    assert summary["reference_date"] == "2026-05-31"
    assert summary["base_currency"] == "USD"
    assert summary["duplicate_invoice_count"] == expected["expected_duplicate_invoice_count"]
    assert summary["duplicate_payment_count"] == expected["expected_duplicate_payment_count"]
    _amounts_close(summary["open_invoice_amount_by_currency"], expected["expected_open_amount_by_currency"])
    _amounts_close(summary["unapplied_cash_amount_by_currency"], expected["expected_unapplied_cash_by_currency"])
    _amounts_close(summary["disputed_open_amount_by_currency"], expected["expected_disputed_open_amount_by_currency"])
    _amounts_close(summary["expected_credit_loss_by_currency"], expected["expected_credit_loss_by_currency"])

    data_quality = answer["data_quality"]
    assert data_quality["duplicate_invoice_ids"] == ["INV-1002"]
    assert data_quality["duplicate_payment_ids"] == ["PAY-003"]
    assert data_quality["invalid_invoice_ids"] == ["INV-1007"]
    assert data_quality["currency_mismatch_payment_ids"] == ["PAY-005"]
    assert "INV-1006" in data_quality["missing_due_date_invoice_ids"]
    assert data_quality["future_dated_payment_ids"] == ["PAY-009"]
    assert data_quality["non_posted_payment_ids"] == ["PAY-010"]
    assert data_quality["unmatched_adjustment_ids"] == ["ADJ-004"]
    assert data_quality["missing_po_invoice_ids"] == expected["expected_missing_po_invoice_ids"]
    assert data_quality["term_mismatch_invoice_ids"] == expected["expected_term_mismatch_invoice_ids"]
    assert data_quality["over_credit_limit_customer_ids"] == expected["expected_over_credit_limit_customer_ids"]

    exceptions = {item["exception_type"]: item for item in answer["exceptions"]}
    assert set(expected["expected_exception_types"]).issubset(exceptions)
    assert exceptions["currency_mismatch"]["count"] == expected["expected_currency_mismatch_payment_count"]
    assert exceptions["missing_due_date"]["count"] == expected["expected_missing_due_date_count"]
    assert exceptions["negative_invoice_amount"]["count"] == expected["expected_negative_invoice_count"]
    assert exceptions["future_dated_payment"]["count"] == expected["expected_future_dated_payment_count"]
    assert exceptions["non_posted_payment"]["count"] == expected["expected_non_posted_payment_count"]
    assert exceptions["unmatched_adjustment"]["count"] == expected["expected_unmatched_adjustment_count"]
    _amounts_close(exceptions["overpayment"]["amount_by_currency"], expected["expected_overpayment_by_currency"])
    _amounts_close(exceptions["approved_credit_memo"]["amount_by_currency"], expected["expected_credit_memo_by_currency"])
    _amounts_close(exceptions["chargeback"]["amount_by_currency"], expected["expected_chargeback_by_currency"])

    reconciliation = {item["invoice_id"]: item for item in answer["invoice_reconciliation"]}
    assert "INV-1007" not in reconciliation
    assert list(reconciliation) == sorted(reconciliation)
    for invoice_id, amount in expected["expected_invoice_open_amounts"].items():
        assert round(float(reconciliation[invoice_id]["open_amount"]), 2) == amount
    for invoice_id, bucket in expected["expected_invoice_aging_buckets"].items():
        assert reconciliation[invoice_id]["aging_bucket"] == bucket
    assert reconciliation["INV-1001"]["overpayment_amount"] == expected["expected_overpayment_by_currency"]["USD"]
    assert "overpayment" in reconciliation["INV-1001"]["exception_tags"]
    assert reconciliation["INV-1003"]["approved_adjustment_amount"] == -50.0
    assert "approved_credit_memo" in reconciliation["INV-1003"]["exception_tags"]
    assert "partial_payment" in reconciliation["INV-1003"]["exception_tags"]
    assert "disputed_invoice" in reconciliation["INV-1008"]["exception_tags"]
    assert reconciliation["INV-1008"]["approved_adjustment_amount"] == 50.0
    assert "chargeback" in reconciliation["INV-1008"]["exception_tags"]
    assert "pending_write_off" in reconciliation["INV-1009"]["exception_tags"]

    aging = {(item["currency"], item["bucket"]): item for item in answer["aging_buckets"]}
    for currency, buckets in expected["expected_aging_buckets"].items():
        for bucket, amount in buckets.items():
            assert round(float(aging[(currency, bucket)]["open_amount"]), 2) == amount
    for bucket, amount in expected["expected_aging_expected_credit_loss"]["USD"].items():
        assert round(float(aging[("USD", bucket)]["expected_credit_loss"]), 2) == amount
    assert [item["bucket"] for item in answer["aging_buckets"] if item["currency"] == "USD"] == BUCKET_ORDER

    customer_risk = {item["customer_id"]: item for item in answer["customer_risk"]}
    assert customer_risk["C001"]["risk_band"] == "high"
    assert customer_risk["C001"]["max_days_overdue"] == 120
    assert customer_risk["C003"]["status"] == "on_hold"
    assert "review_customer_status" in customer_risk["C003"]["action_tags"]
    assert "review_credit_hold" in customer_risk["C002"]["action_tags"]
    assert "request_documentation" in customer_risk["C004"]["action_tags"]
    assert "investigate_chargeback" in customer_risk["C004"]["action_tags"]
    assert "review_adjustment" in customer_risk["C001"]["action_tags"]

    action_tags = {tag for row in answer["customer_risk"] for tag in row["action_tags"]}
    assert set(expected["expected_required_action_tags"]).issubset(action_tags)
    action_types = {item["action_type"] for item in answer["recommended_actions"]}
    assert {"collect_overdue", "resolve_dispute", "apply_unapplied_cash", "fix_data_quality", "review_customer_status"}.issubset(action_types)

    assert answer["validation"]["passed"] is True
