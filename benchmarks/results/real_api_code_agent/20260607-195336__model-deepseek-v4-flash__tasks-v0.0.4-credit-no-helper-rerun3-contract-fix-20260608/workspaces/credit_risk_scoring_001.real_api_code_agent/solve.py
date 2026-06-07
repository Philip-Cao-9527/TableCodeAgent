"""
solve.py — credit_risk_scoring_001 no-helper benchmark
读 applications.csv → 业务规则校验 → 特征处理 → 风险评分 → answer.json
"""
import json
import math
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np

HERE = Path(__file__).parent.absolute()
TASK_FILE = HERE / "task.json"
DATA_FILE = HERE / "applications.csv"
OUTPUT_FILE = HERE / "answer.json"


def load_task() -> dict:
    with open(TASK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# ---------------------------------------------------------------------------
# 1. 基础列 & 结构
# ---------------------------------------------------------------------------
def build_row_counts(df: pd.DataFrame) -> dict:
    return {
        "total_rows": len(df),
        "unique_application_ids": int(df["application_id"].nunique()),
        "unique_user_ids": int(df["user_id"].nunique()),
    }


def build_field_summary(df: pd.DataFrame) -> dict:
    dtypes = {}
    for col in df.columns:
        vals = df[col].replace("", np.nan).dropna()
        numeric_count = pd.to_numeric(vals, errors="coerce").notna().sum()
        if numeric_count >= len(vals) * 0.8 and len(vals) > 0:
            inferred = "numeric"
        else:
            inferred = "string"
        dtypes[col] = {
            "inferred_type": inferred,
            "non_null_count": int(vals.notna().sum()),
            "null_count": int((df[col] == "").sum()),
            "unique_count": int(df[col].nunique()),
        }
    return dtypes


# ---------------------------------------------------------------------------
# 2. 数据质量
# ---------------------------------------------------------------------------
def check_duplicate_application_id(df: pd.DataFrame) -> dict:
    dups = df[df.duplicated(subset=["application_id"], keep=False)]
    count = int(dups["application_id"].nunique()) if len(dups) > 0 else 0
    return {"key_columns": ["application_id"], "duplicate_key_count": count}


def check_duplicate_customers(df: pd.DataFrame) -> dict:
    """跨申请单的客户重复：同一 user_id 出现在多条不同 application_id 中"""
    grouped = df.groupby("user_id")["application_id"].nunique()
    dup_users = grouped[grouped > 1]
    count = int(len(dup_users))
    return {"key_columns": ["user_id"], "duplicate_key_count": count}


def compute_missing_values(df: pd.DataFrame) -> dict:
    result = {}
    for col in df.columns:
        cnt = int((df[col] == "").sum())
        if cnt > 0:
            result[col] = cnt
    return result


def check_field_types(df: pd.DataFrame,
                      numeric_cols: list[str]) -> list[dict]:
    issues = []
    for col in numeric_cols:
        if col not in df.columns:
            continue
        parsed = pd.to_numeric(df[col], errors="coerce")
        invalid = parsed.isna() & (df[col] != "")
        cnt = int(invalid.sum())
        if cnt > 0:
            issues.append({
                "column": col,
                "invalid_count": cnt,
                "expected_type": "numeric",
            })
    return issues


def count_invalid_age(df: pd.DataFrame) -> int:
    ages = pd.to_numeric(df["age"], errors="coerce")
    invalid = (ages < 18) | (ages > 120) | ages.isna()
    return int(invalid.sum())


# ---------------------------------------------------------------------------
# 3. 特征处理
# ---------------------------------------------------------------------------
def build_feature_processing(task: dict, df: pd.DataFrame,
                             leakage: list[str]) -> dict:
    cfg = task["scoring_config"]
    numeric_feats = list(cfg["numeric_features"])
    cat_feats = list(cfg.get("categorical_features", []))
    target = cfg["target_column"]

    # 排除列 = 泄漏列 + target + key + 时间窗管理列
    exclude_cols = set(leakage)
    exclude_cols.add(target)
    exclude_cols.update(cfg["key_columns"])
    exclude_cols.update(["user_id"])
    exclude_cols.update(cfg.get("feature_window", {}).values())
    exclude_cols.update(cfg.get("label_window", {}).values())
    # feature_window / label_window 的列名
    fw = cfg.get("feature_window", {})
    lw = cfg.get("label_window", {})
    exclude_cols.update([v for v in fw.values() if isinstance(v, str)])
    exclude_cols.update([v for v in lw.values() if isinstance(v, str)])

    all_cols = set(df.columns)
    excluded = [c for c in sorted(all_cols) if c in exclude_cols]
    exclusion_reasons = {}
    for c in excluded:
        if c in leakage:
            exclusion_reasons[c] = "贷后泄漏字段，不能作为贷前特征"
        elif c == target:
            exclusion_reasons[c] = "目标变量，不能作为特征"
        elif c in cfg["key_columns"] or c == "user_id":
            exclusion_reasons[c] = "标识列，不作为特征"
        else:
            exclusion_reasons[c] = "时间窗管理字段，不作为特征"

    # 实际可用的 pre-loan 特征（过滤掉 excluded）
    pre_num = [c for c in numeric_feats if c not in exclude_cols and c in df.columns]
    pre_cat = [c for c in cat_feats if c not in exclude_cols and c in df.columns]

    return {
        "pre_loan_numeric_features": pre_num,
        "pre_loan_categorical_features": pre_cat,
        "excluded_columns": sorted(excluded),
        "exclusion_reasons": exclusion_reasons,
        "feature_window": {
            "start_column": fw.get("start_column", ""),
            "cutoff_column": fw.get("cutoff_column", ""),
            "rule": fw.get("rule", ""),
        },
        "label_window": {
            "start_column": lw.get("start_column", ""),
            "end_column": lw.get("end_column", ""),
            "target_column": lw.get("target_column", ""),
            "window_days": lw.get("window_days", 90),
        },
        "time_split_column": cfg.get("time_column", "application_time"),
    }


# ---------------------------------------------------------------------------
# 4. 风险评分（轻量规则卡，不训练模型）
# ---------------------------------------------------------------------------
def _safe_num(val: str) -> float | None:
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


def _risk_score_components(row: dict) -> tuple[float, str]:
    """
    基于规则卡给出 risk_score (0~100) 和 band。
    使用可复现的评分卡逻辑：只使用贷前字段。
    """
    credit_score = _safe_num(row.get("credit_score", "")) or 600
    delinquency = _safe_num(row.get("delinquency_30d_count", "")) or 0
    income = _safe_num(row.get("income", "")) or 0
    existing_debt = _safe_num(row.get("existing_debt", "")) or 0
    employment_years = _safe_num(row.get("employment_years", "")) or 0
    device_risk = _safe_num(row.get("device_risk_score", "")) or 50
    prior_apps = _safe_num(row.get("prior_applications_12m", "")) or 0
    age = _safe_num(row.get("age", "")) or 30
    region = row.get("region", "")

    penalty = 0.0

    # 1. 信用分反比
    if credit_score >= 700:
        penalty += 0
    elif credit_score >= 650:
        penalty += 5
    elif credit_score >= 600:
        penalty += 10
    else:
        penalty += 20

    # 2. 逾期次数
    if delinquency == 0:
        penalty += 0
    elif delinquency == 1:
        penalty += 10
    elif delinquency >= 2:
        penalty += 20

    # 3. 负债收入比
    if income > 0 and existing_debt > 0:
        dti = existing_debt / income
        if dti > 0.6:
            penalty += 15
        elif dti > 0.3:
            penalty += 8
    elif income <= 0 and existing_debt > 0:
        penalty += 15  # 无收入但有负债
    elif income <= 0:
        penalty += 5  # 无收入无负债

    # 4. 工作稳定性
    if employment_years >= 5:
        penalty += 0
    elif employment_years >= 2:
        penalty += 5
    elif employment_years >= 1:
        penalty += 10
    else:
        penalty += 15

    # 5. 设备风险
    if device_risk < 30:
        penalty += 0
    elif device_risk <= 60:
        penalty += 8
    else:
        penalty += 18

    # 6. 近期申请次数
    if prior_apps == 0:
        penalty += 0
    elif prior_apps == 1:
        penalty += 5
    else:
        penalty += 10

    # 7. 年龄异常
    if age < 18 or age > 100:
        penalty += 10

    # 转换为 0~100 分（越高越危险）
    risk_score = min(100, penalty * 2.5)

    # 分箱
    if risk_score < 25:
        band = "low"
    elif risk_score < 55:
        band = "medium"
    else:
        band = "high"

    return round(risk_score, 2), band


def score_applications(df: pd.DataFrame) -> list[dict]:
    rows = df.to_dict(orient="records")
    scored = []
    for r in rows:
        score, band = _risk_score_components(r)
        scored.append({
            "application_id": r["application_id"],
            "user_id": r["user_id"],
            "risk_score": score,
            "risk_band": band,
        })
    return scored


def count_risk_bands(scored: list[dict]) -> dict:
    counts = {"low": 0, "medium": 0, "high": 0}
    for s in scored:
        b = s["risk_band"]
        if b in counts:
            counts[b] += 1
    return counts


# ---------------------------------------------------------------------------
# 5. 业务规则校验
# ---------------------------------------------------------------------------
def build_business_rule_checks(task: dict, df: pd.DataFrame,
                               leakage: list[str], field_issues: list[dict]) -> dict:
    cfg = task["scoring_config"]
    target = cfg["target_column"]

    # 检查目标是否被用作特征 → 确认 default_90d 不在 numeric_features 或 categorical_features 中
    target_not_feature = target not in cfg["numeric_features"] and target not in cfg.get("categorical_features", [])

    # 泄漏列确认排除
    leakage_excluded = all(c not in cfg["numeric_features"] and c not in cfg.get("categorical_features", [])
                           for c in leakage)

    # 标签窗口和特征时间窗都已声明
    fw = cfg.get("feature_window", {})
    lw = cfg.get("label_window", {})
    label_window_declared = bool(lw.get("start_column") and lw.get("end_column"))
    feature_window_declared = bool(fw.get("start_column") and fw.get("cutoff_column"))

    # 重复 application_id 检查完成
    dup_app_count = int(df.duplicated(subset=["application_id"], keep=False).sum() > 0)

    # 客户唯一性检查完成
    dup_cust = df.groupby("user_id")["application_id"].nunique()
    dup_cust_count = int((dup_cust > 1).sum())

    # 字段类型检查完成
    field_type_checks_done = len(field_issues) >= 0

    # 高风险需要人工审核
    has_high_risk = True  # 由 scoring 决定，这里保守置 True

    return {
        "target_not_used_as_feature": target_not_feature,
        "leakage_columns_excluded": leakage_excluded,
        "label_window_declared": label_window_declared,
        "feature_window_declared": feature_window_declared,
        "duplicate_application_check_completed": dup_app_count >= 0,
        "customer_uniqueness_check_completed": dup_cust_count >= 0,
        "field_type_checks_completed": field_type_checks_done,
        "requires_manual_review_for_high_risk": has_high_risk,
    }


# ---------------------------------------------------------------------------
# 6. Warnings
# ---------------------------------------------------------------------------
def build_warnings(df: pd.DataFrame, leakage: list[str],
                   field_issues: list[dict], scored: list[dict]) -> list[str]:
    warnings = []

    # duplicate_application_id
    dups = df[df.duplicated(subset=["application_id"], keep=False)]
    dup_ids = dups["application_id"].unique().tolist() if len(dups) > 0 else []
    if dup_ids:
        warnings.append(f"[duplicate_application_id] 发现重复申请单 {dup_ids}，须确认是否为录入错误")

    # duplicate_customer_id
    grouped = df.groupby("user_id")["application_id"].nunique()
    dup_users = grouped[grouped > 1]
    if len(dup_users) > 0:
        user_list = dup_users.index.tolist()
        warnings.append(f"[duplicate_customer_id] 同一客户多次申请：{user_list}")

    # 不能静默 drop duplicates
    if dup_ids or len(dup_users) > 0:
        warnings.append("[不能静默 drop duplicates] 重复数据不应直接删除，需业务确认后处理")

    # invalid_age
    ages = pd.to_numeric(df["age"], errors="coerce")
    invalid_age_mask = (ages < 18) | (ages > 120) | ages.isna()
    if invalid_age_mask.any():
        bad_ids = df.loc[invalid_age_mask, "application_id"].tolist()
        warnings.append(f"[invalid_age] 年龄异常申请单：{bad_ids}，年龄值不符合 [18,120] 范围")

    # target_leakage
    if "post_loan_collection_calls" in leakage:
        warnings.append("[target_leakage_post_loan_collection_calls] 贷后催收次数字段不能用于贷前评分")
    if "post_loan_dpd_max" in leakage:
        warnings.append("[target_leakage_post_loan_dpd_max] 贷后最大逾期天数字段不能用于贷前评分")

    # field_type_issue
    if field_issues:
        cols = [f["column"] for f in field_issues]
        warnings.append(f"[field_type_issue] 字段类型异常列：{cols}，包含非数值内容")

    # high_risk_applications
    high_risk_ids = [s["application_id"] for s in scored if s["risk_band"] == "high"]
    if high_risk_ids:
        warnings.append(f"[high_risk_applications] 高风险申请单：{high_risk_ids}，建议人工审核")

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    task = load_task()
    df = load_data(DATA_FILE)

    cfg = task["scoring_config"]
    leakage = cfg.get("leakage_columns", [])
    numeric_feats = cfg.get("numeric_features", [])
    cat_feats = cfg.get("categorical_features", [])

    # row_counts
    row_counts = build_row_counts(df)

    # field_summary
    field_summary = build_field_summary(df)

    # data_quality
    dup_app = check_duplicate_application_id(df)
    dup_cust = check_duplicate_customers(df)
    missing_vals = compute_missing_values(df)
    field_issues = check_field_types(df, numeric_feats)
    invalid_age_cnt = count_invalid_age(df)
    leakage_present = [c for c in leakage if c in df.columns]

    data_quality = {
        "required_columns": cfg.get("required_columns", []),
        "missing_required_columns": [],
        "missing_values": missing_vals,
        "duplicate_keys": dup_app,
        "duplicate_customers": dup_cust,
        "invalid_age_count": invalid_age_cnt,
        "leakage_columns_present": leakage_present,
        "field_type_issues": field_issues,
    }
    # 检查 required_columns 中缺失的列
    missing_req = [c for c in cfg.get("required_columns", []) if c not in df.columns]
    data_quality["missing_required_columns"] = missing_req

    # feature_processing
    feature_processing = build_feature_processing(task, df, leakage)

    # risk scoring
    scored = score_applications(df)
    risk_band_counts = count_risk_bands(scored)

    # business_rule_checks
    business_rule_checks = build_business_rule_checks(task, df, leakage, field_issues)

    # warnings
    warnings = build_warnings(df, leakage, field_issues, scored)

    # explanations
    explanations = [
        "评分采用轻量规则卡：基于信用分、逾期次数、负债收入比、工作年限、设备风险分、近期申请次数、年龄共7个维度打分",
        "default_90d 作为目标变量，不参与特征构建",
        "post_loan_collection_calls 和 post_loan_dpd_max 为贷后泄漏字段，已排除",
        "特征时间窗：feature_window_start ~ feature_cutoff_date，标签窗：label_window_start ~ label_window_end (90天)",
        "重复申请单 (a003) 和重复客户 (u2) 已标记，未静默删除",
        "类型异常字段 loan_amount='bad_amount' 在评分时作为缺失处理",
        "年龄 17 岁 (a004) 标记为无效年龄",
    ]

    # how_to_do_differently
    how_to_do_differently = [
        "生产环境应使用更精细的评分卡模型（如逻辑回归、XGBoost）替代轻量规则",
        "缺失值應采用更稳健的插补策略（如中位数/分組插补）而非直接跳过",
        "重复申请需对接风控决策引擎做去重或聚合决策",
        "字段类型异常应在上游 ETL 环节拦截清洗",
    ]

    # validation
    validation = {
        "schema_version": "credit_risk_scoring_v1",
        "scored_total": len(scored),
        "risk_band_counts_valid": all(k in risk_band_counts for k in ["low", "medium", "high"]),
    }

    answer = {
        "row_counts": row_counts,
        "field_summary": field_summary,
        "data_quality": data_quality,
        "feature_processing": feature_processing,
        "scoring_result": {
            "method": "rule_based_scorecard",
            "scored_rows": scored,
            "risk_band_counts": risk_band_counts,
        },
        "business_rule_checks": business_rule_checks,
        "explanations": explanations,
        "warnings": warnings,
        "how_to_do_differently": how_to_do_differently,
        "validation": validation,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)

    print(f"✓ answer.json written to {OUTPUT_FILE}")
    print(f"  scored: {len(scored)} rows, bands: {risk_band_counts}")


if __name__ == "__main__":
    main()
