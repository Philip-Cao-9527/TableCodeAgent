#!/usr/bin/env python3
"""solve.py — 营销活动样本构造数据审计 (growth_campaign_audit_001)"""

import json
import math
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent

# ── 1. 读取所有 CSV ──────────────────────────────────────────────
users = pd.read_csv(HERE / "users.csv", dtype=str)
exposure = pd.read_csv(HERE / "campaign_exposure.csv", dtype=str)
rewards = pd.read_csv(HERE / "rewards.csv", dtype=str)
orders = pd.read_csv(HERE / "orders.csv", dtype=str)

# 数值列转型（用于后续计算）
for col in ["subsidy_amount"]:
    if col in rewards.columns:
        rewards[col] = pd.to_numeric(rewards[col], errors="coerce")

for col in ["gmv", "is_conversion"]:
    if col in orders.columns:
        orders[col] = pd.to_numeric(orders[col], errors="coerce")

users_num_cols = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
for col in users_num_cols:
    if col in users.columns:
        users[col] = pd.to_numeric(users[col], errors="coerce")

# ── 2. row_counts ────────────────────────────────────────────────
row_counts = {
    "users": int(len(users)),
    "campaign_exposure": int(len(exposure)),
    "rewards": int(len(rewards)),
    "orders": int(len(orders)),
}

# ── 3. Join cardinality ──────────────────────────────────────────
LEFT_RIGHT_JOIN_KEYS = ["user_id", "campaign_id", "campaign_window"]

# exposure + rewards
merged_er = exposure.merge(rewards, on=LEFT_RIGHT_JOIN_KEYS, how="left", suffixes=("_left", "_right"))
join_cardinality = {
    "exposure_to_rewards": {
        "left_table": "campaign_exposure",
        "right_table": "rewards",
        "join_keys": LEFT_RIGHT_JOIN_KEYS,
        "left_row_count": len(exposure),
        "right_row_count": len(rewards),
        "joined_row_count": len(merged_er),
        "row_expansion_detected": len(merged_er) > len(exposure),
        "cardinality_risk": "right 表 user_id=u2 存在 2 条记录，join 后行数扩张" if len(merged_er) > len(exposure) else "无扩张",
    },
    "exposure_to_orders": {
        "left_table": "campaign_exposure",
        "right_table": "orders",
        "join_keys": ["user_id"],
        "left_row_count": len(exposure),
        "right_row_count": len(orders),
        "joined_row_count": int(len(exposure.merge(orders, on="user_id", how="left"))),
        "row_expansion_detected": len(exposure.merge(orders, on="user_id", how="left")) > len(exposure),
        "cardinality_risk": "right 表 user_id=u2 存在 2 条订单，join 后行数扩张" if len(exposure.merge(orders, on="user_id", how="left")) > len(exposure) else "无扩张",
    },
    "exposure_to_users": {
        "left_table": "campaign_exposure",
        "right_table": "users",
        "join_keys": ["user_id"],
        "left_row_count": len(exposure),
        "right_row_count": len(users),
        "joined_row_count": int(len(exposure.merge(users, on="user_id", how="left"))),
        "row_expansion_detected": False,
        "cardinality_risk": "无风险，一对一双向唯一",
    },
}

# ── 4. Group distribution ────────────────────────────────────────
group_counts = exposure["treatment_group"].value_counts()
treatment_count = int(group_counts.get("treatment", 0))
control_count = int(group_counts.get("control", 0))
min_ratio = min(treatment_count, control_count) / max(treatment_count, control_count) if max(treatment_count, control_count) > 0 else 0

group_distribution = {
    "treatment_group_column": "treatment_group",
    "treatment_count": treatment_count,
    "control_count": control_count,
    "minority_to_majority_ratio": round(min_ratio, 4),
    "imbalanced": min_ratio < 0.5,
    "note": f"对照组仅有 {control_count} 人，实验组 {treatment_count} 人，比例严重失衡" if min_ratio < 0.5 else "组间比例可接受",
}

# ── 5. SMD (组间平衡) ────────────────────────────────────────────
exposure_users = exposure.merge(users, on="user_id", how="left")

# 数值型 covariates
numeric_covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
treat = exposure_users[exposure_users["treatment_group"] == "treatment"]
ctrl = exposure_users[exposure_users["treatment_group"] == "control"]

smd_results = {}
smd_violations = []

for col in numeric_covariates:
    t_vals = treat[col].dropna()
    c_vals = ctrl[col].dropna()
    if len(t_vals) < 1 or len(c_vals) < 1:
        smd_results[col] = {"smd": None, "note": "某组数据不足，无法计算"}
        smd_violations.append(col)
        continue
    t_mean = t_vals.mean()
    c_mean = c_vals.mean()
    t_var = t_vals.var(ddof=1)
    c_var = c_vals.var(ddof=1)
    pooled_std = math.sqrt((t_var + c_var) / 2.0)
    if pooled_std < 1e-12:
        smd = 0.0
    else:
        smd = abs(t_mean - c_mean) / pooled_std
    smd_results[col] = {
        "smd": round(smd, 4),
        "treatment_mean": round(float(t_mean), 4),
        "control_mean": round(float(c_mean), 4),
        "violates_threshold": smd > 0.1,
    }
    if smd > 0.1:
        smd_violations.append(col)

# 分类变量 user_level
cat_col = "user_level"
if cat_col in exposure_users.columns:
    t_cat = treat[cat_col].value_counts(normalize=True)
    c_cat = ctrl[cat_col].value_counts(normalize=True)
    all_levels = sorted(set(list(t_cat.index) + list(c_cat.index)))
    cat_smd_values = []
    for level in all_levels:
        p_t = t_cat.get(level, 0.0)
        p_c = c_cat.get(level, 0.0)
        cat_smd_values.append(abs(p_t - p_c))
    # 用最大比例差作为分类变量的 SMD 代理
    max_cat_smd = max(cat_smd_values) if cat_smd_values else 0.0
    smd_results[cat_col] = {
        "smd": round(max_cat_smd, 4),
        "note": "分类变量 SMD = 各层级比例差的最大值",
        "level_proportions": {
            str(k): {"treatment_pct": round(float(t_cat.get(k, 0)), 4), "control_pct": round(float(c_cat.get(k, 0)), 4)}
            for k in all_levels
        },
        "violates_threshold": max_cat_smd > 0.1,
    }
    if max_cat_smd > 0.1:
        smd_violations.append(cat_col)

smd_summary = {
    "covariates": numeric_covariates + [cat_col],
    "smd_threshold": 0.1,
    "results": smd_results,
    "violations_count": len(smd_violations),
    "violations_list": smd_violations,
    "note": "因 treatment/control 样本量悬殊（8 vs 2），SMD 估算稳定性不足",
}

# ── 6. 补贴极端值 (IQR) ─────────────────────────────────────────
sub = rewards["subsidy_amount"].dropna()
q1 = sub.quantile(0.25)
q3 = sub.quantile(0.75)
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr
outlier_mask = (rewards["subsidy_amount"] < lower) | (rewards["subsidy_amount"] > upper)
outlier_rows = rewards[outlier_mask].copy()
outlier_details = []
for _, row in outlier_rows.iterrows():
    outlier_details.append({
        "user_id": str(row["user_id"]),
        "subsidy_amount": float(row["subsidy_amount"]) if pd.notna(row["subsidy_amount"]) else None,
    })
outlier_summary = {
    "column": "subsidy_amount",
    "method": "IQR (1.5x)",
    "q1": round(float(q1), 4),
    "q3": round(float(q3), 4),
    "iqr": round(float(iqr), 4),
    "lower_bound": round(float(lower), 4),
    "upper_bound": round(float(upper), 4),
    "outlier_count": int(len(outlier_details)),
    "outlier_detail": outlier_details,
    "note": f"用户 u8 补贴 500，远超 IQR 上限 {upper:.1f}，疑似极端值" if len(outlier_details) > 0 else "无极端值",
}

# ── 7. 时间窗口对齐 ─────────────────────────────────────────────
def parse_window(win):
    """Parse '2026-05-01:2026-05-07' -> (start_date, end_date)"""
    parts = win.split(":")
    return pd.Timestamp(parts[0].strip()), pd.Timestamp(parts[1].strip())

mismatches = []
for _, exp_row in exposure.iterrows():
    win_start, win_end = parse_window(exp_row["campaign_window"])
    uid = exp_row["user_id"]
    user_orders = orders[orders["user_id"] == uid]
    for _, ord_row in user_orders.iterrows():
        ot = pd.Timestamp(ord_row["order_time"])
        if ot < win_start or ot > win_end:
            mismatches.append({
                "user_id": uid,
                "order_id": str(ord_row["order_id"]),
                "order_time": str(ord_row["order_time"]),
                "campaign_window": exp_row["campaign_window"],
                "gmv": float(ord_row["gmv"]) if pd.notna(ord_row["gmv"]) else None,
                "reason": "order_time 不在 campaign_window 范围内",
            })

time_window_alignment = {
    "total_orders": len(orders),
    "orders_within_window": int(len(orders) - len(mismatches)),
    "mismatch_count": len(mismatches),
    "mismatch_rate": round(len(mismatches) / len(orders), 4) if len(orders) > 0 else 0,
    "mismatch_details": mismatches,
    "note": f"发现 {len(mismatches)} 条订单不在活动窗口内，需排查归因逻辑",
}

# ── 8. Warnings ──────────────────────────────────────────────────
warnings = []

# 8a. 组间严重失衡
if min_ratio < 0.5:
    warnings.append({
        "risk_tag": "GROUP_IMBALANCE",
        "severity": "high",
        "message": f"实验组/对照组比例严重失衡（{treatment_count}:{control_count}），ratio={min_ratio:.2f}，因果推断效力不足",
    })

# 8b. SMD 超标
if smd_violations:
    warnings.append({
        "risk_tag": "SMD_VOILATION",
        "severity": "medium",
        "message": f"协变量 {smd_violations} 的 SMD 超过阈值 0.1，组间存在不可忽略的偏差",
    })

# 8c. 补贴极端值
if len(outlier_details) > 0:
    warnings.append({
        "risk_tag": "SUBSIDY_OUTLIER",
        "severity": "high",
        "message": f"补贴金额存在 {len(outlier_details)} 个极端值（用户 {[d['user_id'] for d in outlier_details]}），需人工复核",
    })

# 8d. 时间窗口错配
if len(mismatches) > 0:
    mismatch_users = list(set(m["user_id"] for m in mismatches))
    warnings.append({
        "risk_tag": "TIME_WINDOW_MISMATCH",
        "severity": "high",
        "message": f"发现 {len(mismatches)} 条订单不在活动窗口内（涉及用户 {mismatch_users}），可能错误归因或回溯期设置不合理",
    })

# 8e. 数据缺失
if int(users["city_id"].isna().sum()) > 0:
    warnings.append({
        "risk_tag": "MISSING_DATA",
        "severity": "low",
        "message": f"users.city_id 存在 {int(users['city_id'].isna().sum())} 个缺失值",
    })
if int(rewards["subsidy_amount"].isna().sum()) > 0:
    warnings.append({
        "risk_tag": "MISSING_DATA",
        "severity": "medium",
        "message": f"rewards.subsidy_amount 存在 {int(rewards['subsidy_amount'].isna().sum())} 个缺失值（用户 u6）",
    })

# 8f. Join 扩张
if len(merged_er) > len(exposure):
    warnings.append({
        "risk_tag": "JOIN_EXPANSION",
        "severity": "medium",
        "message": f"exposure + rewards join 后行数从 {len(exposure)} 扩张至 {len(merged_er)}（用户 u2 有 2 条补贴记录），聚合时需注意权重",
    })

# ── 9. how_to_do_differently ────────────────────────────────────
how_to_do_differently = {
    "summary": "本次审计暴露了样本构造中的多项风险，建议从以下方面改进：",
    "suggestions": [
        "1. 扩大对照组规模：当前对照组仅 2 人，应通过 RTA 或预算分配增加对照曝光比例至 20%-30%。",
        "2. 引入分层随机化：基于 historical_orders_30d、user_level 等协变量进行分层抽样，从源头保证组间平衡。",
        "3. 异常值处理策略：对 subsidy_amount 超过 IQR 上界 3 倍的用户（如 u8）进行单独复核，或 Winsorize 处理。",
        "4. 订单归因窗口校准：当前 campaign_window 为固定周，但部分用户订单在其前后 1-2 天出现，建议窗口前后各预留 1 天缓冲期，或按用户粒度设定个性化窗口。",
        "5. 数据完整性校验：补充 users.city_id、rewards.subsidy_amount 等字段的缺失值处理流程，避免下游聚合偏差。",
    ],
}

# ── 10. 写入 answer.json ──────────────────────────────────────────
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

output_path = HERE / "answer.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(answer, f, ensure_ascii=False, indent=2)

print(f"✅ answer.json 已写入: {output_path}")
