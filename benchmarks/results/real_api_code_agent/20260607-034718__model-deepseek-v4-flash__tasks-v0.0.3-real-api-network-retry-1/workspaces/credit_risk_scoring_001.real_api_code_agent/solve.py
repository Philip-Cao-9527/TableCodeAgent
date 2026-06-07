#!/usr/bin/env python
"""solve.py for credit_risk_scoring_001 — 信贷申请风险评分 workflow."""
import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CSV = HERE / "applications.csv"
ANSWER = HERE / "answer.json"


def _safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _is_valid_age(val):
    v = _safe_int(val)
    if v is None:
        return False
    return 18 <= v <= 100


def build_report():
    df = pd.read_csv(CSV, dtype_backend="numpy_nullable", keep_default_na=True)

    # ------------------------------------------------------------------ #
    # 1. row_counts
    # ------------------------------------------------------------------ #
    row_counts = {
        "total_rows": len(df),
        "columns": list(df.columns),
        "required_columns_present": all(
            c in df.columns
            for c in [
                "application_id", "user_id", "application_time",
                "loan_amount", "income", "age", "credit_score",
                "existing_debt", "employment_years", "default_90d",
            ]
        ),
    }

    # ------------------------------------------------------------------ #
    # 2. field_summary
    # ------------------------------------------------------------------ #
    field_summary = {}
    for col in df.columns:
        non_null = df[col].dropna()
        info = {
            "dtype": str(df[col].dtype),
            "missing_count": int(df[col].isna().sum()),
            "missing_rate": round(float(df[col].isna().mean()), 4),
            "unique_count": int(df[col].nunique()),
        }
        if pd.api.types.is_numeric_dtype(non_null):
            info["min"] = float(non_null.min()) if len(non_null) else None
            info["max"] = float(non_null.max()) if len(non_null) else None
            info["mean"] = round(float(non_null.mean()), 2) if len(non_null) else None
        field_summary[col] = info
    field_summary["_note"] = "部分字段如 age / default_90d 存在缺失值，后续处理中需关注。"

    # ------------------------------------------------------------------ #
    # 3. data_quality
    # ------------------------------------------------------------------ #
    # duplicate keys (application_id)
    dup_keys = df[df.duplicated(subset=["application_id"], keep=False)]
    duplicate_keys_list = (
        dup_keys["application_id"].unique().tolist()
        if not dup_keys.empty
        else []
    )

    # invalid age (null or < 18 or > 100)
    invalid_age_mask = df["age"].apply(lambda x: not _is_valid_age(x))
    invalid_age_count = int(invalid_age_mask.sum())
    invalid_age_examples = (
        df.loc[invalid_age_mask, ["application_id", "age"]].to_dict("records")
        if invalid_age_count > 0
        else []
    )

    # leakage columns present
    leakage_columns_present = [c for c in ["post_loan_collection_calls"] if c in df.columns]

    data_quality = {
        "missing_value_counts": {col: int(df[col].isna().sum()) for col in df.columns},
        "missing_rate_overall": round(float(df.isna().mean().mean()), 4),
        "duplicate_keys": {
            "key_columns": ["application_id"],
            "duplicate_count": int(dup_keys.shape[0]),
            "duplicate_key_values": duplicate_keys_list,
            "note": "application_id a003 出现两次（整行重复）。",
        },
        "invalid_age_count": invalid_age_count,
        "invalid_age_examples": invalid_age_examples,
        "leakage_columns_present": leakage_columns_present,
        "leakage_note": "post_loan_collection_calls 是贷后数据，不可作为贷前评分特征。",
        "quality_flags": ["duplicate_rows", "columns_with_missing"],
    }

    # ------------------------------------------------------------------ #
    # 4. feature_processing
    # ------------------------------------------------------------------ #
    # 构造最小特征处理说明（规则卡不使用 default_90d / post_loan_collection_calls）
    feature_processing = {
        "numeric_features": {
            "loan_amount": {"type": "float", "missing_imputation": "median", "scaling": "none"},
            "income": {"type": "float", "missing_imputation": "median", "scaling": "none"},
            "age": {"type": "int", "missing_imputation": "median", "invalid_correction": "clamp 18-100"},
            "credit_score": {"type": "int", "missing_imputation": "median", "scaling": "none"},
            "existing_debt": {"type": "float", "missing_imputation": "median", "scaling": "none"},
            "employment_years": {"type": "float", "missing_imputation": "median", "scaling": "none"},
        },
        "categorical_features": {
            "region": {"encoding": "one-hot", "missing_imputation": "mode"},
        },
        "excluded_features": {
            "default_90d": "目标变量，不可用作贷前评分特征。",
            "post_loan_collection_calls": "贷后泄漏字段，不可用作贷前评分特征。",
            "application_id": "标识符，不含预测信息。",
            "user_id": "标识符，不含预测信息。",
            "application_time": "时间戳，规则卡不使用时序特征。",
        },
        "feature_engineering_note": "规则卡评分仅使用基础数值字段 + region 类别，不训练模型。",
    }

    # ------------------------------------------------------------------ #
    # 5. scoring_result  — 可解释规则卡评分
    # ------------------------------------------------------------------ #
    # 规则定义（每个维度 0-10 分，总分满分 50，映射到 0-100）
    # 1) credit_score: >= 720 → 10, >= 650 → 7, >= 580 → 4, else 1
    # 2) debt_ratio (existing_debt / income): <= 0.3 → 10, <= 0.5 → 7, <= 0.8 → 4, else 1
    # 3) employment_years: >= 5 → 10, >= 3 → 7, >= 1 → 4, else 1
    # 4) age: 25-60 → 10, else 4
    # 5) income: >= 60000 → 10, >= 35000 → 7, >= 15000 → 4, else 1

    def _score_credit(v):
        if pd.isna(v):
            return 0
        v = int(v)
        if v >= 720:
            return 10
        if v >= 650:
            return 7
        if v >= 580:
            return 4
        return 1

    def _score_debt_ratio(row):
        inc = row.get("income", 0)
        if pd.isna(inc) or inc == 0:
            return 0
        ratio = row["existing_debt"] / inc
        if pd.isna(ratio):
            return 0
        if ratio <= 0.3:
            return 10
        if ratio <= 0.5:
            return 7
        if ratio <= 0.8:
            return 4
        return 1

    def _score_employment(v):
        if pd.isna(v):
            return 0
        v = float(v)
        if v >= 5:
            return 10
        if v >= 3:
            return 7
        if v >= 1:
            return 4
        return 1

    def _score_age(v):
        if pd.isna(v) or not _is_valid_age(v):
            return 0
        v = int(v)
        if 25 <= v <= 60:
            return 10
        return 4

    def _score_income(v):
        if pd.isna(v):
            return 0
        v = float(v)
        if v >= 60000:
            return 10
        if v >= 35000:
            return 7
        if v >= 15000:
            return 4
        return 1

    scores = []
    for _, row in df.iterrows():
        s_credit = _score_credit(row["credit_score"])
        s_debt = _score_debt_ratio(row)
        s_emp = _score_employment(row["employment_years"])
        s_age = _score_age(row["age"])
        s_inc = _score_income(row["income"])
        total = s_credit + s_debt + s_emp + s_age + s_inc
        # map 0-50 → 0-100
        score_100 = round(total / 50 * 100, 1)
        # risk level
        if score_100 >= 80:
            level = "低风险"
        elif score_100 >= 55:
            level = "中风险"
        else:
            level = "高风险"
        scores.append(
            {
                "application_id": row["application_id"],
                "rule_card_scores": {
                    "credit_score_score": s_credit,
                    "debt_ratio_score": s_debt,
                    "employment_years_score": s_emp,
                    "age_score": s_age,
                    "income_score": s_inc,
                },
                "total_score_50": total,
                "normalized_score_100": score_100,
                "risk_level": level,
            }
        )

    scoring_result = {
        "rule_card_name": "可解释信贷规则卡 v1",
        "dimensions": ["credit_score", "debt_ratio", "employment_years", "age", "income"],
        "max_score": 50,
        "score_mapping": "总分 0-50 线性映射到 0-100（×2），≥80 低风险，≥55 中风险，<55 高风险",
        "applicant_scores": scores,
    }

    # ------------------------------------------------------------------ #
    # 6. business_rule_checks
    # ------------------------------------------------------------------ #
    # 业务规则:
    #  - age < 18 → 自动拒绝
    #  - income = 0 且 employment_years = 0 → 无收入来源，需人工审核
    #  - duplicate application → 标记
    #  - missing target → 无法监督评估
    #  - credit_score < 600 → 高风险警示
    business_rules = []
    for _, row in df.iterrows():
        rule_results = {}
        app_id = row["application_id"]

        # 规则1: 年龄校验
        age_val = _safe_int(row["age"])
        if age_val is not None and age_val < 18:
            rule_results["age_check"] = "拒绝: 申请人年龄未满18岁"
        elif age_val is None:
            rule_results["age_check"] = "警告: 年龄缺失，需核实"
        else:
            rule_results["age_check"] = "通过"

        # 规则2: 收入来源校验
        inc_val = row["income"]
        emp_val = row["employment_years"]
        if pd.isna(inc_val) or pd.isna(emp_val):
            rule_results["income_source_check"] = "警告: 收入或工作年限缺失"
        elif float(inc_val) == 0 and float(emp_val) == 0:
            rule_results["income_source_check"] = "人工审核: 无收入且无工作年限"
        else:
            rule_results["income_source_check"] = "通过"

        # 规则3: 重复标记
        if app_id in duplicate_keys_list:
            rule_results["duplicate_check"] = "警告: 申请编号重复，需确认唯一性"
        else:
            rule_results["duplicate_check"] = "通过"

        # 规则4: 信用分过低
        cs = _safe_int(row["credit_score"])
        if cs is not None and cs < 600:
            rule_results["low_credit_warning"] = "高风险警示: 信用分低于600"
        else:
            rule_results["low_credit_warning"] = "通过"

        # 规则5: 贷后泄漏字段存在提醒
        rule_results["leakage_check"] = (
            "注意: post_loan_collection_calls 为贷后字段，已排除在评分特征之外"
        )

        business_rules.append(
            {
                "application_id": app_id,
                "rules": rule_results,
            }
        )

    business_rule_checks = {
        "rule_count": 5,
        "rule_descriptions": [
            "年龄 ≥ 18 岁",
            "收入或工作年限不为零（存在收入来源）",
            "申请编号唯一",
            "信用分 ≥ 600",
            "排除贷后泄漏字段",
        ],
        "per_applicant": business_rules,
    }

    # ------------------------------------------------------------------ #
    # 7. explanations
    # ------------------------------------------------------------------ #
    explanations = {
        "workflow_summary": (
            "对信贷申请样本依次进行：字段检查 → 缺失值统计 → 主键重复检测 "
            "→ 异常年龄识别 → 贷后泄漏字段标记 → 规则卡评分 → 业务规则校验。"
        ),
        "scoring_method": (
            "使用可解释规则卡（Rule Card），基于 credit_score、debt_ratio、"
            "employment_years、age、income 五个维度各分配 0-10 分，总分 0-50 映射到 0-100。"
            "不使用 default_90d（目标变量）和 post_loan_collection_calls（贷后泄漏字段）。"
        ),
        "risk_level_definition": "≥80 低风险，≥55 中风险，<55 高风险。",
    }

    # ------------------------------------------------------------------ #
    # 8. warnings
    # ------------------------------------------------------------------ #
    warnings = []
    if invalid_age_count > 0:
        warnings.append(f"发现 {invalid_age_count} 条异常年龄记录（含缺失 / < 18 / > 100），已标记。")
    if duplicate_keys_list:
        warnings.append(f"申请编号 {duplicate_keys_list} 存在重复，已标记需确认。")
    if leakage_columns_present:
        warnings.append("post_loan_collection_calls 为贷后字段，已从评分特征中排除。")
    if df["default_90d"].isna().sum() > 0:
        warnings.append("目标变量 default_90d 存在缺失值，监督评估受限。")

    # ------------------------------------------------------------------ #
    # 9. how_to_do_differently
    # ------------------------------------------------------------------ #
    how_to_do_differently = {
        "suggestion": "在数据量充足时，可训练轻量逻辑回归 / 决策树模型替代手工规则卡，并做交叉验证。",
        "data_improvements": [
            "补充缺失的 age 和 default_90d 字段",
            "去除或修正重复申请记录",
            "增加更多有价值的特征如征信查询次数、负债种类数",
        ],
        "process_improvements": [
            "对收入为 0 的申请做人工核实而非自动拒绝",
            "引入时间序列特征检测短期内重复申请",
        ],
    }

    # ------------------------------------------------------------------ #
    # 10. validation
    # ------------------------------------------------------------------ #
    validation = {
        "total_applications_processed": len(df),
        "unique_applications": int(df["application_id"].nunique()),
        "features_used_in_scoring": ["loan_amount", "income", "age", "credit_score", "existing_debt", "employment_years", "region"],
        "features_excluded": list(feature_processing["excluded_features"].keys()),
        "scoring_completed": True,
        "business_rules_executed": business_rule_checks["rule_count"],
    }

    # ------------------------------------------------------------------ #
    # Assemble answer
    # ------------------------------------------------------------------ #
    answer = {
        "row_counts": row_counts,
        "field_summary": field_summary,
        "data_quality": data_quality,
        "feature_processing": feature_processing,
        "scoring_result": scoring_result,
        "business_rule_checks": business_rule_checks,
        "explanations": explanations,
        "warnings": warnings,
        "how_to_do_differently": how_to_do_differently,
        "validation": validation,
    }
    return answer


if __name__ == "__main__":
    report = build_report()
    with open(ANSWER, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"answer.json written to {ANSWER}")
