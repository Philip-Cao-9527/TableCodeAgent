from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tablecodeagent.table_tools.core import profile_table, read_table_frame
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


DEFAULT_COVARIATES = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(task_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else task_dir / path


def _table_paths(task_dir: Path, task: dict[str, Any]) -> dict[str, Path]:
    tables = task.get("tables") or {}
    return {name: _resolve(task_dir, path) for name, path in tables.items()}


def _warning_labels(
    *,
    duplicate_key: dict[str, Any],
    join_cardinality: dict[str, Any],
    distribution: dict[str, Any],
    smd: dict[str, Any],
    outliers: dict[str, Any],
    time_window: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if duplicate_key["duplicate_key_count"] > 0:
        warnings.append("duplicate_key")
        warnings.append("不能静默 drop duplicates")
    if join_cardinality["row_expansion_detected"]:
        warnings.append("join_row_expansion")
    if join_cardinality["cardinality"] in {"one_to_many", "many_to_one", "many_to_many"}:
        warnings.append(join_cardinality["cardinality"])
    if distribution["imbalanced"]:
        warnings.append("imbalanced_treatment_control")
    for column in smd["warning_columns"]:
        warnings.append(f"smd_{column}")
    if outliers["outlier_count"] > 0:
        warnings.append("subsidy_outlier")
    if time_window["mismatch_count"] > 0:
        warnings.append("time_window_mismatch")
    return warnings


def _how_to_do_differently() -> list[str]:
    return [
        "先报告重复比例和影响样本，只有业务规则确认后才去重。",
        "不能静默 drop duplicates；应先说明 join 膨胀对样本量、补贴金额和转化统计的影响。",
        "在比较 treatment/control 前，先检查组间平衡、时间窗口和补贴极端值。",
    ]


def build_growth_campaign_audit_report(task_dir: str | Path) -> dict[str, Any]:
    task_path = Path(task_dir)
    task = _read_json(task_path / "task.json")
    paths = _table_paths(task_path, task)
    config = task.get("audit_config", {})

    users, _ = read_table_frame(paths["users"])
    exposure, _ = read_table_frame(paths["campaign_exposure"])
    rewards, _ = read_table_frame(paths["rewards"])
    orders, _ = read_table_frame(paths["orders"])

    joined_exposure_users = exposure.merge(users, on="user_id", how="left")
    row_counts = {
        "users": len(users),
        "campaign_exposure": len(exposure),
        "rewards": len(rewards),
        "orders": len(orders),
    }
    profiles = {name: profile_table(path) for name, path in paths.items()}
    missing_values = {name: check_missing_values(path) for name, path in paths.items()}
    duplicate_key_columns = config.get("duplicate_key_columns", ["user_id", "campaign_window"])
    duplicate_key = check_unique_key(rewards, duplicate_key_columns)
    join_keys = config.get("join_keys", ["user_id", "campaign_id", "campaign_window"])
    join_cardinality = check_join_cardinality(
        exposure,
        rewards,
        left_keys=join_keys,
        right_keys=join_keys,
        how="left",
    )
    distribution = check_treatment_control_distribution(
        exposure,
        group_column=config.get("group_column", "treatment_group"),
        treatment_value=config.get("treatment_value", "treatment"),
        control_value=config.get("control_value", "control"),
        min_group_ratio=float(config.get("min_group_ratio", 0.5)),
    )
    smd = calculate_smd(
        joined_exposure_users,
        group_column=config.get("group_column", "treatment_group"),
        covariates=config.get("covariates", DEFAULT_COVARIATES),
        treatment_value=config.get("treatment_value", "treatment"),
        control_value=config.get("control_value", "control"),
        threshold=float(config.get("smd_threshold", 0.1)),
    )
    outliers = check_subsidy_outliers(
        rewards,
        column=config.get("subsidy_column", "subsidy_amount"),
        iqr_multiplier=float(config.get("iqr_multiplier", 1.5)),
    )
    time_window = check_time_window_alignment(
        orders,
        exposure,
        user_key="user_id",
        order_time_column=config.get("order_time_column", "order_time"),
        campaign_window_column=config.get("campaign_window_column", "campaign_window"),
    )
    warnings = _warning_labels(
        duplicate_key=duplicate_key,
        join_cardinality=join_cardinality,
        distribution=distribution,
        smd=smd,
        outliers=outliers,
        time_window=time_window,
    )

    return {
        "task_id": task["id"],
        "row_counts": row_counts,
        "profiles": profiles,
        "missing_values": missing_values,
        "unique_keys": {
            "rewards_duplicate_key": duplicate_key,
        },
        "join_cardinality": join_cardinality,
        "group_distribution": distribution,
        "smd_summary": smd,
        "outlier_summary": outliers,
        "time_window_alignment": time_window,
        "warnings": warnings,
        "how_to_do_differently": _how_to_do_differently(),
    }


def validate_growth_campaign_audit_report(report: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "duplicate_key_count": report["unique_keys"]["rewards_duplicate_key"]["duplicate_key_count"] == expected["expected_duplicate_key_count"],
        "duplicate_key_columns": report["unique_keys"]["rewards_duplicate_key"]["key_columns"] == expected["expected_duplicate_key_columns"],
        "join_cardinality": report["join_cardinality"]["cardinality"] == expected["expected_join_cardinality"],
        "row_expansion_ratio": report["join_cardinality"]["row_expansion_ratio"] >= expected["expected_row_expansion_ratio_min"],
        "treatment_count": report["group_distribution"]["treatment_count"] == expected["expected_treatment_count"],
        "control_count": report["group_distribution"]["control_count"] == expected["expected_control_count"],
        "imbalanced_group": report["group_distribution"]["imbalanced_group"] == expected["expected_imbalanced_group"],
        "smd_warning_columns": set(expected["expected_smd_warning_columns"]).issubset(set(report["smd_summary"]["warning_columns"])),
        "subsidy_outlier_count": report["outlier_summary"]["outlier_count"] == expected["expected_subsidy_outlier_count"],
        "time_window_mismatch_count": report["time_window_alignment"]["mismatch_count"] == expected["expected_time_window_mismatch_count"],
        "how_to_do_differently": expected["expected_how_to_do_differently"] in "\n".join(report["how_to_do_differently"]),
    }
    coverage = expected_warning_coverage(report["warnings"], expected.get("expected_required_warnings", []))
    checks["required_warnings"] = not coverage["missing"]
    return {
        "passed": all(checks.values()),
        "checks": checks,
        **coverage,
    }


def run_growth_campaign_audit(
    task_dir: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    task_path = Path(task_dir)
    report = build_growth_campaign_audit_report(task_path)
    expected = _read_json(task_path / "expected.json")
    validation = validate_growth_campaign_audit_report(report, expected)
    report["validation"] = validation
    if output_path:
        Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

