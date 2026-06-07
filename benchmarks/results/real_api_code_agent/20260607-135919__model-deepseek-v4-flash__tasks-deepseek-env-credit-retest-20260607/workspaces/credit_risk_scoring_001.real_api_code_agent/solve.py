"""
solve.py — credit_risk_scoring_001
信贷申请风险评分 workflow：数据检查 → 质量评估 → 规则卡评分 → 业务校验
"""

import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def load_data() -> pd.DataFrame:
    df = pd.read_csv(HERE / "applications.csv", dtype_backend="numpy_nullable")
    return df


def build_row_counts(df: pd.DataFrame) -> dict:
    return {
        "total_rows": int(len(df)),
        "total_columns": int(len(df.columns)),
        "columns": list(df.columns),
    }


def build_field_summary(df: pd.DataFrame, config: dict) -> dict:
    summary = {}
    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].notna().sum()),
            "null_count": int(df[col].isna().sum()),
            "null_rate": round(float(df[col].isna().mean()), 4),
        }
        if col in config["numeric_features"]:
            num_series = pd.to_numeric(df[col], errors="coerce")
            col_info["min"] = (
                None if num_series.isna().all() else float(num_series.min())
            )
            col_info["max"] = (
                None if num_series.isna().all() else float(num_series.max())
            )
            col_info["mean"] = (
                None if num_series.isna().all() else float(round(num_series.mean(), 2))
            )
        if col in config["categorical_features"]:
            col_info["unique_values"] = int(df[col].nunique())
            col_info["value_counts"] = (
                df[col].value_counts().head(10).to_dict()
            )
        summary[col] = col_info
    return summary


def build_data_quality(df: pd.DataFrame, config: dict) -> dict:
    key_cols = config["key_columns"]

    # duplicate keys
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    dup_keys = (
        df.loc[dup_mask, key_cols].drop_duplicates().to_dict(orient="records")
        if dup_mask.any()
        else []
    )
    duplicate_keys = {
        "has_duplicates": bool(dup_mask.any()),
        "duplicate_key_values": dup_keys,
        "duplicate_row_count": int(dup_mask.sum()),
    }

    # invalid age (< 18)
    age_col = "age"
    age_series = pd.to_numeric(df[age_col], errors="coerce")
    invalid_age_mask = age_series < 18
    invalid_age_count = int(invalid_age_mask.sum())
    invalid_age_rows = (
        df.loc[invalid_age_mask, key_cols + [age_col]].to_dict(orient="records")
        if invalid_age_count > 0
        else []
    )

    # leakage columns present
    leakage_cols = config.get("leakage_columns", [])
    leakage_columns_present = {
        "has_leakage_columns": any(c in df.columns for c in leakage_cols),
        "leakage_columns_found": [c for c in leakage_cols if c in df.columns],
    }

    # missing values summary
    missing_info = {}
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            missing_info[col] = {
                "null_count": null_count,
                "null_rate": round(null_count / len(df), 4),
            }

    return {
        "duplicate_keys": duplicate_keys,
        "invalid_age_count": invalid_age_count,
        "invalid_age_rows": invalid_age_rows,
        "leakage_columns_present": leakage_columns_present,
        "missing_values": missing_info,
    }


def build_feature_processing(df: pd.DataFrame, config: dict) -> dict:
    """构造最小特征处理说明：描述每个特征将如何用于规则卡评分。"""
    features = {}
    for col in config["numeric_features"]:
        series = pd.to_numeric(df[col], errors="coerce")
        missing_count = int(series.isna().sum())
        features[col] = {
            "type": "numeric",
            "null_count": missing_count,
            "null_handling": (
                "忽略该样本（不评分）" if missing_count > 0 else "无需处理"
            ),
        }

    for col in config["categorical_features"]:
        features[col] = {
            "type": "categorical",
            "null_count": int(df[col].isna().sum()),
            "null_handling": "视为缺失类别，不参与评分",
            "encoding": "不编码（规则卡按原始值分箱）",
        }

    return {
        "note": "仅使用贷前可用特征，排除 leakage 列 (post_loan_collection_calls) 与目标列 (default_90d)。各特征通过分箱规则映射为分数，不训练模型。",
        "excluded_features": {
            "leakage_columns": config.get("leakage_columns", []),
            "target_column": [config.get("target_column")],
        },
        "features": features,
    }


def _score_credit_score(val: float) -> int:
    if pd.isna(val):
        return 0
    if val >= 700:
        return 40
    elif val >= 650:
        return 30
    elif val >= 600:
        return 20
    else:
        return 10


def _score_debt_to_income(income: float, existing_debt: float) -> int:
    if pd.isna(income) or pd.isna(existing_debt) or income <= 0:
        return 0
    ratio = existing_debt / income
    if ratio <= 0.3:
        return 20
    elif ratio <= 0.5:
        return 10
    else:
        return 5


def _score_employment_years(val: float) -> int:
    if pd.isna(val):
        return 0
    if val >= 5:
        return 15
    elif val >= 2:
        return 10
    else:
        return 5


def _score_loan_to_income(loan: float, income: float) -> int:
    if pd.isna(loan) or pd.isna(income) or income <= 0:
        return 0
    ratio = loan / income
    if ratio <= 0.3:
        return 15
    elif ratio <= 0.5:
        return 10
    else:
        return 5


def _score_age(val: float) -> int:
    if pd.isna(val):
        return 0
    if 25 <= val <= 60:
        return 10
    else:
        return 5


def compute_rule_card_score(row: dict) -> dict:
    """对单行样本用规则卡打分。"""
    cs = _score_credit_score(row.get("credit_score"))
    dti = _score_debt_to_income(row.get("income"), row.get("existing_debt"))
    emp = _score_employment_years(row.get("employment_years"))
    lti = _score_loan_to_income(row.get("loan_amount"), row.get("income"))
    age = _score_age(row.get("age"))

    total = cs + dti + emp + lti + age

    if total >= 70:
        level = "Low"
    elif total >= 50:
        level = "Medium"
    else:
        level = "High"

    return {
        "score": total,
        "max_score": 100,
        "risk_level": level,
        "breakdown": {
            "credit_score": {"score": cs, "max": 40},
            "debt_to_income_ratio": {"score": dti, "max": 20},
            "employment_years": {"score": emp, "max": 15},
            "loan_to_income_ratio": {"score": lti, "max": 15},
            "age": {"score": age, "max": 10},
        },
    }


def build_scoring_result(df: pd.DataFrame, config: dict) -> dict:
    """为每个申请计算规则卡评分（不使用 default_90d 或 post_loan_collection_calls）。"""
    key_cols = config["key_columns"]
    num_df = df.copy()
    for col in config["numeric_features"]:
        num_df[col] = pd.to_numeric(num_df[col], errors="coerce")

    results = []
    for _, row in num_df.iterrows():
        record = row.to_dict()
        # 跳过关键列为空的样本
        if any(pd.isna(record.get(k)) for k in key_cols):
            continue
        score_info = compute_rule_card_score(record)
        results.append(
            {
                "application_id": record.get("application_id"),
                "score_info": score_info,
            }
        )

    # 汇总统计
    scores = [r["score_info"]["score"] for r in results]
    risk_levels = [r["score_info"]["risk_level"] for r in results]
    level_counts = {}
    for lv in risk_levels:
        level_counts[lv] = level_counts.get(lv, 0) + 1

    return {
        "rule_card_name": "信用申请规则评分卡 v1",
        "total_scored": len(results),
        "total_skipped": int(len(df) - len(results)),
        "score_summary": {
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "mean_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "risk_level_distribution": level_counts,
        },
        "individual_results": results,
    }


def build_business_rule_checks(df: pd.DataFrame, config: dict) -> dict:
    """业务规则校验。"""
    checks = []

    # 规则 1: 年龄 >= 18
    age_series = pd.to_numeric(df["age"], errors="coerce")
    underage_count = int((age_series < 18).sum())
    checks.append(
        {
            "rule": "applicant_age >= 18",
            "passed": underage_count == 0,
            "violation_count": underage_count,
            "detail": "存在年龄小于 18 岁的申请者" if underage_count > 0 else "全部满足",
        }
    )

    # 规则 2: 收入 > 0
    income_series = pd.to_numeric(df["income"], errors="coerce")
    zero_income_count = int((income_series <= 0).sum())
    checks.append(
        {
            "rule": "income > 0",
            "passed": zero_income_count == 0,
            "violation_count": zero_income_count,
            "detail": "存在收入为 0 或负数的申请者" if zero_income_count > 0 else "全部满足",
        }
    )

    # 规则 3: 贷款金额合法
    loan_series = pd.to_numeric(df["loan_amount"], errors="coerce")
    invalid_loan_count = int((loan_series <= 0).sum())
    checks.append(
        {
            "rule": "loan_amount > 0",
            "passed": invalid_loan_count == 0,
            "violation_count": invalid_loan_count,
            "detail": "存在贷款金额 <= 0 的申请" if invalid_loan_count > 0 else "全部满足",
        }
    )

    # 规则 4: 就业年限 >= 0
    emp_series = pd.to_numeric(df["employment_years"], errors="coerce")
    neg_emp_count = int((emp_series < 0).sum())
    checks.append(
        {
            "rule": "employment_years >= 0",
            "passed": neg_emp_count == 0,
            "violation_count": neg_emp_count,
            "detail": "存在就业年限为负数的申请" if neg_emp_count > 0 else "全部满足",
        }
    )

    # 规则 5: credit_score 在合理范围 (300-850)
    cs_series = pd.to_numeric(df["credit_score"], errors="coerce")
    invalid_cs_count = int(((cs_series < 300) | (cs_series > 850)).sum())
    checks.append(
        {
            "rule": "300 <= credit_score <= 850",
            "passed": invalid_cs_count == 0,
            "violation_count": invalid_cs_count,
            "detail": "存在信用分超出合理范围的申请" if invalid_cs_count > 0 else "全部满足",
        }
    )

    return {"rule_checks": checks}


def build_explanations() -> list:
    return [
        "评分卡使用 5 个贷前可用特征：credit_score, debt_to_income_ratio, employment_years, loan_to_income_ratio, age",
        "credit_score 分箱：>=700(40分), 650-699(30分), 600-649(20分), <600(10分)",
        "debt_to_income_ratio 分箱：<=0.3(20分), 0.3-0.5(10分), >0.5(5分)",
        "employment_years 分箱：>=5年(15分), 2-5年(10分), <2年(5分)",
        "loan_to_income_ratio 分箱：<=0.3(15分), 0.3-0.5(10分), >0.5(5分)",
        "age 分箱：25-60岁(10分), 其他(5分)",
        "总分区间 0-100，>=70 低风险，50-69 中风险，<50 高风险",
        "default_90d 和 post_loan_collection_calls 被明确排除在贷前评分特征之外",
        "存在重复主键(a003)的样本在评分时分别输出，但业务校验标记为数据质量问题",
    ]


def build_warnings(df: pd.DataFrame, config: dict, dq: dict) -> list:
    warnings = []
    if dq["duplicate_keys"]["has_duplicates"]:
        warnings.append(
            f"主键重复：application_id={dq['duplicate_keys']['duplicate_key_values']}，共 {dq['duplicate_keys']['duplicate_row_count']} 行"
        )
    if dq["invalid_age_count"] > 0:
        warnings.append(f"存在 {dq['invalid_age_count']} 条申请年龄小于 18 岁")
    if dq["leakage_columns_present"]["has_leakage_columns"]:
        warnings.append(
            f"数据中包含贷后泄漏列：{dq['leakage_columns_present']['leakage_columns_found']}，已排除在评分特征之外"
        )
    missing_cols = [
        col for col, info in dq["missing_values"].items()
    ]
    if missing_cols:
        warnings.append(f"存在缺失值的列：{missing_cols}")
    return warnings


def build_how_to_do_differently() -> list:
    return [
        "在生产环境中应使用更丰富的特征工程（如征信查询次数、多头借贷数等）",
        "规则卡权重可以通过历史违约率统计或专家评分法校准",
        "缺失值处理可以采用中位数/均值填充或模型预测填充，而非直接跳过",
        "可考虑使用逻辑回归或 GBDT 模型替代规则卡以提高区分度",
        "应建立样本外验证集评估评分卡的 KS/AR 值",
        "重复主键需要在上游 ETL 层做去重或业务主键校验",
        "贷后泄漏列应在数据抽取阶段就排除，而非在评分阶段处理",
    ]


def build_validation(df: pd.DataFrame, config: dict) -> dict:
    """输出验证信息以确保契约合规。"""
    leakage_cols = config.get("leakage_columns", [])
    target = config.get("target_column")
    used_features = config.get("numeric_features", []) + config.get(
        "categorical_features", []
    )
    leakage_used = [c for c in leakage_cols if c in used_features]
    target_used = [target] if target in used_features else []
    return {
        "leakage_columns_excluded_from_features": leakage_cols,
        "target_column_excluded_from_features": [target],
        "any_forbidden_feature_used": len(leakage_used) == 0 and len(target_used) == 0,
        "forbidden_features_if_any": leakage_used + target_used,
    }


def main():
    df = load_data()
    config = {
        "key_columns": ["application_id"],
        "target_column": "default_90d",
        "time_column": "application_time",
        "required_columns": [
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
        ],
        "numeric_features": [
            "loan_amount",
            "income",
            "age",
            "credit_score",
            "existing_debt",
            "employment_years",
        ],
        "categorical_features": ["region"],
        "leakage_columns": ["post_loan_collection_calls"],
    }

    answer = {
        "row_counts": build_row_counts(df),
        "field_summary": build_field_summary(df, config),
        "data_quality": build_data_quality(df, config),
        "feature_processing": build_feature_processing(df, config),
        "scoring_result": build_scoring_result(df, config),
        "business_rule_checks": build_business_rule_checks(df, config),
        "explanations": build_explanations(),
        "warnings": build_warnings(df, config, build_data_quality(df, config)),
        "how_to_do_differently": build_how_to_do_differently(),
        "validation": build_validation(df, config),
    }

    output_path = HERE / "answer.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)

    print(f"answer.json 已写入: {output_path}")


if __name__ == "__main__":
    main()
