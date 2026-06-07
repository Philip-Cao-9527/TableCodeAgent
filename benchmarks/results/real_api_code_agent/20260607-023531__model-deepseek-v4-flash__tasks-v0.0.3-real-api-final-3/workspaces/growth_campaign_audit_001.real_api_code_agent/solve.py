#!/usr/bin/env python3
"""
growth_campaign_audit_001 solve.py
营销活动样本构造数据审计：多表 join、treatment/control 分布、组间平衡、补贴极端值、订单时间窗口错配。
"""

import json
import math
import os
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

BASE = Path(__file__).resolve().parent


def load():
    users = pd.read_csv(BASE / "users.csv")
    exposure = pd.read_csv(BASE / "campaign_exposure.csv")
    rewards = pd.read_csv(BASE / "rewards.csv")
    orders = pd.read_csv(BASE / "orders.csv")
    return users, exposure, rewards, orders


def compute_smd(series_treat, series_ctrl, numeric=True):
    """标准化均值差异 (SMD)"""
    if numeric:
        m1, m2 = series_treat.mean(), series_ctrl.mean()
        s1, s2 = series_treat.std(ddof=1), series_ctrl.std(ddof=1)
        denom = math.sqrt((s1 ** 2 + s2 ** 2) / 2)
        if denom == 0:
            return 0.0
        return abs(m1 - m2) / denom
    else:
        # 分类变量：使用 Cramer's V-like 简化 — 计算不平衡比率
        t_counts = series_treat.value_counts()
        c_counts = series_ctrl.value_counts()
        all_cats = set(t_counts.index) | set(c_counts.index)
        max_diff = 0.0
        for cat in all_cats:
            t_rate = t_counts.get(cat, 0) / len(series_treat) if len(series_treat) > 0 else 0
            c_rate = c_counts.get(cat, 0) / len(series_ctrl) if len(series_ctrl) > 0 else 0
            max_diff = max(max_diff, abs(t_rate - c_rate))
        return max_diff


def main():
    users, exposure, rewards, orders = load()

    # ── 1. Row counts ──
    row_counts = {
        "users": int(len(users)),
        "campaign_exposure": int(len(exposure)),
        "rewards": int(len(rewards)),
        "orders": int(len(orders)),
    }

    # ── 2. Join cardinality (exposure → rewards 左连接) ──
    join_keys = ["user_id", "campaign_id", "campaign_window"]
    left = exposure.copy()
    right = rewards.copy()
    # 确保 key 列类型一致
    for c in join_keys:
        left[c] = left[c].astype(str)
        right[c] = right[c].astype(str)

    merged = left.merge(right, on=join_keys, how="left", suffixes=("_left", "_right"))
    joined_count = int(len(merged))
    left_count = int(len(left))
    right_dup_keys = not right.set_index(join_keys).index.is_unique
    row_expansion = joined_count > left_count

    join_cardinality = {
        "left_table": "campaign_exposure",
        "right_table": "rewards",
        "join_keys": join_keys,
        "left_row_count": left_count,
        "right_row_count": int(len(right)),
        "joined_row_count": joined_count,
        "row_expansion_detected": row_expansion,
        "right_has_duplicate_keys": right_dup_keys,
        "right_duplicate_key_example": "u2" if right_dup_keys else None,
    }

    # ── 3. Group distribution ──
    group_counts = exposure["treatment_group"].value_counts().to_dict()
    group_counts = {k: int(v) for k, v in group_counts.items()}
    treat = group_counts.get("treatment", 0)
    ctrl = group_counts.get("control", 0)
    ratio = ctrl / treat if treat > 0 else 0
    imbalanced = ratio < 0.5

    group_distribution = {
        "column": "treatment_group",
        "counts": group_counts,
        "treatment_count": treat,
        "control_count": ctrl,
        "control_to_treatment_ratio": round(ratio, 4),
        "imbalanced": imbalanced,
    }

    # ── 4. SMD summary (exposure + users 拼接后计算) ──
    exposure_u = exposure.merge(users, on="user_id", how="left")
    treat_df = exposure_u[exposure_u["treatment_group"] == "treatment"]
    ctrl_df = exposure_u[exposure_u["treatment_group"] == "control"]

    numeric_covs = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    cat_covs = ["user_level"]

    smd_details = {}
    for col in numeric_covs:
        if col in treat_df and col in ctrl_df:
            s = compute_smd(
                pd.to_numeric(treat_df[col], errors="coerce").dropna(),
                pd.to_numeric(ctrl_df[col], errors="coerce").dropna(),
                numeric=True,
            )
            smd_details[col] = {"type": "numeric", "smd": round(s, 6), "exceeds_threshold": s > 0.1}
        else:
            smd_details[col] = {"type": "numeric", "smd": None, "note": "column_not_found"}

    for col in cat_covs:
        if col in treat_df and col in ctrl_df:
            s = compute_smd(
                treat_df[col].dropna(),
                ctrl_df[col].dropna(),
                numeric=False,
            )
            smd_details[col] = {"type": "categorical", "smd": round(s, 6), "exceeds_threshold": s > 0.1}
        else:
            smd_details[col] = {"type": "categorical", "smd": None, "note": "column_not_found"}

    smd_summary = {
        "smd_threshold": 0.1,
        "by_column": smd_details,
        "any_threshold_exceeded": any(
            v.get("exceeds_threshold", False) for v in smd_details.values()
        ),
    }

    # ── 5. Outlier summary (subsidy_amount IQR) ──
    subsidy = pd.to_numeric(rewards["subsidy_amount"], errors="coerce")
    q1 = subsidy.quantile(0.25)
    q3 = subsidy.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = rewards[subsidy.notna() & ((subsidy < lower) | (subsidy > upper))]

    outlier_summary = {
        "column": "subsidy_amount",
        "method": "iqr",
        "iqr_multiplier": 1.5,
        "q1": round(q1, 2),
        "q3": round(q3, 2),
        "iqr": round(iqr, 2),
        "lower_bound": round(lower, 2),
        "upper_bound": round(upper, 2),
        "outlier_count": int(len(outliers)),
        "outlier_user_ids": outliers["user_id"].tolist() if len(outliers) > 0 else [],
    }

    # ── 6. Time window alignment ──
    # Parse campaign_window from exposure and check each user's orders
    combined = exposure[["user_id", "campaign_window"]].drop_duplicates()
    # Parse window start/end
    def parse_window(w):
        parts = str(w).split(":")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return None, None

    combined[["window_start", "window_end"]] = combined["campaign_window"].apply(
        lambda w: pd.Series(parse_window(w))
    )
    combined["window_start"] = pd.to_datetime(combined["window_start"], errors="coerce")
    combined["window_end"] = pd.to_datetime(combined["window_end"], errors="coerce")

    orders_t = orders.copy()
    orders_t["order_time_dt"] = pd.to_datetime(orders_t["order_time"], errors="coerce")

    aligned = orders_t.merge(combined, on="user_id", how="left")
    aligned["aligned"] = aligned.apply(
        lambda r: (
            pd.isna(r["window_start"])
            or (r["window_start"] <= r["order_time_dt"] <= r["window_end"])
        ),
        axis=1,
    )
    mismatches = aligned[~aligned["aligned"]].copy()
    mismatch_list = []
    for _, r in mismatches.iterrows():
        mismatch_list.append({
            "user_id": r["user_id"],
            "order_id": r["order_id"],
            "order_time": str(r["order_time"]),
            "campaign_window": r["campaign_window"],
            "window_start": str(r["window_start"].date()) if pd.notna(r.get("window_start")) else None,
            "window_end": str(r["window_end"].date()) if pd.notna(r.get("window_end")) else None,
            "mismatch_reason": "order_outside_campaign_window",
        })

    time_window_alignment = {
        "total_orders_checked": int(len(aligned)),
        "mismatch_count": int(len(mismatch_list)),
        "mismatch_details": mismatch_list,
    }

    # ── 7. Warnings ──
    warnings_list = []
    # a) Treatment/control imbalance
    if imbalanced:
        warnings_list.append({
            "risk_tag": "GROUP_IMBALANCE",
            "severity": "HIGH",
            "message": f"对照组/实验组比率 {ratio:.2f} 低于阈值 0.5，实验组({treat})与对照组({ctrl})样本量严重不均，影响 A/B 检验统计功效。建议增加对照组样本或进行分层抽样。",
        })
    # b) SMD threshold exceeded
    exceeded_covs = [k for k, v in smd_details.items() if v.get("exceeds_threshold")]
    if exceeded_covs:
        warnings_list.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "severity": "HIGH",
            "message": f"协变量 {exceeded_covs} 在 treatment/control 组间 SMD 超过 0.1 阈值，表明随机化不充分或样本选择存在系统性偏差。建议使用 PS matching 或 CUPED 校正。",
        })
    # c) Join expansion
    if row_expansion:
        warnings_list.append({
            "risk_tag": "JOIN_EXPANSION",
            "severity": "MEDIUM",
            "message": f"左连接后行数从 {left_count} 膨胀至 {joined_count}，rewards 表中存在重复键(u2)，可能导致聚合指标重复计算。建议去重或明确聚合粒度。",
        })
    # d) Outliers
    if outlier_summary["outlier_count"] > 0:
        warnings_list.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "severity": "MEDIUM",
            "message": f"补贴金额存在 {outlier_summary['outlier_count']} 个 IQR 离群值，用户 {outlier_summary['outlier_user_ids']} 补贴金额异常偏高(u8: 500)。建议核实是否存在发放异常或风控事件。",
        })
    # e) Time window mismatch
    if len(mismatch_list) > 0:
        mismatched_users = list(set(m["user_id"] for m in mismatch_list))
        warnings_list.append({
            "risk_tag": "TIME_WINDOW_MISMATCH",
            "severity": "HIGH",
            "message": f"发现 {len(mismatch_list)} 笔订单不在用户的活动窗口期内，涉及用户 {mismatched_users}。可能原因：订单归属活动周期错误、活动窗口定义不准确或数据 ETL 延迟。",
        })
    # f) Missing values
    missing_details = {}
    for name, df in [("users", users), ("campaign_exposure", exposure), ("rewards", rewards), ("orders", orders)]:
        miss = df.isna().sum()
        miss = miss[miss > 0]
        if not miss.empty:
            missing_details[name] = {col: int(v) for col, v in miss.items()}
    if missing_details:
        warnings_list.append({
            "risk_tag": "MISSING_VALUES",
            "severity": "LOW",
            "message": f"部分表存在缺失值：{json.dumps(missing_details, ensure_ascii=False)}。建议根据业务逻辑进行填充或剔除。",
        })

    # ── 8. How to do differently ──
    how_to_do_differently = (
        "1. 随机化分层：在分配 treatment/control 前, 根据 user_level 和 historical_gmv_30d 进行分层采样, 确保组间协变量均衡。"
        "2. 键值约束：在 rewards 表增加唯一键约束 (user_id, campaign_id, campaign_window, activity_type), 从源头防止重复。"
        "3. 补贴风控：设置补贴金额上限(如 IQR 上界的 3 倍), 超出后自动触发审批或阻断。"
        "4. 时间窗口校验：订单写入时增加 campaign_window 范围约束 (check 约束或应用层校验), 避免窗口外订单落入归因统计。"
        "5. 审计自动化：将上述检查封装为 CI/CD pipeline 中的数据质量 gate, 每次活动样本导出后自动运行审计报告。"
    )

    # ── Assemble answer ──
    answer = {
        "row_counts": row_counts,
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings_list,
        "how_to_do_differently": how_to_do_differently,
    }

    # Write answer.json
    out_path = BASE / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)
    print(f"✅ answer.json written to {out_path}")


if __name__ == "__main__":
    main()
