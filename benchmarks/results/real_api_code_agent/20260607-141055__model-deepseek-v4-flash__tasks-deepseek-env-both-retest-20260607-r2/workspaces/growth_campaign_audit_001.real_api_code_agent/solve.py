#!/usr/bin/env python3
"""growth_campaign_audit_001: solve.py

对营销活动样本构造进行数据审计：
- 多表行数 / 重复键 / join 基数
- treatment/control 分布
- 组间协变量平衡 (SMD)
- 补贴极端值 (IQR)
- 订单时间窗口错配
"""

import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent


def load_tables():
    """Load all CSV tables with proper dtypes."""
    users = pd.read_csv(HERE / "users.csv", dtype={"user_id": str, "city_id": str, "user_level": str})
    # Parse numeric columns
    users["historical_orders_30d"] = pd.to_numeric(users["historical_orders_30d"], errors="coerce").fillna(0).astype(int)
    users["historical_gmv_30d"] = pd.to_numeric(users["historical_gmv_30d"], errors="coerce").fillna(0).astype(float)
    users["active_days_30d"] = pd.to_numeric(users["active_days_30d"], errors="coerce").fillna(0).astype(int)

    exposure = pd.read_csv(HERE / "campaign_exposure.csv", dtype=str)
    exposure["treatment_group"] = exposure["treatment_group"].str.strip().str.lower()

    rewards = pd.read_csv(HERE / "rewards.csv", dtype=str)
    rewards["subsidy_amount"] = pd.to_numeric(rewards["subsidy_amount"], errors="coerce")

    orders = pd.read_csv(HERE / "orders.csv", dtype=str)
    orders["order_time"] = pd.to_datetime(orders["order_time"], errors="coerce")
    orders["gmv"] = pd.to_numeric(orders["gmv"], errors="coerce").fillna(0.0)

    return users, exposure, rewards, orders


def compute_row_counts(users, exposure, rewards, orders):
    return {
        "users": int(len(users)),
        "campaign_exposure": int(len(exposure)),
        "rewards": int(len(rewards)),
        "orders": int(len(orders)),
        "note": {
            "users_city_id_missing": int(users["city_id"].isna().sum()),
            "exposure_activity_type_missing": int(exposure["activity_type"].isna().sum()),
            "rewards_subsidy_missing": int(rewards["subsidy_amount"].isna().sum()),
        },
    }


def compute_join_cardinality(exposure, rewards, orders):
    """Check duplicate keys in exposure and join cardinality to rewards/orders."""
    dup_key_cols = ["user_id", "campaign_window"]
    join_keys = ["user_id", "campaign_id", "campaign_window"]

    # --- Duplicate check on exposure ---
    dups = exposure[exposure.duplicated(subset=dup_key_cols, keep=False)]
    dup_count = int(len(dups))
    dup_examples = []
    if dup_count > 0:
        # Deduplicate examples
        seen = set()
        for _, row in dups.iterrows():
            key = tuple(row[dup_key_cols].to_list())
            if key not in seen:
                seen.add(key)
                dup_examples.append({k: row[k] for k in dup_key_cols})
                if len(dup_examples) >= 3:
                    break

    # --- Join with rewards ---
    merged_rewards = exposure.merge(
        rewards, on=join_keys, how="left", suffixes=("_exp", "_rew"), indicator=True
    )
    rewards_one_to_many = int((merged_rewards["_merge"] == "both").sum())
    rewards_exposure_row_expansion = int(len(merged_rewards))
    rewards_missing_match = int((merged_rewards["_merge"] == "left_only").sum())

    # --- Join with orders ---
    orders_on = ["user_id"]
    merged_orders = exposure.merge(
        orders, on=orders_on, how="left", indicator=True
    )
    orders_one_to_many = int((merged_orders["_merge"] == "both").sum())
    orders_exposure_row_expansion = int(len(merged_orders))

    return {
        "duplicate_key_columns": dup_key_cols,
        "exposure_duplicate_count": dup_count,
        "exposure_duplicate_examples": dup_examples,
        "join_with_rewards": {
            "join_keys": join_keys,
            "exposure_rows_after_join": rewards_exposure_row_expansion,
            "matched_rows": rewards_one_to_many,
            "unmatched_exposure_rows": rewards_missing_match,
        },
        "join_with_orders": {
            "join_keys": orders_on,
            "exposure_rows_after_join": orders_exposure_row_expansion,
            "matched_rows": orders_one_to_many,
        },
    }


def compute_group_distribution(exposure):
    group_col = "treatment_group"
    treatment = "treatment"
    control = "control"

    counts = exposure[group_col].value_counts()
    treatment_count = int(counts.get(treatment, 0))
    control_count = int(counts.get(control, 0))
    total = treatment_count + control_count
    ratio = round(treatment_count / control_count, 4) if control_count > 0 else None

    return {
        "treatment_count": treatment_count,
        "control_count": control_count,
        "total_exposed": total,
        "treatment_control_ratio": ratio,
        "min_group_ratio_config": 0.5,
        "imbalanced": ratio is not None and (ratio < 0.5 or ratio > 2.0),
    }


def compute_smd_summary(users, exposure):
    """Compute SMD for numeric covariates and categorical balance for user_level."""
    group_col = "treatment_group"
    treatment = "treatment"
    control = "control"
    threshold = 0.1

    covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    cat_covariate = "user_level"

    df = exposure.merge(users, on="user_id", how="left")

    t = df[df[group_col] == treatment]
    c = df[df[group_col] == control]
    t_vals = t[covariates].copy()
    c_vals = c[covariates].copy()

    results = {}

    # Numeric SMD
    for col in covariates:
        t_mean = t_vals[col].mean()
        c_mean = c_vals[col].mean()
        t_var = t_vals[col].var(ddof=1)
        c_var = c_vals[col].var(ddof=1)
        pooled_std = math.sqrt((t_var + c_var) / 2.0) if (t_var + c_var) > 0 else 0.0
        smd = abs(t_mean - c_mean) / pooled_std if pooled_std > 0 else 0.0
        results[col] = {
            "treatment_mean": round(float(t_mean), 4),
            "control_mean": round(float(c_mean), 4),
            "smd": round(float(smd), 4),
            "imbalanced": smd > threshold,
        }

    # Categorical: user_level
    t_levels = t[cat_covariate].value_counts()
    c_levels = c[cat_covariate].value_counts()
    all_levels = sorted(set(list(t_levels.index) + list(c_levels.index)))
    cat_balance = []
    max_gap = 0.0
    for level in all_levels:
        t_prop = t_levels.get(level, 0) / len(t) if len(t) > 0 else 0
        c_prop = c_levels.get(level, 0) / len(c) if len(c) > 0 else 0
        gap = abs(t_prop - c_prop)
        max_gap = max(max_gap, gap)
        cat_balance.append({
            "level": level,
            "treatment_proportion": round(float(t_prop), 4),
            "control_proportion": round(float(c_prop), 4),
            "abs_diff": round(float(gap), 4),
        })

    results["user_level"] = {
        "categorical_balance": cat_balance,
        "max_proportion_gap": round(float(max_gap), 4),
        "imbalanced": max_gap > threshold,
    }

    # Overall summary
    imbalanced_cols = [k for k, v in results.items() if isinstance(v, dict) and v.get("imbalanced")]
    return {
        "smd_threshold": threshold,
        "covariates": results,
        "imbalanced_covariates": imbalanced_cols,
    }


def compute_outlier_summary(rewards):
    """IQR-based outlier detection on subsidy_amount."""
    col = "subsidy_amount"
    multiplier = 1.5

    vals = rewards[col].dropna()
    if len(vals) == 0:
        return {"column": col, "error": "no non-null values"}

    q1 = vals.quantile(0.25)
    q3 = vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    outliers = rewards[(rewards[col] < lower) | (rewards[col] > upper)]
    outlier_records = []
    for _, row in outliers.iterrows():
        outlier_records.append({
            "user_id": row["user_id"],
            "subsidy_amount": float(row[col]) if pd.notna(row[col]) else None,
        })

    return {
        "column": col,
        "iqr_multiplier": multiplier,
        "q1": round(float(q1), 4),
        "q3": round(float(q3), 4),
        "iqr": round(float(iqr), 4),
        "lower_fence": round(float(lower), 4),
        "upper_fence": round(float(upper), 4),
        "outlier_count": len(outlier_records),
        "outlier_records": outlier_records,
    }


def compute_time_window_alignment(exposure, orders):
    """Check if orders.order_time falls within the campaign_window for each user."""
    # campaign_window format: "2026-05-01:2026-05-07"
    # Each user in exposure has a campaign_window
    # orders belong to users

    # Parse campaign window
    exp = exposure[["user_id", "campaign_window"]].drop_duplicates(subset=["user_id"])
    # Parse window bounds
    windows = exp["campaign_window"].str.split(":", expand=True)
    exp = exp.assign(
        window_start=pd.to_datetime(windows[0], errors="coerce"),
        window_end=pd.to_datetime(windows[1], errors="coerce"),
    )

    merged = orders.merge(exp, on="user_id", how="left")
    merged["in_window"] = merged.apply(
        lambda r: (
            pd.notna(r["window_start"])
            and pd.notna(r["window_end"])
            and pd.notna(r["order_time"])
            and r["window_start"] <= r["order_time"] <= r["window_end"]
        ),
        axis=1,
    )

    misaligned = merged[~merged["in_window"]]
    total_orders = len(merged)
    misaligned_count = int(len(misaligned))
    misaligned_rate = round(misaligned_count / total_orders, 4) if total_orders > 0 else 0.0

    misaligned_records = []
    for _, row in misaligned.iterrows():
        misaligned_records.append({
            "user_id": str(row["user_id"]),
            "order_id": str(row["order_id"]),
            "order_time": str(row["order_time"].date()) if pd.notna(row["order_time"]) else None,
            "campaign_window": str(row["campaign_window"]) if pd.notna(row["campaign_window"]) else None,
        })

    return {
        "total_orders_checked": total_orders,
        "misaligned_count": misaligned_count,
        "misaligned_rate": misaligned_rate,
        "misaligned_records": misaligned_records,
    }


def compute_warnings(join_cardinality, group_distribution, smd_summary, outlier_summary, time_window_alignment):
    warnings = []

    # 1. Duplicate key warning
    if join_cardinality["exposure_duplicate_count"] > 0:
        warnings.append({
            "risk_tag": "DUPLICATE_EXPOSURE_KEYS",
            "severity": "high",
            "message": f"campaign_exposure 表存在 {join_cardinality['exposure_duplicate_count']} 条重复键 (user_id, campaign_window)，"
                       f"可能导致后续 join 行数膨胀，需确认样本去重逻辑。",
        })

    # 2. Unmatched exposure rows in rewards join
    unmatched = join_cardinality["join_with_rewards"]["unmatched_exposure_rows"]
    if unmatched > 0:
        warnings.append({
            "risk_tag": "REWARDS_MISSING_MATCH",
            "severity": "medium",
            "message": f"有 {unmatched} 条 exposure 记录未在 rewards 表中匹配到对应补贴记录，"
                       f"需排查 reward 发放遗漏或 join key 不匹配。",
        })

    # 3. Group imbalance
    if group_distribution["imbalanced"]:
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "severity": "medium",
            "message": f"Treatment/Control 样本比例 {group_distribution['treatment_control_ratio']} 偏离 1:1，"
                       f"可能影响因果推断的统计效力。",
        })

    # 4. SMD imbalance
    imp_cols = smd_summary["imbalanced_covariates"]
    if imp_cols:
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "severity": "high",
            "message": f"以下协变量在组间存在不平衡 (SMD > {smd_summary['smd_threshold']}): {', '.join(imp_cols)}，"
                       f"建议使用倾向得分匹配或逆概率加权进行校正。",
        })

    # 5. Outliers
    if outlier_summary["outlier_count"] > 0:
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIERS",
            "severity": "medium",
            "message": f"补贴金额存在 {outlier_summary['outlier_count']} 个 IQR 极端值 "
                       f"(上界={outlier_summary['upper_fence']})，"
                       f"最高值 {outlier_summary['outlier_records'][0]['subsidy_amount'] if outlier_summary['outlier_records'] else 'N/A'}，"
                       f"需核实是否为人工干预或数据异常。",
        })

    # 6. Time window misalignment
    if time_window_alignment["misaligned_count"] > 0:
        warnings.append({
            "risk_tag": "ORDER_TIME_MISALIGNMENT",
            "severity": "high",
            "message": f"有 {time_window_alignment['misaligned_count']} 条订单 (占比 {time_window_alignment['misaligned_rate']*100:.2f}%) "
                       f"的 order_time 不在 campaign_window 范围内，可能为 campaign 前后自然转化而非活动效果。",
        })

    # 7. Missing values
    warnings.append({
        "risk_tag": "MISSING_VALUES",
        "severity": "low",
        "message": "users.city_id、exposure.activity_type、rewards.activity_type/subsidy_amount 存在缺失值，"
                   "建议在分析前确认缺失原因并决定填充或剔除策略。",
    })

    return warnings


def compute_how_to_do_differently():
    return {
        "suggestions": [
            "1. 在实验设计阶段使用分层随机化 (stratified randomization) 确保 treatment/control 在关键协变量上平衡。",
            "2. 对 campaign_exposure 表提前做唯一键约束 (user_id, campaign_window)，防止重复曝光记录污染 join 结果。",
            "3. 补贴发放数据应与 exposure 使用相同粒度的 join key，避免 user_id 级别多对多匹配。",
            "4. 对 subsidy_amount 设置合理的上下限阈值，并在 ETL 阶段捕获异常值，减少离群值对因果估计的影响。",
            "5. 订单归属需明确时间窗口判定逻辑，建议使用 campaign_window 做半开区间 [start, end) 过滤，排除窗口边界外的自然转化。",
            "6. 对缺失值制定显式策略，例如 activity_type 缺失可按 'unknown' 归类，subsidy_amount 缺失按 0 填充或整行剔除。",
        ]
    }


def main():
    users, exposure, rewards, orders = load_tables()

    join_cardinality = compute_join_cardinality(exposure, rewards, orders)
    group_distribution = compute_group_distribution(exposure)
    smd_summary = compute_smd_summary(users, exposure)
    outlier_summary = compute_outlier_summary(rewards)
    time_window_alignment = compute_time_window_alignment(exposure, orders)
    warnings = compute_warnings(
        join_cardinality, group_distribution, smd_summary,
        outlier_summary, time_window_alignment,
    )

    answer = {
        "row_counts": compute_row_counts(users, exposure, rewards, orders),
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings,
        "how_to_do_differently": compute_how_to_do_differently(),
    }

    output_path = HERE / "answer.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)
    print(f"answer.json written to {output_path}")


if __name__ == "__main__":
    main()
