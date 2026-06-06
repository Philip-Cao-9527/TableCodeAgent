from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tablecodeagent.table_tools.quality import (
    calculate_smd,
    check_join_cardinality,
    check_missing_values,
    check_subsidy_outliers,
    check_time_window_alignment,
    check_treatment_control_distribution,
    check_unique_key,
    expected_warning_coverage,
)


TASK_DIR = Path("benchmarks/tasks/growth_campaign_audit_001")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_growth_quality_functions_match_expected_check() -> None:
    task = _read_json(TASK_DIR / "task.json")
    expected = _read_json(TASK_DIR / "expected.json")
    paths = {name: TASK_DIR / value for name, value in task["tables"].items()}

    exposure_users = pd.read_csv(paths["campaign_exposure"]).merge(
        pd.read_csv(paths["users"]),
        on="user_id",
        how="left",
    )

    missing = {name: check_missing_values(path) for name, path in paths.items()}
    duplicate_key = check_unique_key(paths["rewards"], task["audit_config"]["duplicate_key_columns"])
    join_cardinality = check_join_cardinality(
        paths["campaign_exposure"],
        paths["rewards"],
        left_keys=task["audit_config"]["join_keys"],
        right_keys=task["audit_config"]["join_keys"],
        how="left",
    )
    distribution = check_treatment_control_distribution(paths["campaign_exposure"])
    smd = calculate_smd(
        exposure_users,
        group_column="treatment_group",
        covariates=task["audit_config"]["covariates"],
    )
    outliers = check_subsidy_outliers(paths["rewards"])
    time_window = check_time_window_alignment(paths["orders"], paths["campaign_exposure"])

    warnings = ["duplicate_key", "不能静默 drop duplicates"]
    warnings.extend(["join_row_expansion", join_cardinality["cardinality"]])
    warnings.append("imbalanced_treatment_control")
    warnings.extend([f"smd_{column}" for column in smd["warning_columns"]])
    warnings.extend(["subsidy_outlier", "time_window_mismatch"])
    coverage = expected_warning_coverage(warnings, expected["expected_required_warnings"])

    assert sum(item["total_missing"] for item in missing.values()) == 4
    assert duplicate_key["duplicate_key_count"] == expected["expected_duplicate_key_count"]
    assert join_cardinality["cardinality"] == expected["expected_join_cardinality"]
    assert join_cardinality["row_expansion_ratio"] >= expected["expected_row_expansion_ratio_min"]
    assert distribution["treatment_count"] == expected["expected_treatment_count"]
    assert distribution["control_count"] == expected["expected_control_count"]
    assert set(expected["expected_smd_warning_columns"]).issubset(set(smd["warning_columns"]))
    assert outliers["outlier_count"] == expected["expected_subsidy_outlier_count"]
    assert time_window["mismatch_count"] == expected["expected_time_window_mismatch_count"]
    assert coverage["missing"] == []
