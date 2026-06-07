"""solve.py — 营销活动样本构造数据审计 (growth_campaign_audit_001)"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_csv(name: str) -> list[dict]:
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── 1. Row counts ──────────────────────────────────────────────────────────

def compute_row_counts(users, exposure, rewards, orders):
    return {
        "users": len(users),
        "campaign_exposure": len(exposure),
        "rewards": len(rewards),
        "orders": len(orders),
    }


# ── 2. Join cardinality check ─────────────────────────────────────────────

def compute_join_cardinality(exposure, rewards, orders):
    keys = ["user_id", "campaign_id", "campaign_window"]

    def _key_dupes(rows, name):
        seen = {}
        dupes = 0
        for r in rows:
            k = tuple(r.get(k, "") for k in keys)
            seen.setdefault(k, 0)
            seen[k] += 1
        dupes = sum(1 for v in seen.values() if v > 1)
        dup_rows = sum(v - 1 for v in seen.values() if v > 1)
        return {
            "table": name,
            "total_rows": len(rows),
            "unique_keys": len(seen),
            "duplicate_key_rows": dup_rows + dupes,
            "has_duplicates": dupes > 0,
        }

    exposure_info = _key_dupes(exposure, "campaign_exposure")
    rewards_info = _key_dupes(rewards, "rewards")
    orders_info = _key_dupes(orders, "orders")

    # Simulated join row counts
    # exposure -> rewards (left on keys)
    rew_idx = {}
    for i, r in enumerate(rewards):
        k = tuple(r.get(k, "") for k in keys)
        rew_idx.setdefault(k, []).append(r)

    join_er = 0
    for r in exposure:
        k = tuple(r.get(k, "") for k in keys)
        matches = rew_idx.get(k, [None])
        join_er += len(matches)

    return {
        "key_columns": keys,
        "exposure_key_check": exposure_info,
        "rewards_key_check": rewards_info,
        "orders_key_check": orders_info,
        "exposure_rewards_join_rows": join_er,
        "exposure_rewards_join_expansion_ratio": round(
            join_er / len(exposure), 4
        ),
    }


# ── 3. Group distribution ─────────────────────────────────────────────────

def compute_group_distribution(exposure):
    counts = Counter(r["treatment_group"] for r in exposure)
    treatment = counts.get("treatment", 0)
    control = counts.get("control", 0)
    total = treatment + control
    ratio = round(treatment / control, 4) if control > 0 else None
    return {
        "treatment": treatment,
        "control": control,
        "total_exposed": total,
        "treatment_control_ratio": ratio,
        "ratio_check": (
            "PASS" if ratio is not None and 0.5 <= ratio <= 2.0 else "WARN"
        ),
    }


# ── 4. SMD (group balance) ────────────────────────────────────────────────

def _smd_numeric(vals_t, vals_c):
    n_t, n_c = len(vals_t), len(vals_c)
    if n_t < 2 or n_c < 2:
        return None
    mean_t = sum(vals_t) / n_t
    mean_c = sum(vals_c) / n_c
    var_t = sum((x - mean_t) ** 2 for x in vals_t) / (n_t - 1)
    var_c = sum((x - mean_c) ** 2 for x in vals_c) / (n_c - 1)
    pooled = math.sqrt((var_t + var_c) / 2.0)
    if pooled == 0:
        return 0.0
    return round((mean_t - mean_c) / pooled, 6)


def _smd_categorical(vals_t, vals_c):
    t_dist = Counter(vals_t)
    c_dist = Counter(vals_c)
    n_t = len(vals_t)
    n_c = len(vals_c)
    all_cats = set(t_dist.keys()) | set(c_dist.keys())
    max_diff = 0.0
    for cat in all_cats:
        p_t = t_dist.get(cat, 0) / n_t if n_t else 0
        p_c = c_dist.get(cat, 0) / n_c if n_c else 0
        max_diff = max(max_diff, abs(p_t - p_c))
    return round(max_diff, 6)


def compute_smd_summary(users, exposure):
    user_map = {r["user_id"]: r for r in users}
    covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"]
    treat_vals = {c: [] for c in covariates}
    control_vals = {c: [] for c in covariates}

    for r in exposure:
        u = user_map.get(r["user_id"])
        if u is None:
            continue
        bucket = treat_vals if r["treatment_group"] == "treatment" else control_vals
        for c in covariates:
            v = u.get(c)
            if v is None or v == "":
                continue
            if c == "user_level":
                bucket[c].append(v)
            else:
                try:
                    bucket[c].append(float(v))
                except (ValueError, TypeError):
                    continue

    results = {}
    threshold = 0.1
    for c in covariates:
        t = treat_vals[c]
        ct = control_vals[c]
        if c == "user_level":
            smd = _smd_categorical(t, ct)
        else:
            smd = _smd_numeric(t, ct)
        results[c] = {
            "smd": smd,
            "imbalanced": smd is not None and abs(smd) > threshold,
        }

    vars_over = [k for k, v in results.items() if v.get("imbalanced")]
    return {
        "covariates": results,
        "smd_threshold": threshold,
        "vars_over_threshold": vars_over,
        "balance_verdict": "IMBALANCED" if vars_over else "BALANCED",
    }


# ── 5. Subsidy outlier (IQR) ──────────────────────────────────────────────

def compute_outlier_summary(rewards):
    amounts = []
    missing = 0
    for r in rewards:
        v = r.get("subsidy_amount", "")
        if v == "" or v is None:
            missing += 1
        else:
            try:
                amounts.append(float(v))
            except (ValueError, TypeError):
                missing += 1
    amounts.sort()
    n = len(amounts)
    if n == 0:
        return {
            "column": "subsidy_amount",
            "q1": None,
            "q3": None,
            "iqr": None,
            "lower_fence": None,
            "upper_fence": None,
            "outlier_count": 0,
            "outlier_values": [],
            "missing_count": missing,
        }

    def _percentile(sorted_vals, p):
        idx = p / 100.0 * (len(sorted_vals) - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return sorted_vals[lo]
        return sorted_vals[lo] + (idx - lo) * (sorted_vals[hi] - sorted_vals[lo])

    q1 = _percentile(amounts, 25)
    q3 = _percentile(amounts, 75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = [round(v, 2) for v in amounts if v < lower or v > upper]

    return {
        "column": "subsidy_amount",
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "lower_fence": round(lower, 4),
        "upper_fence": round(upper, 4),
        "outlier_count": len(outliers),
        "outlier_values": outliers,
        "missing_count": missing,
    }


# ── 6. Time window alignment ──────────────────────────────────────────────

def _parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def compute_time_window_alignment(orders, exposure):
    exp_by_user = {}
    for r in exposure:
        exp_by_user.setdefault(r["user_id"], []).append(r)

    aligned = 0
    misaligned = 0
    misaligned_details = []

    for o in orders:
        uid = o.get("user_id", "")
        exposures = exp_by_user.get(uid, [])
        if not exposures:
            continue
        order_dt = _parse_date(o.get("order_time", ""))
        if order_dt is None:
            continue
        # check if order_time falls in ANY campaign window for this user
        in_window = False
        for e in exposures:
            win = e.get("campaign_window", "")
            if ":" not in win:
                continue
            parts = win.split(":", 1)
            ws = _parse_date(parts[0])
            we = _parse_date(parts[1])
            if ws is None or we is None:
                continue
            if ws <= order_dt <= we:
                in_window = True
                break
        if in_window:
            aligned += 1
        else:
            misaligned += 1
            misaligned_details.append({
                "user_id": uid,
                "order_id": o.get("order_id", ""),
                "order_time": o.get("order_time", ""),
                "campaign_window": exposures[0].get("campaign_window", ""),
            })

    return {
        "total_orders_joined": len(orders),
        "aligned_count": aligned,
        "misaligned_count": misaligned,
        "misaligned_details": misaligned_details,
    }


# ── 7. Warnings ───────────────────────────────────────────────────────────

def _missing_cols(rows):
    if not rows:
        return []
    cols = rows[0].keys()
    return [c for c in cols if any(r.get(c, "") == "" for r in rows)]


def compute_warnings(users, exposure, rewards, orders,
                     join_cardinality, group_distribution,
                     smd_summary, outlier_summary,
                     time_window_alignment):
    warnings = []

    # Missing values
    for data, name in [(users, "users"), (exposure, "campaign_exposure"),
                       (rewards, "rewards"), (orders, "orders")]:
        cols = _missing_cols(data)
        if cols:
            warnings.append({
                "risk_tag": "MISSING_VALUES",
                "table": name,
                "columns": cols,
                "message": f"表 {name} 存在缺失值：{cols}",
            })

    # Duplicate keys
    for info_key, label in [("exposure_key_check", "campaign_exposure"),
                            ("rewards_key_check", "rewards"),
                            ("orders_key_check", "orders")]:
        info = join_cardinality.get(info_key, {})
        if info.get("has_duplicates"):
            warnings.append({
                "risk_tag": "DUPLICATE_KEYS",
                "table": label,
                "message": f"表 {label} 在 join keys 上存在重复行，可能导致 join 后行膨胀",
            })

    # Group imbalance
    if group_distribution.get("ratio_check") == "WARN":
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "table": "campaign_exposure",
            "message": "treatment/control 比例偏离 0.5~2.0 范围，可能影响 A/B 测试统计功效",
        })

    # Covariate imbalance
    if smd_summary.get("vars_over_threshold"):
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "variables": smd_summary["vars_over_threshold"],
            "message": f"以下协变量在组间不平衡（SMD > {smd_summary['smd_threshold']}）：{smd_summary['vars_over_threshold']}，建议使用 CUPED 或分层随机化调整",
        })

    # Subsidy outliers
    if outlier_summary["outlier_count"] > 0:
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIERS",
            "count": outlier_summary["outlier_count"],
            "values": outlier_summary["outlier_values"],
            "message": f"补贴金额发现 {outlier_summary['outlier_count']} 个极端值（IQR 法），最高值 {max(outlier_summary['outlier_values']) if outlier_summary['outlier_values'] else 'N/A'}，需排查异常发放或数据录入错误",
        })

    # Time window misalignment
    if time_window_alignment["misaligned_count"] > 0:
        warnings.append({
            "risk_tag": "TIME_WINDOW_MISALIGNMENT",
            "count": time_window_alignment["misaligned_count"],
            "details": time_window_alignment["misaligned_details"],
            "message": f"有 {time_window_alignment['misaligned_count']} 笔订单的订单时间不在 campaign_window 范围内，可能为窗口外自然转化或数据登记时间偏差",
        })

    return warnings


# ── 8. How to do differently ──────────────────────────────────────────────

def compute_how_to_do_differently(warnings):
    tags = {w["risk_tag"] for w in warnings}
    tips = []
    if "MISSING_VALUES" in tags:
        tips.append("数据采集阶段应加强必填字段校验，减少缺失值进入分析流程")
    if "DUPLICATE_KEYS" in tags:
        tips.append("对 exposure / rewards 表应在入库时按 join keys 去重，或在 ETL 阶段做 upsert 处理")
    if "GROUP_IMBALANCE" in tags:
        tips.append("改用分层抽样或倾向性评分匹配（PSM）重新构造 treatment/control 样本")
    if "COVARIATE_IMBALANCE" in tags:
        tips.append("采用 CUPED（方差缩减）或逆概率加权（IPW）在效果评估阶段校正组间差异")
    if "SUBSIDY_OUTLIERS" in tags:
        tips.append("补贴发放应设置金额上限风控规则，并对超出 fence 的记录进行人工复核")
    if "TIME_WINDOW_MISALIGNMENT" in tags:
        tips.append("订单归因逻辑应限定在 campaign_window 内，或对窗口外订单单独标记自然转化")
    if not tips:
        tips.append("当前数据质量良好，可维持现有样本构造流程")
    return tips


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    users = _load_csv("users.csv")
    exposure = _load_csv("campaign_exposure.csv")
    rewards = _load_csv("rewards.csv")
    orders = _load_csv("orders.csv")

    row_counts = compute_row_counts(users, exposure, rewards, orders)
    join_cardinality = compute_join_cardinality(exposure, rewards, orders)
    group_distribution = compute_group_distribution(exposure)
    smd_summary = compute_smd_summary(users, exposure)
    outlier_summary = compute_outlier_summary(rewards)
    time_window_alignment = compute_time_window_alignment(orders, exposure)
    warnings = compute_warnings(
        users, exposure, rewards, orders,
        join_cardinality, group_distribution, smd_summary,
        outlier_summary, time_window_alignment,
    )
    how_to_do_differently = compute_how_to_do_differently(warnings)

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

    (HERE / "answer.json").write_text(
        json.dumps(answer, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
