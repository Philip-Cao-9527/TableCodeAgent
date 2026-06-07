#!/usr/bin/env python3
"""solve.py — growth_campaign_audit_001 数据审计"""

import json
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent


def load_tables(base: Path) -> dict:
    """加载所有 CSV 表并标准化数值列"""
    users = pd.read_csv(base / "users.csv")
    campaign_exposure = pd.read_csv(base / "campaign_exposure.csv")
    orders = pd.read_csv(base / "orders.csv")
    rewards = pd.read_csv(base / "rewards.csv")

    # 数值列转 float（空字符串 → NaN）
    for col in ["subsidy_amount", "gmv"]:
        if col in rewards.columns:
            rewards[col] = pd.to_numeric(rewards[col], errors="coerce")
        if col in orders.columns:
            orders[col] = pd.to_numeric(orders[col], errors="coerce")

    for col in ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]:
        if col in users.columns:
            users[col] = pd.to_numeric(users[col], errors="coerce")

    # 解析 order_time 为 datetime
    if "order_time" in orders.columns:
        orders["order_time"] = pd.to_datetime(orders["order_time"], errors="coerce")

    # 解析 campaign_window → start / end
    def parse_window(w):
        try:
            parts = str(w).split(":")
            return pd.Timestamp(parts[0]), pd.Timestamp(parts[1])
        except Exception:
            return pd.NaT, pd.NaT

    if "campaign_window" in campaign_exposure.columns:
        win_parsed = campaign_exposure["campaign_window"].apply(parse_window)
        campaign_exposure["window_start"] = win_parsed.apply(lambda x: x[0])
        campaign_exposure["window_end"] = win_parsed.apply(lambda x: x[1])

    return {"users": users, "campaign_exposure": campaign_exposure,
            "orders": orders, "rewards": rewards}


def compute_row_counts(tables: dict) -> dict:
    return {name: int(len(df)) for name, df in tables.items()}


def compute_join_cardinality(tables: dict) -> dict:
    """检查关键表之间的 join 基数"""
    exp = tables["campaign_exposure"]
    orders = tables["orders"]
    rewards = tables["rewards"]

    result = {}

    # exposure → orders (left join 行膨胀)
    left_join = exp.merge(orders, on="user_id", how="left")
    result["exposure_left_join_orders"] = {
        "exposure_rows": len(exp),
        "orders_rows": len(orders),
        "left_join_rows": len(left_join),
        "null_after_join": int(left_join["order_id"].isna().sum()),
        "note": "部分曝光用户在 orders 中无匹配订单（如 u6、u7）"
    }

    # exposure → rewards
    left_join_rewards = exp.merge(rewards, on=["user_id", "campaign_id", "campaign_window"], how="left")
    result["exposure_left_join_rewards"] = {
        "exposure_rows": len(exp),
        "rewards_rows": len(rewards),
        "left_join_rows": len(left_join_rewards),
        "null_after_join": int(left_join_rewards["subsidy_amount"].isna().sum()),
        "note": "部分用户无 rewards 记录"
    }

    # duplicate check on exposure
    dup_cols = ["user_id", "campaign_window"]
    dups = exp[exp.duplicated(subset=dup_cols, keep=False)]
    result["exposure_duplicate_check"] = {
        "duplicate_key_columns": dup_cols,
        "duplicate_row_count": len(dups),
        "note": "无重复" if len(dups) == 0 else f"发现 {len(dups)} 行重复"
    }

    # rewards duplicate check
    dup_rewards = rewards[rewards.duplicated(subset=["user_id", "campaign_id", "campaign_window"], keep=False)]
    result["rewards_duplicate_check"] = {
        "duplicate_key_columns": ["user_id", "campaign_id", "campaign_window"],
        "duplicate_row_count": len(dup_rewards),
        "note": f"发现 {len(dup_rewards)} 行重复（u2 有两条补贴记录）" if len(dup_rewards) > 0 else "无重复"
    }

    return result


def compute_group_distribution(tables: dict) -> dict:
    exp = tables["campaign_exposure"]
    counts = exp["treatment_group"].value_counts().to_dict()
    counts = {str(k): int(v) for k, v in counts.items()}
    total = sum(counts.values())
    ratio = None
    if "treatment" in counts and "control" in counts and counts["control"] > 0:
        ratio = round(counts["treatment"] / counts["control"], 4)
    return {
        "counts": counts,
        "total": total,
        "treatment_control_ratio": ratio,
        "min_group_ratio_threshold": 0.5,
        "imbalanced": ratio is not None and (ratio < 0.5 or ratio > 2.0),
        "note": f"treatment={counts.get('treatment',0)}, control={counts.get('control',0)}, ratio={ratio}" if ratio else "仅有一个分组"
    }


def compute_smd_summary(tables: dict) -> dict:
    """计算 treatment/control 在连续协变量上的 SMD + 分类变量的 balance gap"""
    exp = tables["campaign_exposure"]
    users = tables["users"]

    # merge
    merged = exp.merge(users, on="user_id", how="left")

    treatment = merged[merged["treatment_group"] == "treatment"]
    control = merged[merged["treatment_group"] == "control"]

    numeric_covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    categorical_covariates = ["user_level"]

    smd_results = []

    # 数值型 SMD
    for col in numeric_covariates:
        t_vals = treatment[col].dropna()
        c_vals = control[col].dropna()
        if len(t_vals) < 2 or len(c_vals) < 2:
            smd_results.append({
                "covariate": col, "type": "numeric",
                "treatment_mean": None, "control_mean": None,
                "smd": None, "note": "样本不足"
            })
            continue
        t_mean = t_vals.mean()
        c_mean = c_vals.mean()
        t_var = t_vals.var(ddof=1)
        c_var = c_vals.var(ddof=1)
        pooled_std = np.sqrt((t_var + c_var) / 2)
        smd = abs(t_mean - c_mean) / pooled_std if pooled_std > 1e-8 else 0.0
        smd_results.append({
            "covariate": col, "type": "numeric",
            "treatment_mean": round(float(t_mean), 4),
            "control_mean": round(float(c_mean), 4),
            "smd": round(float(smd), 4),
            "imbalanced": smd > 0.1
        })

    # 分类变量 balance
    for col in categorical_covariates:
        t_dist = treatment[col].value_counts(normalize=True).to_dict()
        c_dist = control[col].value_counts(normalize=True).to_dict()
        all_levels = set(list(t_dist.keys()) + list(c_dist.keys()))
        max_gap = 0.0
        for lv in all_levels:
            gap = abs(t_dist.get(lv, 0.0) - c_dist.get(lv, 0.0))
            max_gap = max(max_gap, gap)
        smd_results.append({
            "covariate": col, "type": "categorical",
            "treatment_distribution": {str(k): round(float(v), 4) for k, v in t_dist.items()},
            "control_distribution": {str(k): round(float(v), 4) for k, v in c_dist.items()},
            "max_balance_gap": round(float(max_gap), 4),
            "imbalanced": max_gap > 0.1
        })

    return {
        "smd_threshold": 0.1,
        "covariates": numeric_covariates + categorical_covariates,
        "results": smd_results,
        "any_imbalanced": any(r.get("imbalanced", False) for r in smd_results)
    }


def compute_outlier_summary(tables: dict) -> dict:
    """IQR 法检测 subsidy_amount 极端值"""
    rewards = tables["rewards"]
    col = "subsidy_amount"
    vals = rewards[col].dropna()
    if len(vals) == 0:
        return {"column": col, "note": "无有效值", "outliers": []}

    q1 = vals.quantile(0.25)
    q3 = vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = rewards[(rewards[col] < lower) | (rewards[col] > upper)]
    outlier_list = []
    for _, row in outliers.iterrows():
        outlier_list.append({
            "user_id": row["user_id"],
            "subsidy_amount": float(row[col]),
            "lower_bound": round(float(lower), 2),
            "upper_bound": round(float(upper), 2)
        })

    return {
        "column": col,
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_bound": round(float(lower), 2),
        "upper_bound": round(float(upper), 2),
        "outlier_count": len(outlier_list),
        "outliers": outlier_list,
        "missing_count": int(rewards[col].isna().sum()),
        "note": f"发现 {len(outlier_list)} 个补贴极端值" if outlier_list else "无极端值"
    }


def compute_time_window_alignment(tables: dict) -> dict:
    """检查订单时间是否落在用户的 campaign_window 内"""
    exp = tables["campaign_exposure"]
    orders = tables["orders"]

    merged = exp.merge(orders, on="user_id", how="inner")
    misaligned = []

    for _, row in merged.iterrows():
        ot = row["order_time"]
        ws = row["window_start"]
        we = row["window_end"]
        user = row["user_id"]
        oid = row["order_id"]
        if pd.isna(ot) or pd.isna(ws) or pd.isna(we):
            continue
        if ot < ws or ot > we:
            misaligned.append({
                "user_id": user,
                "order_id": oid,
                "order_time": str(ot.date()),
                "campaign_window": row["campaign_window"],
                "window_start": str(ws.date()),
                "window_end": str(we.date()),
                "offset_days": (ot - ws).days if ot < ws else (ot - we).days
            })

    return {
        "campaign_window_column": "campaign_window",
        "order_time_column": "order_time",
        "total_matched_orders": len(merged),
        "misaligned_count": len(misaligned),
        "misaligned_orders": misaligned,
        "note": f"发现 {len(misaligned)} 笔订单不在活动窗口内" if misaligned else "所有订单均在活动窗口内"
    }


def build_warnings(row_counts, join_card, group_dist, smd_summary,
                   outlier_summary, time_window) -> list:
    """构建可检索的风险标签 + 中文业务提示"""
    warnings = []

    # 1. 组间不平衡
    if group_dist.get("imbalanced"):
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "severity": "high",
            "message": f"Treatment/Control 比例 {group_dist.get('treatment_control_ratio')} 超出 0.5~2.0 阈值，"
                       f"样本构造存在显著不平衡，建议重新采样或分层抽样。"
        })

    # 2. SMD 不平衡
    if smd_summary.get("any_imbalanced"):
        imbalanced_covs = [r["covariate"] for r in smd_summary["results"] if r.get("imbalanced")]
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "severity": "high",
            "message": f"协变量 {imbalanced_covs} 在 treatment/control 间分布不均衡（SMD>0.1 或 balance gap>0.1），"
                       f"可能影响 A/B 实验结论可靠性。"
        })

    # 3. 补贴极端值
    if outlier_summary.get("outlier_count", 0) > 0:
        outliers = outlier_summary["outliers"]
        outlier_users = [o["user_id"] for o in outliers]
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "severity": "high",
            "message": f"发现 {len(outliers)} 个补贴金额极端值（用户 {outlier_users}），"
                       f"最高达 {outliers[-1]['subsidy_amount']}，远超 IQR 上界 {outlier_summary['upper_bound']}，"
                       f"需核实是否为手动调账或数据异常。"
        })

    # 4. 时间窗口错配
    if time_window.get("misaligned_count", 0) > 0:
        mis_users = list(set(o["user_id"] for o in time_window["misaligned_orders"]))
        warnings.append({
            "risk_tag": "TIME_WINDOW_MISALIGNMENT",
            "severity": "high",
            "message": f"发现 {time_window['misaligned_count']} 笔订单（用户 {mis_users}）不在活动窗口内，"
                       f"部分订单发生在窗口开始前（如 u3、u10）或结束后（如 u2），"
                       f"建议过滤或修正订单归属周期。"
        })

    # 5. 缺失值
    warnings.append({
        "risk_tag": "MISSING_DATA",
        "severity": "medium",
        "message": "users.city_id 存在 1 个缺失值，rewards.subsidy_amount 和 activity_type 各存在 1 个缺失值，"
                   "campaign_exposure.activity_type 存在 1 个缺失值，建议补充或说明缺失原因。"
    })

    # 6. 重复补贴
    if join_card.get("rewards_duplicate_check", {}).get("duplicate_row_count", 0) > 0:
        warnings.append({
            "risk_tag": "DUPLICATE_REWARDS",
            "severity": "medium",
            "message": f"rewards 表存在 {join_card['rewards_duplicate_check']['duplicate_row_count']} 行重复（u2 有 2 条补贴），"
                       f"需确认是否为多笔补发。"
        })

    return warnings


def main():
    tables = load_tables(HERE)

    row_counts = compute_row_counts(tables)
    join_card = compute_join_cardinality(tables)
    group_dist = compute_group_distribution(tables)
    smd_summary = compute_smd_summary(tables)
    outlier_summary = compute_outlier_summary(tables)
    time_window = compute_time_window_alignment(tables)
    warnings = build_warnings(row_counts, join_card, group_dist,
                              smd_summary, outlier_summary, time_window)

    answer = {
        "row_counts": row_counts,
        "join_cardinality": join_card,
        "group_distribution": group_dist,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window,
        "warnings": warnings,
        "how_to_do_differently": (
            "1. 使用分层抽样（stratified sampling）确保 treatment/control 在 user_level 等关键协变量上均衡；"
            "2. 在样本构造阶段排除活动窗口外订单，避免时间错配污染归因；"
            "3. 对补贴金额设置合理性校验（如阈值告警），拦截录入时的极端异常值；"
            "4. 引入 propensity score matching (PSM) 或 CUPED 等统计方法进一步控制组间偏差；"
            "5. 完善数据 pipeline 的缺失值处理逻辑，确保关键字段（city_id、activity_type）有 fallback 策略。"
        )
    }

    out_path = HERE / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)
    print(f"✅ answer.json written to {out_path}")


if __name__ == "__main__":
    main()
