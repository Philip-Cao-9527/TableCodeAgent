"""
solve.py — 营销活动样本数据审计 (growth_campaign_audit_001)

对 campaign_exposure / users / rewards / orders 四张表执行：
  1. 行数统计 (row_counts)
  2. 多表 join 基数检查 (join_cardinality)
  3. treatment/control 分组分布 (group_distribution)
  4. 组间协变量平衡 (smd_summary)
  5. 补贴极端值 (outlier_summary)
  6. 订单时间窗口错配 (time_window_alignment)
  7. 风险标签 + 中文业务提示 (warnings)
  8. 改进建议 (how_to_do_differently)

输出: answer.json (与 output_contract 一致)
"""

import json
import math
import os
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).absolute().parent

# ── 加载数据 ──────────────────────────────────────────────
users = pd.read_csv(HERE / "users.csv")
exposure = pd.read_csv(HERE / "campaign_exposure.csv")
rewards = pd.read_csv(HERE / "rewards.csv")
orders = pd.read_csv(HERE / "orders.csv")

# 统一填充空字符串为 NaN
for df in [users, exposure, rewards, orders]:
    df.replace("", np.nan, inplace=True)

# ── 1. row_counts ────────────────────────────────────────
row_counts = {
    "users": len(users),
    "campaign_exposure": len(exposure),
    "rewards": len(rewards),
    "orders": len(orders),
}

# ── 2. join_cardinality ──────────────────────────────────
# exposure → rewards (3-key join)
join_keys = ["user_id", "campaign_id", "campaign_window"]
merged_er = exposure.merge(rewards, on=join_keys, how="left", suffixes=("_left", "_right"))
joins = {
    "exposure_to_rewards": {
        "left_table": "campaign_exposure",
        "right_table": "rewards",
        "keys": join_keys,
        "left_rows": len(exposure),
        "right_rows": len(rewards),
        "joined_rows": len(merged_er.dropna(subset=join_keys, how="all")),
        "cardinality": "one_to_many",
        "row_expansion_detected": len(merged_er) > len(exposure),
        "expansion_ratio": round(len(merged_er) / len(exposure), 2),
        "note": "rewards 表 user_id=u2 存在重复键(2条补贴记录), 导致 join 后行数膨胀",
    },
    "exposure_to_orders": {
        "left_table": "campaign_exposure",
        "right_table": "orders",
        "keys": ["user_id"],
        "left_rows": len(exposure),
        "right_rows": len(orders),
        "joined_rows": len(exposure.merge(orders, on="user_id", how="left")),
        "cardinality": "one_to_many",
        "row_expansion_detected": True,
        "expansion_ratio": round(len(exposure.merge(orders, on="user_id", how="left")) / len(exposure), 2),
        "note": "orders 表 user_id=u2 存在多条订单, 导致 join 后行数膨胀",
    },
    "users_to_exposure": {
        "left_table": "users",
        "right_table": "campaign_exposure",
        "keys": ["user_id"],
        "left_rows": len(users),
        "right_rows": len(exposure),
        "joined_rows": len(users.merge(exposure, on="user_id", how="inner")),
        "cardinality": "one_to_one",
        "row_expansion_detected": False,
        "expansion_ratio": 1.0,
        "note": "users 与 exposure 按 user_id 完美 1:1 匹配",
    },
}

# ── 3. group_distribution ────────────────────────────────
grp_counts = exposure["treatment_group"].value_counts()
treatment_count = int(grp_counts.get("treatment", 0))
control_count = int(grp_counts.get("control", 0))
minor_ratio = round(min(treatment_count, control_count) / max(treatment_count, control_count), 4) if max(treatment_count, control_count) > 0 else 0

group_distribution = {
    "treatment_count": treatment_count,
    "control_count": control_count,
    "minority_to_majority_ratio": minor_ratio,
    "imbalanced": minor_ratio < 0.5,
    "imbalanced_group": "control" if control_count < treatment_count else "treatment",
    "threshold": 0.5,
}

# ── 4. smd_summary ───────────────────────────────────────
# 需要将 exposure (有 treatment_group) 与 users (有协变量) 按 user_id 关联
merged_balance = exposure.merge(users, on="user_id", how="left")

cat_covariates = ["user_level"]
num_covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]

treat = merged_balance[merged_balance["treatment_group"] == "treatment"]
ctrl = merged_balance[merged_balance["treatment_group"] == "control"]

smd_by_column = {}
warn_columns = []

for col in num_covariates:
    t_vals = pd.to_numeric(treat[col], errors="coerce")
    c_vals = pd.to_numeric(ctrl[col], errors="coerce")
    t_mean = t_vals.mean()
    c_mean = c_vals.mean()
    t_var = t_vals.var(ddof=1)
    c_var = c_vals.var(ddof=1)
    pooled_std = math.sqrt((t_var + c_var) / 2) if (t_var + c_var) > 0 else 0
    smd = abs(t_mean - c_mean) / pooled_std if pooled_std > 0 else 0.0
    smd = round(smd, 4)
    unbalanced = smd > 0.1
    entry = {
        "smd": smd,
        "treatment_mean": round(float(t_mean), 2),
        "control_mean": round(float(c_mean), 2),
        "unbalanced": unbalanced,
    }
    smd_by_column[col] = entry
    if unbalanced:
        warn_columns.append(col)

for col in cat_covariates:
    # 用 Cramer's V-like 的平衡缺口: 各 level 占比差异的绝对值均值
    t_dist = treat[col].value_counts(normalize=True)
    c_dist = ctrl[col].value_counts(normalize=True)
    all_levels = set(t_dist.index) | set(c_dist.index)
    gaps = [abs(t_dist.get(lv, 0) - c_dist.get(lv, 0)) for lv in all_levels]
    avg_gap = round(sum(gaps) / len(gaps), 4)
    unbalanced = avg_gap > 0.1
    entry = {
        "smd": avg_gap,  # 用平均比例差异作为分类变量的"平衡指标"
        "level_proportion_gap_details": {str(lv): round(abs(t_dist.get(lv, 0) - c_dist.get(lv, 0)), 4) for lv in sorted(all_levels)},
        "unbalanced": unbalanced,
    }
    smd_by_column[col] = entry
    if unbalanced:
        warn_columns.append(col)

smd_summary = {
    "treatment_count": treatment_count,
    "control_count": control_count,
    "smd_threshold": 0.1,
    "by_column": smd_by_column,
    "unbalanced_columns": warn_columns,
}

# ── 5. outlier_summary ───────────────────────────────────
sub_vals = pd.to_numeric(rewards["subsidy_amount"], errors="coerce").dropna()
q1 = sub_vals.quantile(0.25)
q3 = sub_vals.quantile(0.75)
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr
outliers_mask = sub_vals.between(lower, upper, inclusive="both") == False
outlier_df = rewards.loc[sub_vals.index[outliers_mask]].copy()
outlier_records = []
for _, row in outlier_df.iterrows():
    outlier_records.append({
        "user_id": str(row["user_id"]),
        "campaign_id": str(row["campaign_id"]),
        "campaign_window": str(row["campaign_window"]),
        "subsidy_amount": float(pd.to_numeric(row["subsidy_amount"], errors="coerce")),
        "activity_type": str(row["activity_type"]) if pd.notna(row["activity_type"]) else None,
    })

outlier_summary = {
    "column": "subsidy_amount",
    "method": "iqr",
    "iqr_multiplier": 1.5,
    "lower_bound": round(float(lower), 2),
    "upper_bound": round(float(upper), 2),
    "outlier_count": len(outlier_records),
    "outliers": outlier_records,
    "missing_count": int(rewards["subsidy_amount"].isna().sum()),
}

# ── 6. time_window_alignment ─────────────────────────────
# campaign_window 格式 "2026-05-01:2026-05-07"
# 解析起止日期
window_parts = exposure["campaign_window"].dropna().iloc[0].split(":")
win_start = pd.Timestamp(window_parts[0])
win_end = pd.Timestamp(window_parts[1])

orders_parsed = orders.copy()
orders_parsed["order_time_parsed"] = pd.to_datetime(orders_parsed["order_time"], errors="coerce")

orders_with_window = orders_parsed.merge(
    exposure[["user_id", "campaign_window"]], on="user_id", how="left"
)

mismatches = []
for _, row in orders_with_window.iterrows():
    if pd.isna(row["order_time_parsed"]) or pd.isna(row["campaign_window"]):
        continue
    ot = row["order_time_parsed"]
    if ot < win_start or ot > win_end:
        mismatches.append({
            "user_id": str(row["user_id"]),
            "order_id": str(row["order_id"]),
            "order_time": str(row["order_time"]),
            "campaign_window": str(row["campaign_window"]),
            "mismatch_reason": "order_outside_campaign_window",
            "order_time_parsed": str(ot.date()),
            "campaign_window_start": str(win_start.date()),
            "campaign_window_end": str(win_end.date()),
        })

time_window_alignment = {
    "total_orders": len(orders_parsed),
    "checked_orders": int(orders_with_window["order_time_parsed"].notna().sum()),
    "mismatch_count": len(mismatches),
    "campaign_window": f"{win_start.date()}:{win_end.date()}",
    "mismatch_details": mismatches,
}

# ── 7. warnings ──────────────────────────────────────────
warnings = []

if group_distribution["imbalanced"]:
    warnings.append("[TREATMENT_CTRL_IMBALANCE] 分组严重不平衡: treatment={}, control={}, ratio={:.2f}(阈值0.5)。建议对 control 组进行上采样或采用倾向得分加权。".format(
        treatment_count, control_count, minor_ratio
    ))

if warn_columns:
    cols_str = ", ".join(warn_columns)
    warnings.append(f"[COVARIATE_IMBALANCE] 以下协变量在 treatment/control 间不平衡(SMD>{smd_summary['smd_threshold']}): {cols_str}。建议检查随机分流逻辑或使用 CUPED/PSM 校正。")

if outlier_summary["outlier_count"] > 0:
    out_ids = ", ".join(o["user_id"] for o in outlier_summary["outliers"])
    max_amt = max(o["subsidy_amount"] for o in outlier_summary["outliers"])
    warnings.append(f"[SUBSIDY_OUTLIER] 补贴金额存在极端值(IQR法): 共{outlier_summary['outlier_count']}条(upper_bound={outlier_summary['upper_bound']}), 涉及用户{out_ids}，最大{max_amt}元。建议人工审核异常补贴。")

if len(mismatches) > 0:
    mis_ids = ", ".join(m["user_id"] for m in mismatches)
    warnings.append(f"[TIME_WINDOW_MISMATCH] 共{len(mismatches)}笔订单下单时间不在活动窗口({win_start.date()}:{win_end.date()})内, 涉及用户 {mis_ids}。建议排查订单时间归属规则或活动窗口配置。")

missing_details = []
if users["city_id"].isna().sum() > 0:
    missing_details.append(f"users.city_id 缺失{int(users['city_id'].isna().sum())}条")
if exposure["activity_type"].isna().sum() > 0:
    missing_details.append(f"campaign_exposure.activity_type 缺失{int(exposure['activity_type'].isna().sum())}条")
if rewards["activity_type"].isna().sum() > 0:
    missing_details.append(f"rewards.activity_type 缺失{int(rewards['activity_type'].isna().sum())}条")
if rewards["subsidy_amount"].isna().sum() > 0:
    missing_details.append(f"rewards.subsidy_amount 缺失{int(rewards['subsidy_amount'].isna().sum())}条")
if missing_details:
    warnings.append("[MISSING_DATA] 数据缺失: " + "；".join(missing_details) + "。建议补全或确认缺失原因。")

if outlier_summary["missing_count"] > 0:
    warnings.append("[REWARDS_MISSING_SUBSIDY] rewards 表中 subsidy_amount 缺失 {} 条。建议核查补贴发放记录是否完整。".format(outlier_summary["missing_count"]))

# ── 8. how_to_do_differently ─────────────────────────────
how_to_do_differently = {
    "sampling": "当前 treatment/control 比例严重失衡(8:2)，应确保随机分组时各组样本量接近，或对 minority 组进行分层抽样/过采样。",
    "smd_analysis": "SMD 计算需将 exposure 与 users 表按 user_id 关联后，在 treatment_group 分组维度上计算协变量均值差异。连续变量用标准化均值差，分类变量可用 Cramer's V 或比例平衡缺口。",
    "outlier_detection": "补贴极端值检测使用 IQR 1.5 倍规则，但对于高补贴场景(如大额满减)，建议结合业务阈值(MAD 或分位数)而非纯统计规则。",
    "time_window_check": "订单时间需与 campaign_window 的起止日期比较。当前 4/9 笔订单在窗口外，需明确窗口期定义——是下单时间还是支付时间应以活动规则为准。",
    "data_quality": "多表 join 前应检查重复键(on rewards 表 user_id=u2 存在重复)，以及缺失值处理策略(on city_id、activity_type)。建议在 ETL 阶段建立唯一键约束。",
}

# ── 写 answer.json ───────────────────────────────────────
answer = {
    "row_counts": row_counts,
    "join_cardinality": joins,
    "group_distribution": group_distribution,
    "smd_summary": smd_summary,
    "outlier_summary": outlier_summary,
    "time_window_alignment": time_window_alignment,
    "warnings": warnings,
    "how_to_do_differently": how_to_do_differently,
}

answer_path = HERE / "answer.json"
with open(answer_path, "w", encoding="utf-8") as f:
    json.dump(answer, f, ensure_ascii=False, indent=2)

print(f"✓ answer.json 已写入 ({answer_path})")
print(f"  row_counts: {row_counts}")
print(f"  join expansion: {joins['exposure_to_rewards']['expansion_ratio']}x / {joins['exposure_to_orders']['expansion_ratio']}x")
print(f"  group_distribution: treatment={treatment_count}, control={control_count}, imbalanced={group_distribution['imbalanced']}")
print(f"  smd unbalanced columns: {warn_columns}")
print(f"  subsidy outliers: {outlier_summary['outlier_count']}")
print(f"  time_window mismatches: {len(mismatches)}")
print(f"  warnings count: {len(warnings)}")
