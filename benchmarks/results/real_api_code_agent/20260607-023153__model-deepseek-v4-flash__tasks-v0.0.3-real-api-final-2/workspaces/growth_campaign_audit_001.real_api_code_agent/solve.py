"""
solve.py — 营销活动样本构造数据审计 (growth_campaign_audit_001)
输出 answer.json，包含 output_contract 规定的所有字段。
"""
import json
import os
import math
from collections import Counter

import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_csv(name):
    return pd.read_csv(os.path.join(SCRIPT_DIR, name), dtype=str, keep_default_na=False).replace("", np.nan)


def parse_window(w):
    """Parse 'YYYY-MM-DD:YYYY-MM-DD' into (start_date, end_date) as pd.Timestamp."""
    parts = w.split(":")
    return pd.to_datetime(parts[0]), pd.to_datetime(parts[1])


def main():
    # 1. Load tables
    users = load_csv("users.csv")
    campaign_exposure = load_csv("campaign_exposure.csv")
    rewards = load_csv("rewards.csv")
    orders = load_csv("orders.csv")

    # Convert numeric columns
    for col in ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]:
        users[col] = pd.to_numeric(users[col], errors="coerce")
    users["city_id"] = pd.to_numeric(users["city_id"], errors="coerce")

    rewards["subsidy_amount"] = pd.to_numeric(rewards["subsidy_amount"], errors="coerce")
    orders["gmv"] = pd.to_numeric(orders["gmv"], errors="coerce")

    # 2. row_counts
    row_counts = {
        "users": int(len(users)),
        "campaign_exposure": int(len(campaign_exposure)),
        "orders": int(len(orders)),
        "rewards": int(len(rewards)),
    }

    # 3. join_cardinality — campaign_exposure LEFT JOIN orders on user_id
    exp_orders = campaign_exposure.merge(orders, on="user_id", how="left", suffixes=("", "_order"))
    # campaign_exposure LEFT JOIN rewards on [user_id, campaign_id, campaign_window]
    exp_rewards = campaign_exposure.merge(
        rewards, on=["user_id", "campaign_id", "campaign_window"], how="left", suffixes=("", "_reward")
    )

    join_cardinality = {
        "exposure_to_orders": {
            "left_table": "campaign_exposure",
            "right_table": "orders",
            "join_keys": ["user_id"],
            "left_row_count": int(len(campaign_exposure)),
            "right_row_count": int(len(orders)),
            "joined_row_count": int(len(exp_orders)),
            "cardinality": "one_to_many",
            "row_expansion_detected": len(exp_orders) > len(campaign_exposure),
        },
        "exposure_to_rewards": {
            "left_table": "campaign_exposure",
            "right_table": "rewards",
            "join_keys": ["user_id", "campaign_id", "campaign_window"],
            "left_row_count": int(len(campaign_exposure)),
            "right_row_count": int(len(rewards)),
            "joined_row_count": int(len(exp_rewards)),
            "cardinality": "one_to_many",
            "row_expansion_detected": len(exp_rewards) > len(campaign_exposure),
        },
    }

    # 4. group_distribution
    gd = campaign_exposure["treatment_group"].value_counts()
    treatment_cnt = gd.get("treatment", 0)
    control_cnt = gd.get("control", 0)
    group_distribution = {
        "treatment_count": int(treatment_cnt),
        "control_count": int(control_cnt),
        "minority_to_majority_ratio": round(
            min(treatment_cnt, control_cnt) / max(treatment_cnt, control_cnt), 4
        ),
        "imbalanced": min(treatment_cnt, control_cnt) / max(treatment_cnt, control_cnt) < 0.5,
    }

    # 5. smd_summary — join campaign_exposure with users, compute SMD per covariate
    exp_users = campaign_exposure.merge(users, on="user_id", how="left")
    treat = exp_users[exp_users["treatment_group"] == "treatment"]
    control = exp_users[exp_users["treatment_group"] == "control"]

    covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    categorical_covariates = ["user_level"]
    smd_results = {}

    for col in covariates:
        t_vals = treat[col].dropna()
        c_vals = control[col].dropna()
        if len(t_vals) < 2 or len(c_vals) < 2:
            smd_results[col] = {"smd": None, "note": "insufficient_data"}
            continue
        t_mean, t_std = t_vals.mean(), t_vals.std(ddof=1)
        c_mean, c_std = c_vals.mean(), c_vals.std(ddof=1)
        pooled_std = math.sqrt((t_std**2 + c_std**2) / 2)
        if pooled_std < 1e-10:
            smd = 0.0
        else:
            smd = (t_mean - c_mean) / pooled_std
        smd_results[col] = {
            "smd": round(smd, 6),
            "treatment_mean": round(t_mean, 4),
            "control_mean": round(c_mean, 4),
            "exceeds_threshold": abs(smd) > 0.1,
        }

    # Categorical: user_level — compute balance gap (proportion difference)
    for col in categorical_covariates:
        t_cat = treat[col].value_counts(normalize=True)
        c_cat = control[col].value_counts(normalize=True)
        all_levels = sorted(set(list(t_cat.index) + list(c_cat.index)))
        gaps = {}
        max_gap = 0.0
        for lv in all_levels:
            p_t = t_cat.get(lv, 0.0)
            p_c = c_cat.get(lv, 0.0)
            gap = abs(p_t - p_c)
            gaps[lv] = {"treatment_prop": round(p_t, 4), "control_prop": round(p_c, 4), "gap": round(gap, 4)}
            max_gap = max(max_gap, gap)
        smd_results[col] = {
            "type": "categorical",
            "level_gaps": gaps,
            "max_gap": round(max_gap, 4),
            "exceeds_threshold": max_gap > 0.1,
        }

    n_imbalanced = sum(
        1 for v in smd_results.values()
        if isinstance(v, dict) and v.get("exceeds_threshold")
    )
    smd_summary = {
        "covariates": smd_results,
        "n_imbalanced": n_imbalanced,
        "imbalanced_covariates": [
            k for k, v in smd_results.items()
            if isinstance(v, dict) and v.get("exceeds_threshold")
        ],
    }

    # 6. outlier_summary — subsidy IQR rule
    sub_vals = rewards["subsidy_amount"].dropna()
    q1 = sub_vals.quantile(0.25)
    q3 = sub_vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = rewards[rewards["subsidy_amount"] > upper]
    outlier_summary = {
        "column": "subsidy_amount",
        "method": "iqr",
        "lower_bound": round(lower, 4),
        "upper_bound": round(upper, 4),
        "outlier_count": int(len(outliers)),
        "outliers": outliers[
            ["user_id", "campaign_id", "campaign_window", "subsidy_amount"]
        ].fillna("NaN").to_dict(orient="records"),
        "missing_subsidy_count": int(rewards["subsidy_amount"].isna().sum()),
    }

    # 7. time_window_alignment — check orders within campaign window per user
    exp_win = campaign_exposure[["user_id", "campaign_window"]].drop_duplicates()
    merged = orders.merge(exp_win, on="user_id", how="left")
    mismatches = []
    for _, row in merged.iterrows():
        if pd.isna(row.get("campaign_window")):
            continue
        try:
            win_start, win_end = parse_window(row["campaign_window"])
        except Exception:
            continue
        ot = pd.to_datetime(row["order_time"])
        if ot < win_start or ot > win_end:
            mismatches.append({
                "user_id": row["user_id"],
                "order_id": row["order_id"],
                "order_time": row["order_time"],
                "campaign_window": row["campaign_window"],
                "mismatch_reason": "order_outside_campaign_window",
            })

    time_window_alignment = {
        "total_orders": int(len(orders)),
        "matched_orders": int(len(orders) - len(mismatches)),
        "mismatch_count": int(len(mismatches)),
        "mismatches": mismatches,
    }

    # 8. warnings
    warnings = []
    if group_distribution["imbalanced"]:
        warnings.append({
            "risk_tag": "TREATMENT_CONTROL_IMBALANCE",
            "detail": f"对照组/实验组比例 {group_distribution['minority_to_majority_ratio']}，低于阈值 0.5，样本构造存在显著不平衡",
        })
    if n_imbalanced > 0:
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "detail": f"有 {n_imbalanced} 个协变量在组间存在不平衡（SMD > 0.1），可能影响效果评估",
        })
    if outlier_summary["outlier_count"] > 0:
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "detail": f"补贴金额存在 {outlier_summary['outlier_count']} 个极端异常值（IQR 规则），最高达 {outlier_summary['outliers'][0]['subsidy_amount'] if outlier_summary['outliers'] else 'N/A'}，需排查数据采集或策略异常",
        })
    if time_window_alignment["mismatch_count"] > 0:
        warnings.append({
            "risk_tag": "ORDER_TIME_WINDOW_MISMATCH",
            "detail": f"有 {time_window_alignment['mismatch_count']} 笔订单不在用户所属活动窗口内，可能是窗口期定义偏差或数据归属错误",
        })
    missing_act = int(campaign_exposure["activity_type"].isna().sum())
    if missing_act > 0:
        warnings.append({
            "risk_tag": "MISSING_ACTIVITY_TYPE",
            "detail": f"campaign_exposure 中 activity_type 有 {missing_act} 条缺失",
        })
    missing_city = int(users["city_id"].isna().sum())
    if missing_city > 0:
        warnings.append({
            "risk_tag": "MISSING_CITY_ID",
            "detail": f"users 中 city_id 有 {missing_city} 条缺失",
        })
    missing_subsidy = outlier_summary["missing_subsidy_count"]
    if missing_subsidy > 0:
        warnings.append({
            "risk_tag": "MISSING_SUBSIDY_AMOUNT",
            "detail": f"rewards 中 subsidy_amount 有 {missing_subsidy} 条缺失",
        })

    # 9. how_to_do_differently
    how_to_do_differently = (
        "本次审计基于 4 张 CSV 表完成了多维度数据质量检查。改进方向："
        "（1）在样本构造阶段增加分层抽样约束，确保 treatment/control 比例不低于 1:2；"
        "（2）对协变量做 PSM（倾向性得分匹配）或 CUPED 校正，缓解组间不平衡带来的评估偏差；"
        "（3）补贴金额应设置合理上限（如均值±3σ），避免单条极端值拉偏整体指标；"
        "（4）订单归属窗口需建立严格的 UTC 时间校验机制，防止跨窗口订单被错误归因；"
        "（5）缺失数据（activity_type、city_id、subsidy_amount）需要在上游 ETL 中补全或设置默认值兜底。"
    )

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

    out_path = os.path.join(SCRIPT_DIR, "answer.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)

    print(f"answer.json written to {out_path}")
    print(f"Keys: {list(answer.keys())}")


if __name__ == "__main__":
    main()
