from __future__ import annotations

import json
from pathlib import Path


def _load_answer() -> dict:
    answer_path = Path("answer.json")
    assert answer_path.exists(), "answer.json must exist"
    return json.loads(answer_path.read_text(encoding="utf-8"))


def _load_expected() -> dict:
    return json.loads(Path("expected.json").read_text(encoding="utf-8"))


def test_answer_schema_and_credit_risk_findings() -> None:
    answer = _load_answer()
    expected = _load_expected()

    assert set(expected["expected_output_keys"]).issubset(answer), sorted(set(expected["expected_output_keys"]) - set(answer))

    duplicate_key = answer["data_quality"]["duplicate_keys"]
    assert duplicate_key["duplicate_key_count"] == expected["expected_duplicate_application_count"]

    assert answer["data_quality"]["invalid_age_count"] == expected["expected_invalid_age_count"]
    assert set(expected["expected_leakage_columns"]).issubset(set(answer["data_quality"]["leakage_columns_present"]))

    high_risk_count = answer["scoring_result"]["risk_band_counts"].get("high", 0)
    assert high_risk_count >= expected["expected_high_risk_min"]

    warnings = "\n".join(answer["warnings"])
    for warning in expected["expected_required_warnings"]:
        assert warning in warnings

    excluded = set(answer["feature_processing"]["excluded_columns"])
    assert "default_90d" in excluded
    assert "post_loan_collection_calls" in excluded
