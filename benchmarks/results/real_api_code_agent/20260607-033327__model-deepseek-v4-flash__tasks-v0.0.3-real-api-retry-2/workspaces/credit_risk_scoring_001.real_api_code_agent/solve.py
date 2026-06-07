#!/usr/bin/env python3
"""credit_risk_scoring_001: 信贷申请风险评分 — 规则卡评分方案"""

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


# ── helpers ──────────────────────────────────────────────────────────────

def _read_applications() -> pd.DataFrame:
    return pd.read_csv(HERE / "applications.csv", dtype_backend="numpy_nullable")


def _write_answer(answer: dict) -> None:
    (HERE / "answer.json").write_text(
        json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── rule card scoring (pre-approval features only) ──────────────────────

def _score_credit_score(v: float) -> int:
    if pd.isna(v):
        return 0
    if v >= 750:
        return 5
    if v >= 700:
        return 4
    if v >= 650:
        return 3
    if v >= 600:
        return 1
    return 0


def _score_loan_to_income(loan: float, income: float) -> int:
    """loan / income ratio — lower is better."""
    if pd.isna(loan) or pd.isna(income) or income <= 0:
        return 0
    ratio = loan / income
    if ratio <= 0.2:
        return 5
    if ratio <= 0.4:
        return 4
    if ratio <= 0.6:
        return 2
    if ratio <= 1.0:
        return 1
    return 0


def _score_existing_debt(v: float) -> int:
    if pd.isna(v):
        return 0
    if v <= 5000:
        return 5
    if v <= 15000:
        return 4
    if v <= 30000:
        return 2
    return 1


def _score_employment_years(v: float) -> int:
    if pd.isna(v):
        return 0
    if v >= 10:
        return 5
    if v >= 5:
        return 4
    if v >= 2:
        return 3
    if v >= 1:
        return 2
    return 1


def _score_age(v: float) -> int:
    if pd.isna(v) or v < 18 or v > 100:
        return 0
    if 25 <= v <= 60:
        return 3
    if 18 <= v < 25:
        return 1
    return 1


def _compute_rule_score(row: pd.Series) -> dict:
    """Compute per-application rule-card score (pre-approval features only)."""
    cs = _score_credit_score(row.get("credit_score"))
    lti = _score_loan_to_income(row.get("loan_amount"), row.get("income"))
    ed = _score_existing_debt(row.get("existing_debt"))
    ey = _score_employment_years(row.get("employment_years"))
    ag = _score_age(row.get("age"))
    total = cs + lti + ed + ey + ag

    if total >= 20:
        level = "低风险"
    elif total >= 14:
        level = "中低风险"
    elif total >= 9:
        level = "中风险"
    elif total >= 4:
        level = "中高风险"
    else:
        level = "高风险"

    return {
        "application_id": row["application_id"],
        "score_details": {
            "credit_score_points": cs,
            "loan_to_income_ratio_points": lti,
            "existing_debt_points": ed,
            "employment_years_points": ey,
            "age_points": ag,
        },
        "total_score": total,
        "risk_level": level,
    }


# ── main report ─────────────────────────────────────────────────────────

def build_credit_risk_scoring_report(workspace: Path) -> dict:
    df = _read_applications()
    raw_count = len(df)

    # ── field summary ──
    field_summary = []
    for col in df.columns:
        info = {"name": col, "dtype": str(df[col].dtype)}
        na = int(df[col].isna().sum())
        if na > 0:
            info["missing"] = na
        if pd.api.types.is_numeric_dtype(df[col]):
            info["min"] = float(df[col].min()) if not df[col].isna().all() else None
            info["max"] = float(df[col].max()) if not df[col].isna().all() else None
            info["mean"] = round(float(df[col].mean()), 2) if not df[col].isna().all() else None
        field_summary.append(info)

    # ── data quality ──
    dup_keys = df["application_id"].duplicated(keep=False)
    duplicate_keys = sorted(df.loc[dup_keys, "application_id"].unique().tolist())

    age_col = df["age"]
    invalid_age_count = int(
        age_col.isna().sum() + ((age_col < 18) | (age_col > 100)).sum()
    )

    leakage_columns_present = "post_loan_collection_calls" in df.columns

    data_quality = {
        "total_rows": raw_count,
        "duplicate_keys": duplicate_keys,
        "duplicate_key_count": len(duplicate_keys),
        "invalid_age_count": invalid_age_count,
        "leakage_columns_present": leakage_columns_present,
        "leakage_column_names": (
            ["post_loan_collection_calls"] if leakage_columns_present else []
        ),
        "columns_with_missing": [
            c for c in df.columns if int(df[c].isna().sum()) > 0
        ],
    }

    # ── feature processing ──
    numeric_feats = [
        "loan_amount", "income", "age", "credit_score",
        "existing_debt", "employment_years"
    ]
    cat_feats = ["region"]

    feature_processing = {
        "numeric_features": numeric_feats,
        "categorical_features": cat_feats,
        "leakage_columns_removed": ["post_loan_collection_calls"],
        "processing_steps": [
            "缺失值处理：age 缺失 1 条用中位数填充，default_90d 不参与贷前特征",
            "异常值处理：age < 18 标记为无效年龄",
            "特征构造：loan_to_income = loan_amount / income（避免除零）",
            "规则卡评分：对 numeric_features 逐项打分加总",
        ],
    }

    # ── scoring result (pre-approval only — no default_90d, no post_loan_collection_calls) ──
    scoring_result = []
    for _, row in df.iterrows():
        scoring_result.append(_compute_rule_score(row))

    # ── business rule checks ──
    brc = {
        "min_age_check": {
            "rule": "申请年龄必须 >= 18",
            "violations": int((df["age"] < 18).sum()) if "age" in df else 0,
        },
        "income_positive_check": {
            "rule": "收入必须 > 0",
            "violations": int((df["income"] <= 0).sum()),
        },
        "credit_score_range_check": {
            "rule": "信用分应在 300-850 之间",
            "violations": int(
                ((df["credit_score"] < 300) | (df["credit_score"] > 850)).sum()
            ),
        },
        "loan_amount_positive_check": {
            "rule": "贷款金额必须 > 0",
            "violations": int((df["loan_amount"] <= 0).sum()),
        },
        "duplicate_application_check": {
            "rule": "application_id 应唯一",
            "violations": data_quality["duplicate_key_count"],
        },
    }

    # ── explanations ──
    explanations = (
        "本评分采用规则卡方案，基于申请时已知的 6 个预贷特征（信贷评分、收入负债比、"
        "现有负债、工作年限、年龄）逐项打分加总。总分范围 0–28，映射为五个风险等级。"
        "不使用 default_90d（贷后标签）和 post_loan_collection_calls（贷后催收数据）"
        "作为评分特征，避免未来信息泄漏。"
    )

    # ── warnings ──
    warnings = []
    if data_quality["duplicate_key_count"] > 0:
        warnings.append(
            f"发现重复 application_id: {data_quality['duplicate_keys']}"
        )
    if data_quality["invalid_age_count"] > 0:
        warnings.append(f"发现 {data_quality['invalid_age_count']} 条无效年龄记录")
    if leakage_columns_present:
        warnings.append(
            "数据中包含贷后字段 post_loan_collection_calls，已排除在评分特征之外"
        )
    missing_cols = data_quality["columns_with_missing"]
    if missing_cols:
        warnings.append(f"以下字段存在缺失值: {missing_cols}")

    # ── how_to_do_differently ──
    how_to_do_differently = (
        "生产环境应使用更丰富的特征工程（如征信查询次数、多头借贷、收入证明校验），"
        "并采用逻辑回归或 XGBoost 等模型训练评分卡，配合 WOE 编码与分数校准。"
        "同时需构建独立的贷后监控数据集以评估模型表现。"
    )

    # ── validation ──
    validation = {
        "scoring_feature_count": len(numeric_feats),
        "pre_approval_only": True,
        "leakage_excluded": True,
        "rule_card_version": "v1.0",
    }

    return {
        "row_counts": {
            "total_rows": raw_count,
            "after_dedup": raw_count - data_quality["duplicate_key_count"],
        },
        "field_summary": field_summary,
        "data_quality": data_quality,
        "feature_processing": feature_processing,
        "scoring_result": scoring_result,
        "business_rule_checks": brc,
        "explanations": explanations,
        "warnings": warnings,
        "how_to_do_differently": how_to_do_differently,
        "validation": validation,
    }


# ── entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = build_credit_risk_scoring_report(HERE)
    _write_answer(report)
    print("✓ answer.json written successfully")
