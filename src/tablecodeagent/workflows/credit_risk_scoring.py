from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from tablecodeagent.table_tools.core import profile_table, read_table_frame
from tablecodeagent.table_tools.quality import check_missing_values, check_unique_key


DEFAULT_REQUIRED_COLUMNS = [
    "application_id",
    "user_id",
    "application_time",
    "loan_amount",
    "income",
    "age",
    "credit_score",
    "existing_debt",
    "employment_years",
    "default_90d",
]
DEFAULT_LEAKAGE_COLUMNS = ["post_loan_collection_calls"]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(task_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else task_dir / path


def _risk_band(score: float) -> str:
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _score_applications(frame: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    scored = frame.copy()
    for column in ("loan_amount", "income", "age", "credit_score", "existing_debt", "employment_years"):
        scored[column] = pd.to_numeric(scored[column], errors="coerce")
    income = scored["income"].replace(0, pd.NA)
    debt_to_income = (scored["existing_debt"] / income).fillna(0)
    loan_to_income = (scored["loan_amount"] / income).fillna(0)
    credit_component = ((680 - scored["credit_score"].fillna(680)) / 8).clip(lower=0)
    age_component = scored["age"].lt(18).fillna(False).astype(int) * 30
    employment_component = scored["employment_years"].fillna(0).lt(1).astype(int) * 10
    risk_score = (20 + debt_to_income * 25 + loan_to_income * 20 + credit_component + age_component + employment_component).clip(0, 100)
    scored["risk_score"] = risk_score.round(2)
    scored["risk_band"] = scored["risk_score"].map(_risk_band)
    band_counts = {key: int(value) for key, value in scored["risk_band"].value_counts().to_dict().items()}
    columns = ["application_id", "user_id", "risk_score", "risk_band"]
    return scored[columns].to_dict(orient="records"), band_counts


def _data_quality(frame: Any, table_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    required_columns = config.get("required_columns", DEFAULT_REQUIRED_COLUMNS)
    leakage_columns = config.get("leakage_columns", DEFAULT_LEAKAGE_COLUMNS)
    key_columns = config.get("key_columns", ["application_id"])
    missing_columns = [column for column in required_columns if column not in frame.columns]
    duplicate_key = check_unique_key(frame, key_columns)
    missing_values = check_missing_values(table_path)
    age = pd.to_numeric(frame.get("age"), errors="coerce")
    invalid_age_count = int(age.lt(18).fillna(False).sum())
    present_leakage_columns = [column for column in leakage_columns if column in frame.columns]
    return {
        "required_columns": required_columns,
        "missing_required_columns": missing_columns,
        "missing_values": missing_values,
        "duplicate_keys": duplicate_key,
        "invalid_age_count": invalid_age_count,
        "leakage_columns_present": present_leakage_columns,
    }


def _warnings(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    quality = report["data_quality"]
    if quality["duplicate_keys"]["duplicate_key_count"] > 0:
        warnings.append("duplicate_application_id")
        warnings.append("不能静默 drop duplicates；重复申请会影响坏账率和评分样本权重。")
    if quality["invalid_age_count"] > 0:
        warnings.append("invalid_age")
    for column in quality["leakage_columns_present"]:
        warnings.append(f"target_leakage_{column}")
    if report["scoring_result"]["risk_band_counts"].get("high", 0) > 0:
        warnings.append("high_risk_applications")
    return warnings


def _how_to_do_differently() -> list[str]:
    return [
        "先按 application_time 做时间切分，再拟合编码、标准化或采样规则，避免训练集看到未来信息。",
        "贷后字段、标签字段和人工催收字段不能进入贷前评分特征。",
        "重复申请样本应先报告重复比例和业务主键，再由业务规则决定保留首笔、末笔或全部样本。",
    ]


def build_credit_risk_scoring_report(task_dir: str | Path) -> dict[str, Any]:
    task_path = Path(task_dir)
    task = _read_json(task_path / "task.json")
    table_path = _resolve(task_path, task["tables"]["applications"])
    frame, _ = read_table_frame(table_path)
    config = task.get("scoring_config", {})
    quality = _data_quality(frame, table_path, config)
    score_rows, risk_band_counts = _score_applications(frame)
    report = {
        "task_id": task["id"],
        "row_counts": {"applications": len(frame)},
        "field_summary": {
            "profile": profile_table(table_path),
            "target_column": config.get("target_column", "default_90d"),
            "time_column": config.get("time_column", "application_time"),
        },
        "data_quality": quality,
        "feature_processing": {
            "numeric_features": config.get("numeric_features", [
                "loan_amount",
                "income",
                "age",
                "credit_score",
                "existing_debt",
                "employment_years",
            ]),
            "categorical_features": config.get("categorical_features", ["region"]),
            "excluded_columns": [config.get("target_column", "default_90d"), *quality["leakage_columns_present"]],
            "time_split_column": config.get("time_column", "application_time"),
        },
        "scoring_result": {
            "method": "rule_based_scorecard",
            "scored_rows": score_rows,
            "risk_band_counts": risk_band_counts,
        },
        "business_rule_checks": {
            "target_not_used_as_feature": True,
            "leakage_columns_excluded": bool(quality["leakage_columns_present"]),
            "requires_manual_review_for_high_risk": risk_band_counts.get("high", 0) > 0,
        },
        "explanations": [
            "评分示例使用可复现规则卡，不声明已训练生产模型。",
            "较高债收比、较低信用分、无稳定就业和异常年龄会提高风险分。",
        ],
        "warnings": [],
        "how_to_do_differently": _how_to_do_differently(),
    }
    report["warnings"] = _warnings(report)
    report["validation"] = {
        "passed": True,
        "checks": {
            "required_columns_present": not quality["missing_required_columns"],
            "duplicate_key_check_completed": "duplicate_key_count" in quality["duplicate_keys"],
            "invalid_age_check_completed": isinstance(quality["invalid_age_count"], int),
            "leakage_columns_excluded": all(
                column in report["feature_processing"]["excluded_columns"]
                for column in quality["leakage_columns_present"]
            ),
            "scoring_rows_match_input": len(score_rows) == len(frame),
            "business_rule_checks_present": bool(report["business_rule_checks"]),
        },
    }
    report["validation"]["passed"] = all(report["validation"]["checks"].values())
    return report


def validate_credit_risk_scoring_report(report: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    warnings_text = "\n".join(str(item) for item in report["warnings"])
    output_keys = set(report) | {"validation"}
    checks = {
        "duplicate_application_count": (
            report["data_quality"]["duplicate_keys"]["duplicate_key_count"]
            == expected["expected_duplicate_application_count"]
        ),
        "invalid_age_count": report["data_quality"]["invalid_age_count"] == expected["expected_invalid_age_count"],
        "leakage_columns": set(expected["expected_leakage_columns"]).issubset(
            set(report["data_quality"]["leakage_columns_present"])
        ),
        "high_risk_count": report["scoring_result"]["risk_band_counts"].get("high", 0) >= expected["expected_high_risk_min"],
        "required_warnings": all(warning in warnings_text for warning in expected["expected_required_warnings"]),
        "output_keys": set(expected["expected_output_keys"]).issubset(output_keys),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_credit_risk_scoring(
    task_dir: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    task_path = Path(task_dir)
    report = build_credit_risk_scoring_report(task_path)
    expected = _read_json(task_path / "expected.json")
    report["validation"] = validate_credit_risk_scoring_report(report, expected)
    if output_path:
        Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
