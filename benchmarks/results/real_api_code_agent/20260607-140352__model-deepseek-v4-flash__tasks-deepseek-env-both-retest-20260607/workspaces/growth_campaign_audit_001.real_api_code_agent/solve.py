"""
solve.py — growth_campaign_audit_001
营销活动样本构造数据审计
"""
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent


def load_tables(data_dir: Path):
    users = pd.read_csv(data_dir / "users.csv")
    exposure = pd.read_csv(data_dir / "campaign_exposure.csv")
    rewards = pd.read_csv(data_dir / "rewards.csv")
    orders = pd.read_csv(data_dir / "orders.csv")
    return users, exposure, rewards, orders


def compute_row_counts(users, exposure, rewards, orders):
    return {
        "users": int(len(users)),
        "campaign_exposure": int(len(exposure)),
        "rewards": int(len(rewards)),
        "orders": int(len(orders)),
    }


def compute_join_cardinality(exposure, users, rewards, orders):
    """多表 join 基数检查"""
    # 1) exposure × users (left join on user_id)
    e_u = exposure.merge(users, on="user_id", how="left")
    e_u_rows = len(e_u)
    e_u_expanded = e_u_rows > len(exposure)
    e_u_missing_users = int(e_u["city_id"].isna().sum())

    # 2) exposure × rewards (left join on user_id, campaign_id, campaign_window)
    e_r = exposure.merge(
        rewards, on=["user_id", "campaign_id", "campaign_window"], how="left"
    )
    e_r_rows = len(e_r)
    e_r_expanded = e_r_rows > len(exposure)
    e_r_missing_rewards = int(e_r["subsidy_amount"].isna().sum())

    # 3) exposure × orders (left join on user_id)
    e_o = exposure.merge(orders, on="user_id", how="left")
    e_o_rows = len(e_o)
    e_o_expanded = e_o_rows > len(exposure)
    e_o_no_orders = int(e_o["order_id"].isna().sum())

    return {
        "exposure_left_join_users": {
            "base_rows": len(exposure),
            "result_rows": e_u_rows,
            "has_expansion": e_u_expanded,
            "missing_right_rows": e_u_missing_users,
        },
        "exposure_left_join_rewards": {
            "base_rows": len(exposure),
            "result_rows": e_r_rows,
            "has_expansion": e_r_expanded,
            "missing_right_rows": e_r_missing_rewards,
        },
        "exposure_left_join_orders": {
            "base_rows": len(exposure),
            "result_rows": e_o_rows,
            "has_expansion": e_o_expanded,
            "missing_right_rows": e_o_no_orders,
        },
    }


def compute_group_distribution(exposure):
    """treatment / control 分布"""
    counts = exposure["treatment_group"].value_counts()
    total = len(exposure)
    treatment_count = int(counts.get("treatment", 0))
    control_count = int(counts.get("control", 0))
    ratio = treatment_count / control_count if control_count > 0 else float("inf")
    return {
        "treatment_count": treatment_count,
        "control_count": control_count,
        "ratio_treatment_over_control": round(ratio, 4),
        "treatment_pct": round(treatment_count / total * 100, 2) if total else 0,
        "control_pct": round(control_count / total * 100, 2) if total else 0,
    }


def compute_smd(exposure, users):
    """Standardized Mean Differences for covariates between treatment and control"""
    df = exposure.merge(users, on="user_id", how="inner")
    numeric_covs = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    categorical_covs = ["user_level"]

    treatment = df[df["treatment_group"] == "treatment"]
    control = df[df["treatment_group"] == "control"]

    results = {}
    balance_flags = []

    # Numeric SMD
    for col in numeric_covs:
        t_mean = treatment[col].mean()
        c_mean = control[col].mean()
        t_var = treatment[col].var(ddof=1)
        c_var = control[col].var(ddof=1)
        n_t = len(treatment)
        n_c = len(control)

        # pooled std
        pooled_std = math.sqrt(
            ((n_t - 1) * t_var + (n_c - 1) * c_var) / (n_t + n_c - 2)
            if (n_t + n_c - 2) > 0
            else 0
        )
        smd = (t_mean - c_mean) / pooled_std if pooled_std > 0 else 0.0
        results[col] = {
            "treatment_mean": round(float(t_mean), 4),
            "control_mean": round(float(c_mean), 4),
            "smd": round(float(smd), 4),
            "imbalanced": abs(smd) > 0.1,
        }
        if abs(smd) > 0.1:
            balance_flags.append(col)

    # Categorical: user_level — compute gap in proportions
    for col in categorical_covs:
        t_props = treatment[col].value_counts(normalize=True)
        c_props = control[col].value_counts(normalize=True)
        all_levels = sorted(set(df[col].dropna().unique()))
        level_gaps = {}
        max_gap = 0.0
        for level in all_levels:
            t_p = t_props.get(level, 0.0)
            c_p = c_props.get(level, 0.0)
            gap = abs(t_p - c_p)
            level_gaps[str(level)] = {
                "treatment_prop": round(float(t_p), 4),
                "control_prop": round(float(c_p), 4),
                "gap": round(float(gap), 4),
            }
            max_gap = max(max_gap, gap)
        results[col] = {
            "level_gaps": level_gaps,
            "max_gap": round(float(max_gap), 4),
            "imbalanced": max_gap > 0.1,
        }
        if max_gap > 0.1:
            balance_flags.append(col)

    return {
        "covariates": results,
        "imbalanced_covariates": balance_flags,
        "smd_threshold": 0.1,
    }


def compute_outliers(rewards):
    """IQR-based subsidy outlier detection"""
    amounts = rewards["subsidy_amount"].dropna()
    if len(amounts) < 4:
        return {
            "iqr_result": "insufficient_data",
            "outlier_count": 0,
            "outlier_details": [],
            "note": "数据量不足，无法计算 IQR 离群值",
        }

    q1 = amounts.quantile(0.25)
    q3 = amounts.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = rewards[
        (rewards["subsidy_amount"].notna())
        & ((rewards["subsidy_amount"] < lower) | (rewards["subsidy_amount"] > upper))
    ]
    details = []
    for _, row in outliers.iterrows():
        details.append({
            "user_id": str(row["user_id"]),
            "subsidy_amount": float(row["subsidy_amount"]),
            "reason": "过高" if row["subsidy_amount"] > upper else "过低",
        })

    return {
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_bound": round(float(lower), 2),
        "upper_bound": round(float(upper), 2),
        "outlier_count": len(details),
        "outlier_details": details,
    }


def compute_time_window_alignment(exposure, orders):
    """检查订单时间是否在 campaign 窗口内"""
    df = exposure.merge(orders, on="user_id", how="inner")
    misaligned_rows = []

    for _, row in df.iterrows():
        window_str = str(row["campaign_window"])
        order_time = str(row["order_time"])
        try:
            if ":" in window_str:
                parts = window_str.split(":")
                start_str, end_str = parts[0], parts[1]
                start = pd.Timestamp(start_str)
                end = pd.Timestamp(end_str)
            else:
                start = end = pd.Timestamp(window_str)
            ot = pd.Timestamp(order_time)
            if ot < start or ot > end:
                misaligned_rows.append({
                    "user_id": str(row["user_id"]),
                    "order_id": str(row["order_id"]),
                    "order_time": order_time,
                    "campaign_window": window_str,
                    "window_start": str(start.date()),
                    "window_end": str(end.date()),
                })
        except Exception:
            misaligned_rows.append({
                "user_id": str(row["user_id"]),
                "order_id": str(row["order_id"]),
                "order_time": order_time,
                "campaign_window": window_str,
                "error": "无法解析时间窗口",
            })

    return {
        "total_orders_with_exposure": len(df),
        "misaligned_count": len(misaligned_rows),
        "misaligned_details": misaligned_rows,
    }


def build_warnings(row_counts, join_info, group_dist, smd_summary, outliers, time_alignment):
    """汇总风险标签与中文业务提示"""
    warnings_list = []

    # 1) 数据缺失
    # 2) Join expansion
    for key, info in join_info.items():
        if info.get("has_expansion"):
            warnings_list.append({
                "tag": "JOIN_EXPANSION",
                "detail": f"{key} 产生了行数膨胀（{info['result_rows']} vs {info['base_rows']} 条），请检查是否存在一对多关系",
            })
        if info.get("missing_right_rows", 0) > 0:
            warnings_list.append({
                "tag": "JOIN_MISSING_RIGHT",
                "detail": f"{key} 有 {info['missing_right_rows']} 条记录未能匹配到右表数据",
            })

    # 3) Treatment / control imbalance
    ratio = group_dist["ratio_treatment_over_control"]
    if ratio < 0.5 or ratio > 2.0:
        warnings_list.append({
            "tag": "GROUP_IMBALANCE",
            "detail": f"treatment/control 比例 {ratio:.2f} 超出 0.5~2.0 范围，建议检查随机分桶逻辑",
        })

    # 4) SMD imbalance
    if smd_summary["imbalanced_covariates"]:
        warnings_list.append({
            "tag": "COVARIATE_IMBALANCE",
            "detail": f"协变量 {smd_summary['imbalanced_covariates']} 的 SMD 超过阈值 0.1，treatment/control 组间存在系统性偏差",
        })

    # 5) Subsidy outliers
    if outliers["outlier_count"] > 0:
        warnings_list.append({
            "tag": "SUBSIDY_OUTLIER",
            "detail": f"补贴金额发现 {outliers['outlier_count']} 个离群值，请核实是否存在异常发放或灌水风险",
        })

    # 6) Time window misalignment
    if time_alignment["misaligned_count"] > 0:
        warnings_list.append({
            "tag": "TIME_WINDOW_MISALIGN",
            "detail": f"有 {time_alignment['misaligned_count']} 笔订单的订单时间不在 campaign_window 范围内，可能存在时间窗口错配",
        })

    return warnings_list


def build_how_to_do_differently():
    """改进建议"""
    return [
        "建议在数据录入阶段即对 user_id 做外键约束，避免 join 时出现悬空记录",
        "建议在分桶时进行 stratified sampling，确保 treatment/control 在关键协变量上平衡",
        "建议对 subsidy_amount 设置业务合理阈值，在发放环节拦截异常值",
        "建议在 campaign_window 设计时前后各加缓冲天（grace period），减少时间窗口边界截断问题",
        "建议增加数据质量监控 pipeline，在 ETL 完成后自动执行上述审计检查",
    ]


class NpEncoder(json.JSONEncoder):
    """Convert numpy types to native Python types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return super().default(obj)


def main():
    users, exposure, rewards, orders = load_tables(HERE)

    row_counts = compute_row_counts(users, exposure, rewards, orders)
    join_cardinality = compute_join_cardinality(exposure, users, rewards, orders)
    group_distribution = compute_group_distribution(exposure)
    smd_summary = compute_smd(exposure, users)
    outlier_summary = compute_outliers(rewards)
    time_window_alignment = compute_time_window_alignment(exposure, orders)
    warnings = build_warnings(
        row_counts, join_cardinality, group_distribution,
        smd_summary, outlier_summary, time_window_alignment
    )
    how_to_do_differently = build_how_to_do_differently()

    answer = {
        "row_counts": row_counts,
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings,
        "how_to_do_differently": how_to_do_differently,
    }

    out_path = HERE / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2, cls=NpEncoder)

    print(f"answer.json written to {out_path}")
    print(f"row_counts: {row_counts}")
    print(f"warnings count: {len(warnings)}")


if __name__ == "__main__":
    main()
