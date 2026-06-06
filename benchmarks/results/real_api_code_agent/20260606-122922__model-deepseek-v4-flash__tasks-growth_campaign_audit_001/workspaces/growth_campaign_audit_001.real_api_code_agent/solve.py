#!/usr/bin/env python3
"""
solve.py — growth_campaign_audit_001
营销活动样本构造数据审计: 多表join、treatment/control分布、组间平衡、补贴极端值、订单时间窗口错配
"""

import json
import math
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

HERE = Path(__file__).resolve().parent


def load_task() -> dict:
    with open(HERE / "task.json") as f:
        return json.load(f)


def load_table(name: str) -> pd.DataFrame:
    path = HERE / f"{name}.csv"
    df = pd.read_csv(path, keep_default_na=False)
    # treat empty string as NaN for analysis (but keep track)
    df = df.replace(r"^\s*$", pd.NA, regex=True)
    return df


def audit_duplicate_keys(df: pd.DataFrame, key_cols: list[str], label: str) -> dict:
    """Check for duplicate rows based on key columns."""
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    dup_count = dup_mask.sum()
    dup_examples = []
    if dup_count > 0:
        dups = df[dup_mask].sort_values(by=key_cols)
        dup_examples = dups.head(10).to_dict(orient="records")
    return {
        "table": label,
        "key_columns": key_cols,
        "duplicate_count": int(dup_count),
        "duplicate_examples": dup_examples,
    }


def audit_join_quality(
    left: pd.DataFrame, right: pd.DataFrame, keys: list[str], left_label: str, right_label: str
) -> dict:
    """Compare key sets between two tables to find orphaned/non-matching rows."""
    # Only consider rows where all keys are non-null
    left_valid = left.dropna(subset=keys)
    right_valid = right.dropna(subset=keys)

    left_keys = left_valid[keys].astype(str).apply(lambda r: "|".join(r), axis=1)
    right_keys = right_valid[keys].astype(str).apply(lambda r: "|".join(r), axis=1)

    left_set = set(left_keys)
    right_set = set(right_keys)

    left_not_in_right = sorted(left_set - right_set)
    right_not_in_left = sorted(right_set - left_set)

    # Get example rows for non-matching keys
    left_miss_examples = []
    if left_not_in_right:
        mask = left_keys.isin(left_not_in_right)
        left_miss_examples = left_valid[mask].head(5).to_dict(orient="records")

    right_miss_examples = []
    if right_not_in_left:
        mask = right_keys.isin(right_not_in_left)
        right_miss_examples = right_valid[mask].head(5).to_dict(orient="records")

    return {
        "left_table": left_label,
        "right_table": right_label,
        "join_keys": keys,
        "left_row_count_valid": int(len(left_valid)),
        "right_row_count_valid": int(len(right_valid)),
        "left_keys_not_in_right_count": len(left_not_in_right),
        "right_keys_not_in_left_count": len(right_not_in_left),
        "left_keys_not_in_right": left_not_in_right,
        "right_keys_not_in_left": right_not_in_left,
        "left_miss_examples": left_miss_examples,
        "right_miss_examples": right_miss_examples,
    }


def audit_treatment_control_distribution(df: pd.DataFrame, group_col: str, treatment: str, control: str, min_ratio: float) -> dict:
    """Check treatment/control sample counts and ratio."""
    counts = df[group_col].value_counts()
    t_count = int(counts.get(treatment, 0))
    c_count = int(counts.get(control, 0))

    ratio = t_count / c_count if c_count > 0 else float("inf")
    ratio_pass = ratio >= min_ratio if c_count > 0 else False

    return {
        "group_column": group_col,
        "treatment_value": treatment,
        "control_value": control,
        "treatment_count": t_count,
        "control_count": c_count,
        "treatment_control_ratio": round(ratio, 4),
        "min_ratio_threshold": min_ratio,
        "ratio_pass": ratio_pass,
        "min_group_size": min(t_count, c_count),
    }


def _smd_for_numeric(t: pd.Series, c: pd.Series) -> float:
    """Compute standardized mean difference for a numeric covariate."""
    t_mean = t.mean()
    c_mean = c.mean()
    t_var = t.var(ddof=1)
    c_var = c.var(ddof=1)
    pooled_std = math.sqrt((t_var + c_var) / 2.0)
    if pooled_std == 0:
        return 0.0
    return abs(t_mean - c_mean) / pooled_std


def _smd_for_categorical(t: pd.Series, c: pd.Series, levels: list) -> float:
    """Compute categorical balance gap as max absolute proportion difference."""
    t_counts = t.value_counts()
    c_counts = c.value_counts()
    t_n = len(t)
    c_n = len(c)

    max_gap = 0.0
    for lvl in levels:
        p_t = t_counts.get(lvl, 0) / t_n if t_n > 0 else 0
        p_c = c_counts.get(lvl, 0) / c_n if c_n > 0 else 0
        gap = abs(p_t - p_c)
        max_gap = max(max_gap, gap)
    return max_gap


def audit_group_balance(
    df: pd.DataFrame, group_col: str, treatment: str, control: str,
    covariates: list[str], smd_threshold: float
) -> dict:
    """Check covariate balance between treatment and control groups."""
    t_df = df[df[group_col] == treatment].copy()
    c_df = df[df[group_col] == control].copy()

    balance_results = []
    all_pass = True
    for cov in covariates:
        if cov not in df.columns:
            continue

        t_series = t_df[cov]
        c_series = c_df[cov]

        # Infer type
        if pd.api.types.is_numeric_dtype(t_series) or pd.api.types.is_numeric_dtype(c_series):
            t_num = pd.to_numeric(t_series, errors="coerce")
            c_num = pd.to_numeric(c_series, errors="coerce")
            smd = _smd_for_numeric(t_num.dropna(), c_num.dropna())
            cov_type = "numeric"
        else:
            # Categorical
            all_levels = sorted(set(t_series.dropna().unique()).union(set(c_series.dropna().unique())))
            smd = _smd_for_categorical(t_series.dropna(), c_series.dropna(), all_levels)
            cov_type = "categorical"

        passed = smd < smd_threshold
        if not passed:
            all_pass = False

        balance_results.append({
            "covariate": cov,
            "type": cov_type,
            "smd": round(smd, 6),
            "threshold": smd_threshold,
            "passed": passed,
            "treatment_mean": round(t_num.dropna().mean(), 4) if cov_type == "numeric" else None,
            "control_mean": round(c_num.dropna().mean(), 4) if cov_type == "numeric" else None,
        })

    return {
        "group_column": group_col,
        "treatment_value": treatment,
        "control_value": control,
        "covariates_checked": covariates,
        "smd_threshold": smd_threshold,
        "all_pass": all_pass,
        "details": balance_results,
    }


def audit_subsidy_outliers(df: pd.DataFrame, subsidy_col: str) -> dict:
    """Detect extreme subsidy values using IQR rule."""
    amounts = pd.to_numeric(df[subsidy_col], errors="coerce").dropna()
    if len(amounts) == 0:
        return {"subsidy_column": subsidy_col, "error": "no valid subsidy data"}

    q1 = amounts.quantile(0.25)
    q3 = amounts.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = amounts[(amounts < lower) | (amounts > upper)]
    outlier_rows = df.loc[outliers.index].copy()
    outlier_rows[subsidy_col] = pd.to_numeric(outlier_rows[subsidy_col], errors="coerce")

    return {
        "subsidy_column": subsidy_col,
        "total_valid": int(len(amounts)),
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "lower_fence": round(lower, 4),
        "upper_fence": round(upper, 4),
        "outlier_count": int(len(outliers)),
        "outlier_examples": outlier_rows.head(10).to_dict(orient="records"),
    }


def audit_time_window_misalignment(
    exposure: pd.DataFrame, orders: pd.DataFrame,
    order_time_col: str, campaign_window_col: str,
    user_key: str = "user_id",
) -> dict:
    """Check if orders fall within campaign exposure windows."""
    results = []
    misaligned_count = 0

    for _, exp_row in exposure.iterrows():
        uid = exp_row[user_key]
        window_str = exp_row[campaign_window_col]
        if pd.isna(window_str):
            continue
        parts = str(window_str).split(":")
        if len(parts) != 2:
            continue
        try:
            window_start = pd.Timestamp(parts[0])
            window_end = pd.Timestamp(parts[1])
        except Exception:
            continue

        user_orders = orders[orders[user_key] == uid]
        for _, o_row in user_orders.iterrows():
            ot = o_row[order_time_col]
            if pd.isna(ot):
                continue
            try:
                ot_ts = pd.Timestamp(ot)
            except Exception:
                continue
            in_window = window_start <= ot_ts <= window_end
            if not in_window:
                misaligned_count += 1
                results.append({
                    "user_id": uid,
                    "order_id": str(o_row.get("order_id", "")),
                    "order_time": str(ot),
                    "campaign_window": window_str,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "in_window": False,
                })

    return {
        "order_time_column": order_time_col,
        "campaign_window_column": campaign_window_col,
        "total_checked_orders": int(len(orders)),
        "misaligned_count": misaligned_count,
        "misaligned_examples": results,
    }


def main():
    task = load_task()
    config = task["audit_config"]

    # Load tables
    exposure = load_table("campaign_exposure")
    orders = load_table("orders")
    rewards = load_table("rewards")
    users = load_table("users")

    duplicates = []
    # 1. Duplicate key check on campaign_exposure
    dup_keys = config["duplicate_key_columns"]
    duplicates.append(audit_duplicate_keys(exposure, dup_keys, "campaign_exposure"))

    # 2. Multi-table join quality
    join_keys = config["join_keys"]  # ["user_id", "campaign_id", "campaign_window"]
    # exposure -> rewards
    join_er = audit_join_quality(exposure, rewards, join_keys, "campaign_exposure", "rewards")
    # exposure -> users (only user_id)
    join_eu = audit_join_quality(exposure, users, ["user_id"], "campaign_exposure", "users")
    # exposure -> orders (only user_id)
    join_eo = audit_join_quality(exposure, orders, ["user_id"], "campaign_exposure", "orders")

    # 3. Treatment/control distribution
    group_col = config["group_column"]
    treatment = config["treatment_value"]
    control = config["control_value"]
    min_ratio = config["min_group_ratio"]
    tc_dist = audit_treatment_control_distribution(exposure, group_col, treatment, control, min_ratio)

    # 4. Group balance (SMD)
    covariates = config["covariates"]
    smd_threshold = config["smd_threshold"]
    # Merge exposure with users to get covariates for each user
    exp_users = exposure.merge(users, on="user_id", how="left")
    balance = audit_group_balance(exp_users, group_col, treatment, control, covariates, smd_threshold)

    # 5. Subsidy outliers
    subsidy_col = config["subsidy_column"]
    outliers = audit_subsidy_outliers(rewards, subsidy_col)

    # 6. Time window misalignment
    order_time_col = config["order_time_column"]
    campaign_window_col = config["campaign_window_column"]
    time_window = audit_time_window_misalignment(exposure, orders, order_time_col, campaign_window_col)

    # 7. Missing value summary across tables
    missing_summary = {}
    for tbl_name, tbl_df in [("campaign_exposure", exposure), ("orders", orders), ("rewards", rewards), ("users", users)]:
        missing_counts = tbl_df.isna().sum()
        missing_summary[tbl_name] = {
            col: int(missing_counts[col])
            for col in tbl_df.columns
            if missing_counts[col] > 0
        }

    # Assemble answer
    answer = {
        "task_id": task["id"],
        "audit_results": {
            "duplicate_key_checks": duplicates,
            "join_quality": {
                "exposure_vs_rewards": join_er,
                "exposure_vs_users": join_eu,
                "exposure_vs_orders": join_eo,
            },
            "treatment_control_distribution": tc_dist,
            "group_balance": balance,
            "subsidy_outliers": outliers,
            "time_window_misalignment": time_window,
            "missing_value_summary": missing_summary,
        },
    }

    out_path = HERE / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)

    print(f"✅ answer.json written to {out_path}")
    print(f"   Duplicate keys: {[d['duplicate_count'] for d in duplicates]}")
    print(f"   Join quality (miss keys): exp->rewards L={join_er['left_keys_not_in_right_count']} R={join_er['right_keys_not_in_left_count']}")
    print(f"   T/C ratio: {tc_dist['treatment_control_ratio']} (pass={tc_dist['ratio_pass']})")
    print(f"   Balance all pass: {balance['all_pass']}")
    print(f"   Subsidy outliers: {outliers.get('outlier_count', 'N/A')}")
    print(f"   Time window misalignments: {time_window['misaligned_count']}")


if __name__ == "__main__":
    main()
