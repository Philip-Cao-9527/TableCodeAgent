from __future__ import annotations

import json
from pathlib import Path


def _load_answer() -> dict:
    answer_path = Path("answer.json")
    assert answer_path.exists(), "answer.json must exist"
    return json.loads(answer_path.read_text(encoding="utf-8"))


def _load_expected() -> dict:
    return json.loads(Path("expected.json").read_text(encoding="utf-8"))


def test_answer_schema_and_growth_audit_findings() -> None:
    answer = _load_answer()
    expected = _load_expected()

    required_keys = {
        "row_counts",
        "join_cardinality",
        "group_distribution",
        "smd_summary",
        "outlier_summary",
        "time_window_alignment",
        "warnings",
        "how_to_do_differently",
    }
    assert required_keys.issubset(answer), sorted(required_keys - set(answer))

    duplicate_key = answer.get("unique_keys", {}).get("rewards_duplicate_key", {})
    assert duplicate_key.get("duplicate_key_count") == expected["expected_duplicate_key_count"]
    assert duplicate_key.get("key_columns") == expected["expected_duplicate_key_columns"]

    join_cardinality = answer["join_cardinality"]
    assert join_cardinality["cardinality"] in {"many_to_many", "one_to_many"}
    assert join_cardinality["row_expansion_ratio"] > 1
    assert join_cardinality["row_expansion_ratio"] >= expected["expected_row_expansion_ratio_min"]

    distribution = answer["group_distribution"]
    assert distribution["treatment_count"] == expected["expected_treatment_count"]
    assert distribution["control_count"] == expected["expected_control_count"]
    assert distribution["imbalanced"] is True

    smd = answer["smd_summary"]
    assert set(expected["expected_smd_warning_columns"]).issubset(set(smd["warning_columns"]))

    outliers = answer["outlier_summary"]
    assert outliers["outlier_count"] == expected["expected_subsidy_outlier_count"]

    time_window = answer["time_window_alignment"]
    assert time_window["mismatch_count"] == expected["expected_time_window_mismatch_count"]

    warnings = "\n".join(answer["warnings"])
    assert "不能静默 drop duplicates" in warnings
    for warning in expected["expected_required_warnings"]:
        assert warning in warnings

    how_to_do_differently = "\n".join(answer["how_to_do_differently"])
    assert expected["expected_how_to_do_differently"] in how_to_do_differently
