#!/usr/bin/env python3
"""growth_campaign_audit_001 — 营销活动样本构造数据审计 (pure Python / csv)"""

import csv
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_csv(filename):
    with open(HERE / filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


# ── 1. Load tables ──────────────────────────────────────────────────────────
users = load_csv("users.csv")
exposure = load_csv("campaign_exposure.csv")
rewards = load_csv("rewards.csv")
orders = load_csv("orders.csv")


# ── 2. Row counts ───────────────────────────────────────────────────────────
row_counts = {
    "users": len(users),
    "campaign_exposure": len(exposure),
    "rewards": len(rewards),
    "orders": len(orders),
}


# ── 3. Join cardinality (exposure LEFT JOIN rewards on user_id/campaign_id/campaign_window) ──
def make_key(row, keys):
    return tuple(row.get(k, "") for k in keys)

join_keys = ["user_id", "campaign_id", "campaign_window"]
rew_index = {}
for r in rewards:
    k = make_key(r, join_keys)
    rew_index.setdefault(k, []).append(r)

n_exp = len(exposure)
exp_rew_rows = []
rewards_matched_ids = set()
rewards_unmatched_ids = set()

for r in exposure:
    k = make_key(r, join_keys)
    matched = rew_index.get(k, [])
    if matched:
        for m in matched:
            exp_rew_rows.append({**r, **m})
            rewards_unmatched_ids.discard(id(m))
    else:
        exp_rew_rows.append(r)

# Find unmatched rewards
all_rew_ids = set(id(r) for r in rewards)
rewards_matched = all_rew_ids - set()
for r in rewards:
    k = make_key(r, join_keys)
    if k in rew_index and any(make_key(e, join_keys) == k for e in exposure):
        pass
    else:
        rewards_unmatched_ids.add(id(r))

rew_unmatched_count = len(rewards_unmatched_ids) if rewards_unmatched_ids else 0

# Count matched rewards
rew_matched_count = len(set(
    id(er) for er in exp_rew_rows
    if er.get("subsidy_amount") is not None and er["subsidy_amount"] != ""
))

join_cardinality = {
    "exposure_left_rows": n_exp,
    "exposure_after_left_join_rewards": len(exp_rew_rows),
    "rewards_matched_count": rew_matched_count,
    "rewards_total": len(rewards),
    "rewards_unmatched_count": rew_unmatched_count,
    "rewards_matched_pct": round(rew_matched_count / len(rewards) * 100, 2) if rewards else 0,
    "note": "左连接后行数不变（1:1 或 1:N 均摊平），rewards 中有 unmatched 记录需关注",
}


# ── 4. Treatment / control group distribution ───────────────────────────────
group_counter = Counter(r["treatment_group"] for r in exposure)
treatment_count = group_counter.get("treatment", 0)
control_count = group_counter.get("control", 0)
ratio = round(control_count / treatment_count, 4) if treatment_count else 0
imbalanced = ratio < 0.5

group_distribution = {
    "treatment_count": treatment_count,
    "control_count": control_count,
    "minority_to_majority_ratio": ratio,
    "imbalanced": imbalanced,
    "threshold": 0.5,
}


# ── 5. SMD on numeric covariates ────────────────────────────────────────────
user_map = {u["user_id"]: u for u in users}
covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]

treat_vals = {c: [] for c in covariates}
ctrl_vals = {c: [] for c in covariates}

for r in exposure:
    u = user_map.get(r["user_id"])
    if u is None:
        continue
    group = r["treatment_group"]
    for c in covariates:
        v = u.get(c, "")
        if v == "" or v is None:
            continue
        try:
            val = float(v)
        except (ValueError, TypeError):
            continue
        if group == "treatment":
            treat_vals[c].append(val)
        elif group == "control":
            ctrl_vals[c].append(val)

smd_details = {}
any_smd_above_threshold = False

for c in covariates:
    tv = treat_vals[c]
    cv = ctrl_vals[c]
    if len(tv) < 2 or len(cv) < 2:
        smd_details[c] = {"smd": None, "note": "样本量不足 2，无法计算"}
        continue
    t_mean = statistics.mean(tv)
    c_mean = statistics.mean(cv)
    t_var = statistics.variance(tv)
    c_var = statistics.variance(cv)
    pooled_std = math.sqrt((t_var + c_var) / 2)
    smd = abs(t_mean - c_mean) / pooled_std if pooled_std > 0 else 0.0
    smd = round(smd, 4)
    flagged = smd > 0.1
    if flagged:
        any_smd_above_threshold = True
    smd_details[c] = {
        "smd": smd,
        "treatment_mean": round(t_mean, 2),
        "control_mean": round(c_mean, 2),
        "flagged": flagged,
    }

# Categorical: user_level
level_treat = Counter()
level_ctrl = Counter()
for r in exposure:
    u = user_map.get(r["user_id"])
    if u is None:
        continue
    lv = u.get("user_level", "")
    if r["treatment_group"] == "treatment":
        level_treat[lv] += 1
    elif r["treatment_group"] == "control":
        level_ctrl[lv] += 1

treat_total = sum(level_treat.values())
ctrl_total = sum(level_ctrl.values())
all_levels = sorted(set(list(level_treat.keys()) + list(level_ctrl.keys())))
level_gaps = {}
for lv in all_levels:
    t_pct = level_treat.get(lv, 0) / treat_total if treat_total else 0
    c_pct = level_ctrl.get(lv, 0) / ctrl_total if ctrl_total else 0
    gap = round(abs(t_pct - c_pct), 4)
    level_gaps[lv] = gap
    if gap > 0.1:
        any_smd_above_threshold = True

smd_summary = {
    "numeric_smd": smd_details,
    "categorical_user_level_gap": level_gaps,
    "any_flagged": any_smd_above_threshold,
    "smd_threshold": 0.1,
}


# ── 6. Subsidy outliers (IQR 1.5x) ─────────────────────────────────────────
subsidy_vals = []
for r in rewards:
    v = r.get("subsidy_amount", "")
    if v == "" or v is None:
        continue
    try:
        subsidy_vals.append(float(v))
    except (ValueError, TypeError):
        continue

subsidy_vals.sort()
n_s = len(subsidy_vals)


def percentile(data, p):
    if not data:
        return 0
    idx = p / 100 * (len(data) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return data[lo]
    return data[lo] * (hi - idx) + data[hi] * (idx - lo)


Q1 = percentile(subsidy_vals, 25)
Q3 = percentile(subsidy_vals, 75)
IQR = Q3 - Q1
lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR

outlier_rows = []
for r in rewards:
    v = r.get("subsidy_amount", "")
    if v == "" or v is None:
        continue
    try:
        val = float(v)
        if val < lower or val > upper:
            outlier_rows.append(r)
    except (ValueError, TypeError):
        continue

outlier_summary = {
    "method": "iqr_1.5x",
    "q1": round(Q1, 2),
    "q3": round(Q3, 2),
    "lower_bound": round(lower, 2),
    "upper_bound": round(upper, 2),
    "outlier_count": len(outlier_rows),
    "outlier_rows": outlier_rows,
}


# ── 7. Time window alignment ───────────────────────────────────────────────
def parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# Build user->campaign_window map from exposure
user_window_map = {}
for r in exposure:
    uid = r["user_id"]
    cw = r.get("campaign_window", "")
    if ":" in cw:
        parts = cw.split(":")
        ws = parse_date(parts[0])
        we = parse_date(parts[1])
        if uid not in user_window_map:
            user_window_map[uid] = (ws, we)

out_of_window_orders = []
total_orders_checked = 0
in_window_count = 0

for r in orders:
    total_orders_checked += 1
    uid = r["user_id"]
    ot = parse_date(r.get("order_time", ""))
    win = user_window_map.get(uid)
    if ot is None or win is None:
        out_of_window_orders.append({
            "order_id": r.get("order_id"),
            "user_id": uid,
            "order_time": r.get("order_time"),
            "campaign_window": r.get("campaign_window") or "N/A",
            "reason": "无法解析日期或缺少窗口信息",
        })
        continue
    ws, we = win
    if ws is not None and we is not None and ws <= ot <= we:
        in_window_count += 1
    else:
        out_of_window_orders.append({
            "order_id": r.get("order_id"),
            "user_id": uid,
            "order_time": r.get("order_time"),
            "campaign_window": f"{ws.date()}:{we.date()}" if ws and we else "N/A",
        })

time_window_alignment = {
    "total_orders_checked": total_orders_checked,
    "in_window_count": in_window_count,
    "out_of_window_count": total_orders_checked - in_window_count,
    "out_of_window_orders": out_of_window_orders,
    "note": "out_of_window 订单可能出现在活动窗口开始之前或结束之后",
}


# ── 8. Warnings ─────────────────────────────────────────────────────────────
warnings_list = []
risk_tags = []

if imbalanced:
    warnings_list.append(
        f"Treatment/control 比例严重失衡：treatment={treatment_count}, control={control_count}, "
        f"比值={ratio}，低于阈值 0.5。建议重新采样或使用分层抽样。"
    )
    risk_tags.append("IMBALANCE_TREATMENT_CONTROL")

if any_smd_above_threshold:
    flagged_covs = [k for k, v in smd_details.items() if isinstance(v, dict) and v.get("flagged")]
    flagged_cat = [f"user_level({lv})" for lv, g in level_gaps.items() if g > 0.1]
    all_flagged = flagged_covs + flagged_cat
    warnings_list.append(
        f"SMD 超过阈值 0.1 的协变量：{', '.join(all_flagged)}。"
        "组间协变量不平衡可能影响因果推断的可信度。"
    )
    risk_tags.append("COVARIATE_IMBALANCE")

if outlier_rows:
    outlier_desc = "; ".join(
        f"user={r.get('user_id')}, amount={r.get('subsidy_amount')}" for r in outlier_rows
    )
    warnings_list.append(
        f"补贴金额存在 {len(outlier_rows)} 个极端值（IQR 1.5 倍距）：{outlier_desc}。"
        "建议核实数据来源，考虑截尾或缩尾处理。"
    )
    risk_tags.append("SUBSIDY_OUTLIER")

out_of_window_count = total_orders_checked - in_window_count
if out_of_window_count > 0:
    oow_orders_desc = "; ".join(
        f"order={r['order_id']}, user={r['user_id']}, time={r['order_time']}" for r in out_of_window_orders
    )
    warnings_list.append(
        f"发现 {out_of_window_count} 笔订单不在活动窗口内：{oow_orders_desc}。"
        "这类订单可能属于自然转化而非活动驱动，建议排除或标记。"
    )
    risk_tags.append("TIME_WINDOW_MISMATCH")

# Missing data
missing_checks = [
    ("users", "city_id", sum(1 for u in users if u.get("city_id", "").strip() == "")),
    ("campaign_exposure", "activity_type", sum(1 for r in exposure if r.get("activity_type", "").strip() == "")),
    ("rewards", "activity_type", sum(1 for r in rewards if r.get("activity_type", "").strip() == "")),
    ("rewards", "subsidy_amount", sum(1 for r in rewards if r.get("subsidy_amount", "").strip() == "")),
]
missing_flags = [f"{tbl}.{col} 缺失 {cnt} 条" for tbl, col, cnt in missing_checks if cnt > 0]
if missing_flags:
    warnings_list.append("存在缺失数据：" + "；".join(missing_flags) + "。建议评估缺失机制并考虑插补或剔除。")
    risk_tags.append("MISSING_DATA")

if not warnings_list:
    warnings_list.append("未发现明显的数据质量问题。")
    risk_tags.append("CLEAN")

warnings_output = [{"risk_tag": tag, "message": msg} for tag, msg in zip(risk_tags, warnings_list)]


# ── 9. How to do differently ────────────────────────────────────────────────
how_to_do_differently = [
    "使用分层随机抽样替代简单随机抽样以保障 treatment/control 组间协变量平衡",
    "对连续协变量进行 PS（倾向性得分）匹配或 IPTW 加权校正",
    "对补贴金额采用缩尾（winsorize）或分箱（bucketing）处理以减少极端值影响",
    "排除活动窗口外的订单或将窗口定义扩展至包含曝光后合理转化周期",
    "补全缺失数据（如 city_id 可用众数填充，activity_type 可按 campaign 维度推断）",
    "增加样本量以满足最小可检测效应量（MDE）要求",
    "添加 permutation test 验证组间差异显著性",
]


# ── 10. Assemble & write answer ─────────────────────────────────────────────
answer = {
    "row_counts": row_counts,
    "join_cardinality": join_cardinality,
    "group_distribution": group_distribution,
    "smd_summary": smd_summary,
    "outlier_summary": outlier_summary,
    "time_window_alignment": time_window_alignment,
    "warnings": warnings_output,
    "how_to_do_differently": how_to_do_differently,
}

with open(HERE / "answer.json", "w", encoding="utf-8") as f:
    json.dump(answer, f, ensure_ascii=False, indent=2)

print("✅ answer.json written successfully.")
print(f"   row_counts: {row_counts}")
print(f"   group_imbalanced: {imbalanced} (treatment={treatment_count}, control={control_count})")
print(f"   subsidy_outliers: {len(outlier_rows)}")
print(f"   time_window_mismatch: {out_of_window_count}")
