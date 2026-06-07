"""
solve.py — growth_campaign_audit_001
营销活动样本构造数据审计：多表 join、treatment/control 分布、组间平衡、补贴极端值、订单时间窗口错配。
"""
import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

WORKSPACE = Path(__file__).resolve().parent


def load_tables():
    users = pd.read_csv(WORKSPACE / "users.csv")
    exposure = pd.read_csv(WORKSPACE / "campaign_exposure.csv")
    rewards = pd.read_csv(WORKSPACE / "rewards.csv")
    orders = pd.read_csv(WORKSPACE / "orders.csv")
    # Normalise column names
    for df in (users, exposure, rewards, orders):
        df.columns = df.columns.str.strip().str.lower()
    return users, exposure, rewards, orders


def compute_row_counts(users, exposure, rewards, orders):
    return {
        "users": int(len(users)),
        "campaign_exposure": int(len(exposure)),
        "rewards": int(len(rewards)),
        "orders": int(len(orders)),
    }


def compute_join_cardinality(exposure, rewards, orders):
    """Check join cardinality between exposure → rewards and exposure → orders."""
    join_keys = ["user_id", "campaign_id", "campaign_window"]

    # exposure → rewards (left join count per exposure row)
    exp_rewards = exposure.merge(rewards, on=join_keys, how="left", suffixes=("_exp", "_rwd"))
    exp_orders = exposure.merge(orders, on=["user_id"], how="left", suffixes=("_exp", "_ord"))

    # Count rows per left-side key
    max_rewards_per_user = int(exp_rewards.groupby("user_id").size().max())
    max_orders_per_user = int(exp_orders.groupby("user_id").size().max())

    # Check for duplicate keys in exposure
    dups = exposure[exposure.duplicated(subset=["user_id", "campaign_window"], keep=False)]

    return {
        "exposure_rewards_join_keys": join_keys,
        "exposure_orders_join_keys": ["user_id"],
        "exposure_rewards_left_join_total_rows": int(len(exp_rewards)),
        "exposure_orders_left_join_total_rows": int(len(exp_orders)),
        "max_rewards_per_exposure_user": max_rewards_per_user,
        "max_orders_per_exposure_user": max_orders_per_user,
        "duplicate_key_rows_in_exposure": int(len(dups)),
    }


def compute_group_distribution(exposure):
    group_col = "treatment_group"
    dist = exposure[group_col].value_counts().to_dict()
    total = sum(dist.values())
    result = {k: {"count": int(v), "pct": round(v / total * 100, 2)} for k, v in dist.items()}
    return result


def compute_smd(exposure, users):
    """Compute SMD for numerical covariates and balance gap for categorical."""
    cfg = {
        "group_column": "treatment_group",
        "treatment_value": "treatment",
        "control_value": "control",
        "covariates": ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"],
        "smd_threshold": 0.1,
    }

    merged = exposure.merge(users, on="user_id", how="left")

    treat = merged[merged[cfg["group_column"]] == cfg["treatment_value"]]
    ctrl = merged[merged[cfg["group_column"]] == cfg["control_value"]]

    smd_results = {}
    balance_flags = []

    for cov in cfg["covariates"]:
        if cov in ("user_level",):
            # Categorical: compare proportions
            t_prop = treat[cov].value_counts(normalize=True)
            c_prop = ctrl[cov].value_counts(normalize=True)
            all_levels = sorted(set(t_prop.index) | set(c_prop.index))
            max_gap = 0.0
            level_gaps = {}
            for lv in all_levels:
                tv = t_prop.get(lv, 0.0)
                cv = c_prop.get(lv, 0.0)
                gap = abs(tv - cv)
                level_gaps[str(lv)] = {"treatment_pct": round(tv * 100, 2), "control_pct": round(cv * 100, 2), "gap": round(gap, 4)}
                max_gap = max(max_gap, gap)
            smd_results[cov] = {
                "type": "categorical",
                "max_proportion_gap": round(max_gap, 4),
                "levels": level_gaps,
            }
            if max_gap > cfg["smd_threshold"]:
                balance_flags.append(f"{cov} 最大比例差异 {max_gap:.4f} 超过阈值 {cfg['smd_threshold']}")
        else:
            # Numerical SMD
            t_vals = pd.to_numeric(treat[cov], errors="coerce").dropna()
            c_vals = pd.to_numeric(ctrl[cov], errors="coerce").dropna()
            if len(t_vals) < 2 or len(c_vals) < 2:
                smd_results[cov] = {"type": "numerical", "smd": None, "reason": "样本量不足"}
                continue
            t_mean = t_vals.mean()
            c_mean = c_vals.mean()
            t_var = t_vals.var(ddof=1)
            c_var = c_vals.var(ddof=1)
            pooled_sd = math.sqrt((t_var + c_var) / 2.0)
            if pooled_sd == 0:
                smd_val = 0.0
            else:
                smd_val = (t_mean - c_mean) / pooled_sd
            smd_results[cov] = {
                "type": "numerical",
                "smd": round(abs(smd_val), 4),
                "treatment_mean": round(float(t_mean), 2),
                "control_mean": round(float(c_mean), 2),
            }
            if abs(smd_val) > cfg["smd_threshold"]:
                balance_flags.append(f"{cov} SMD={abs(smd_val):.4f} 超过阈值 {cfg['smd_threshold']}")

    return {
        "smd_values": smd_results,
        "threshold": cfg["smd_threshold"],
        "imbalanced_covariate_count": len(balance_flags),
        "imbalance_details": balance_flags,
    }


def compute_outlier_summary(exposure, rewards):
    """Check subsidy outliers using IQR rule."""
    merged = exposure.merge(rewards, on=["user_id", "campaign_id", "campaign_window"], how="left", suffixes=("_exp", "_rwd"))
    subsidy_col = "subsidy_amount"
    vals = pd.to_numeric(merged[subsidy_col], errors="coerce").dropna()
    q1 = vals.quantile(0.25)
    q3 = vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = merged[pd.to_numeric(merged[subsidy_col], errors="coerce").between(lower, upper, inclusive="neither")]
    null_count = int(merged[subsidy_col].isna().sum()) + int((merged[subsidy_col] == "").sum())

    outlier_rows = []
    for _, row in outliers.iterrows():
        outlier_rows.append({
            "user_id": row["user_id"],
            "subsidy_amount": float(pd.to_numeric(row[subsidy_col], errors="coerce")),
        })

    return {
        "total_subsidy_records": int(len(vals)),
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_bound": round(float(lower), 2),
        "upper_bound": round(float(upper), 2),
        "outlier_count": int(len(outliers)),
        "outlier_rows": outlier_rows,
        "empty_or_null_subsidy_count": null_count,
    }


def compute_time_window_alignment(exposure, orders):
    """Check if order_time falls within campaign_window for each user."""
    merged = exposure.merge(orders, on="user_id", how="left")

    def parse_window(w):
        parts = str(w).split(":")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return None, None

    misaligned = []
    aligned_count = 0
    total_checked = 0

    for _, row in merged.iterrows():
        if pd.isna(row.get("order_time")):
            continue
        total_checked += 1
        start_str, end_str = parse_window(row.get("campaign_window", ""))
        if start_str is None:
            continue
        try:
            order_ts = pd.Timestamp(row["order_time"])
            start_ts = pd.Timestamp(start_str)
            end_ts = pd.Timestamp(end_str)
            if start_ts <= order_ts <= end_ts:
                aligned_count += 1
            else:
                misaligned.append({
                    "user_id": row["user_id"],
                    "order_id": row.get("order_id"),
                    "order_time": str(row["order_time"]),
                    "campaign_window": str(row["campaign_window"]),
                })
        except Exception:
            continue

    return {
        "total_orders_with_exposure": total_checked,
        "aligned_in_window": aligned_count,
        "misaligned_count": len(misaligned),
        "misaligned_details": misaligned,
    }


def build_warnings(row_counts, join_card, group_dist, smd_summary, outlier_summary, win_align):
    """Build risk-tagged warnings with Chinese business hints."""
    warnings = []

    # Row count sanity
    if row_counts["campaign_exposure"] != row_counts["users"]:
        warnings.append({
            "tag": "ROW_COUNT_MISMATCH",
            "message": f"用户表({row_counts['users']}行)与曝光表({row_counts['campaign_exposure']}行)行数不一致，可能存在用户未曝光或曝光记录缺失。",
        })

    # Treatment/control imbalance
    for grp, info in group_dist.items():
        if info["pct"] < 20:
            warnings.append({
                "tag": "GROUP_IMBALANCE",
                "message": f"{grp} 组占比仅 {info['pct']}%，组别严重不平衡，可能影响因果推断效力。",
            })

    # SMD imbalance
    if smd_summary["imbalanced_covariate_count"] > 0:
        warnings.append({
            "tag": "COVARIATE_IMBALANCE",
            "message": f"有 {smd_summary['imbalanced_covariate_count']} 个协变量组间不均衡：{'；'.join(smd_summary['imbalance_details'])}",
        })

    # Subsidy outliers
    if outlier_summary["outlier_count"] > 0:
        warnings.append({
            "tag": "SUBSIDY_OUTLIER",
            "message": f"补贴金额存在 {outlier_summary['outlier_count']} 个极端值（IQR法），最高值远超正常范围，请核查是否存在录入错误或特殊策略。",
        })

    # Empty subsidy
    if outlier_summary["empty_or_null_subsidy_count"] > 0:
        warnings.append({
            "tag": "MISSING_SUBSIDY",
            "message": f"有 {outlier_summary['empty_or_null_subsidy_count']} 条奖励记录补贴金额为空或缺失。",
        })

    # Time window misalignment
    mis_cnt = win_align["misaligned_count"]
    if mis_cnt > 0:
        warnings.append({
            "tag": "TIME_WINDOW_MISALIGNMENT",
            "message": f"有 {mis_cnt} 笔订单的下单时间不在用户所属 campaign 窗口内，可能为窗口外自然转化或窗口定义有误。",
        })

    # Duplicate keys in exposure
    if join_card["duplicate_key_rows_in_exposure"] > 0:
        warnings.append({
            "tag": "DUPLICATE_EXPOSURE_KEY",
            "message": f"曝光表中存在 {join_card['duplicate_key_rows_in_exposure']} 行重复的(user_id, campaign_window)键值。",
        })

    # Missing city_id in users
    warnings.append({
        "tag": "MISSING_USER_INFO",
        "message": "用户表中 city_id 列存在空值，可能影响基于地域的分层分析。",
    })

    return warnings


def main():
    users, exposure, rewards, orders = load_tables()

    row_counts = compute_row_counts(users, exposure, rewards, orders)
    join_cardinality = compute_join_cardinality(exposure, rewards, orders)
    group_distribution = compute_group_distribution(exposure)
    smd_summary = compute_smd(exposure, users)
    outlier_summary = compute_outlier_summary(exposure, rewards)
    time_window_alignment = compute_time_window_alignment(exposure, orders)
    warnings = build_warnings(row_counts, join_cardinality, group_distribution, smd_summary, outlier_summary, time_window_alignment)

    answer = {
        "row_counts": row_counts,
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings,
        "how_to_do_differently": (
            "1. 数据采集阶段：在ETL中增加主键唯一性约束和NOT NULL校验，从源头减少脏数据。"
            "2. 曝光记录：确保每个被随机分组的用户都在campaign_exposure中有且仅有一条记录，可采用upsert逻辑维护。"
            "3. 补贴录入：对subsidy_amount设置业务合理范围（如[0, 200]），超出则触发人工审核。"
            "4. 时间窗口对齐：在下单时实时校验order_time是否落在用户所属campaign_window内，标记窗口外转化。"
            "5. 组间平衡：在随机分组后立即执行SMD检查，若发现不均衡可通过分层采样或PS加权修正。"
            "6. 审计自动化：将上述检查封装为CI/CD流水线中的data quality gate，每次活动样本生成后自动触发审计报告。"
        ),
    }

    answer_path = WORKSPACE / "answer.json"
    with open(answer_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)

    print(f"✅ answer.json written to {answer_path}")


if __name__ == "__main__":
    main()
