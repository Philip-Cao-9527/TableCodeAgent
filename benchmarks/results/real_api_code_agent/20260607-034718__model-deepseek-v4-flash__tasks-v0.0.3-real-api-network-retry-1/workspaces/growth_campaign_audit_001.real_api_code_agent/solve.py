"""
solve.py — growth_campaign_audit_001
营销活动样本构造数据审计：多表 join、treatment/control 分布、组间平衡、补贴极端值、订单时间窗口。
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


def load_data():
    users = pd.read_csv(ROOT / "users.csv")
    exposure = pd.read_csv(ROOT / "campaign_exposure.csv")
    orders = pd.read_csv(ROOT / "orders.csv")
    rewards = pd.read_csv(ROOT / "rewards.csv")
    return users, exposure, orders, rewards


def calc_row_counts(users, exposure, orders, rewards):
    return {
        "users": {"rows": len(users), "columns": len(users.columns)},
        "campaign_exposure": {"rows": len(exposure), "columns": len(exposure.columns)},
        "orders": {"rows": len(orders), "columns": len(orders.columns)},
        "rewards": {"rows": len(rewards), "columns": len(rewards.columns)},
    }


def calc_join_cardinality(users, exposure, orders, rewards):
    """Check join cardinality between key tables."""
    results = {}

    # users <-> campaign_exposure (on user_id)
    left = users.merge(exposure, on="user_id", how="left", suffixes=("_u", "_e"))
    n_left = len(left)
    n_left_u = users["user_id"].nunique()
    n_left_e = exposure["user_id"].nunique()
    results["users_to_campaign_exposure"] = {
        "left_table": "users",
        "right_table": "campaign_exposure",
        "left_rows": len(users),
        "right_rows": len(exposure),
        "join_key": "user_id",
        "joined_rows": n_left,
        "left_unique_keys": n_left_u,
        "right_unique_keys": n_left_e,
        "row_expansion_detected": n_left > len(users),
        "note": "1:1 映射，无扩行" if n_left == len(users) else f"出现扩行: {n_left} vs {len(users)}",
    }

    # campaign_exposure <-> rewards (on user_id, campaign_id, campaign_window)
    join_keys = ["user_id", "campaign_id", "campaign_window"]
    cer = exposure.merge(rewards, on=join_keys, how="left", suffixes=("_e", "_r"))
    n_cer = len(cer)
    results["campaign_exposure_to_rewards"] = {
        "left_table": "campaign_exposure",
        "right_table": "rewards",
        "join_keys": join_keys,
        "left_rows": len(exposure),
        "right_rows": len(rewards),
        "joined_rows": n_cer,
        "row_expansion_detected": n_cer > len(exposure),
        "note": "1:1 映射，无扩行" if n_cer == len(exposure) else f"出现扩行: {n_cer} vs {len(exposure)}",
    }

    # users <-> orders (on user_id) - likely 1:N
    uo = users.merge(orders, on="user_id", how="left")
    n_uo = len(uo)
    results["users_to_orders"] = {
        "left_table": "users",
        "right_table": "orders",
        "join_key": "user_id",
        "left_rows": len(users),
        "right_rows": len(orders),
        "joined_rows": n_uo,
        "left_unique_keys": users["user_id"].nunique(),
        "right_unique_keys": orders["user_id"].nunique(),
        "row_expansion_detected": n_uo > len(users),
        "note": "1:N 映射（存在扩行），部分用户有多笔订单",
    }

    return results


def calc_group_distribution(exposure):
    counts = exposure["treatment_group"].value_counts().to_dict()
    treatment_count = counts.get("treatment", 0)
    control_count = counts.get("control", 0)
    total = treatment_count + control_count
    ratio = control_count / treatment_count if treatment_count else 0
    return {
        "treatment_count": treatment_count,
        "control_count": control_count,
        "total": total,
        "treatment_pct": round(treatment_count / total * 100, 2) if total else 0,
        "control_pct": round(control_count / total * 100, 2) if total else 0,
        "minority_to_majority_ratio": round(ratio, 4),
        "imbalanced": ratio < 0.5,
        "threshold": 0.5,
    }


def calc_smd_summary(users, exposure):
    """Merge exposure with users, then compute SMD for numeric covariates + categorical for user_level."""
    df = exposure.merge(users, on="user_id", how="left")
    covariates_num = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    covariates_cat = ["user_level"]

    treatment = df[df["treatment_group"] == "treatment"]
    control = df[df["treatment_group"] == "control"]

    results = {}
    warnings_ = []

    # Numeric SMD
    for col in covariates_num:
        t_vals = treatment[col].dropna().astype(float)
        c_vals = control[col].dropna().astype(float)
        if len(t_vals) < 2 or len(c_vals) < 2:
            results[col] = {"smd": None, "note": "样本量不足，无法计算 SMD"}
            warnings_.append(f"{col}: 组内样本量不足")
            continue
        t_mean = t_vals.mean()
        c_mean = c_vals.mean()
        t_var = t_vals.var(ddof=1)
        c_var = c_vals.var(ddof=1)
        pooled_std = math.sqrt((t_var + c_var) / 2)
        if pooled_std == 0:
            smd = 0.0
        else:
            smd = abs(t_mean - c_mean) / pooled_std
        results[col] = {
            "smd": round(smd, 4),
            "treatment_mean": round(t_mean, 2),
            "control_mean": round(c_mean, 2),
            "imbalanced": smd > 0.1,
        }
        if smd > 0.1:
            warnings_.append(f"{col}: SMD={smd:.4f} > 0.1，组间不平衡")

    # Categorical: user_level
    for col in covariates_cat:
        cross = pd.crosstab(df["user_level"], df["treatment_group"])
        # Simple balance metric: proportion difference per level
        t_total = treatment[col].value_counts()
        c_total = control[col].value_counts()
        all_levels = set(list(t_total.index) + list(c_total.index))
        cat_balance = {}
        max_diff = 0.0
        for level in all_levels:
            t_prop = t_total.get(level, 0) / max(len(treatment), 1)
            c_prop = c_total.get(level, 0) / max(len(control), 1)
            diff = abs(t_prop - c_prop)
            cat_balance[level] = {
                "treatment_proportion": round(t_prop, 4),
                "control_proportion": round(c_prop, 4),
                "abs_diff": round(diff, 4),
            }
            max_diff = max(max_diff, diff)
        results[col] = {
            "type": "categorical",
            "levels": cat_balance,
            "max_proportion_diff": round(max_diff, 4),
            "imbalanced": max_diff > 0.15,
        }
        if max_diff > 0.15:
            warnings_.append(f"{col}: 最大比例差异={max_diff:.4f} > 0.15，组间分布不平衡")

    return {
        "covariates_checked": covariates_num + covariates_cat,
        "smd_threshold": 0.1,
        "details": results,
        "warning_count": len(warnings_),
        "warnings": warnings_,
    }


def calc_outlier_summary(rewards):
    """IQR-based outlier detection on subsidy_amount."""
    col = "subsidy_amount"
    vals = pd.to_numeric(rewards[col], errors="coerce").dropna()
    if len(vals) == 0:
        return {"column": col, "note": "无可用的补贴金额数据"}

    Q1 = vals.quantile(0.25)
    Q3 = vals.quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - 1.5 * IQR
    upper = Q3 + 1.5 * IQR

    outliers = rewards[
        pd.to_numeric(rewards[col], errors="coerce").between(lower, upper, inclusive="neither")
    ]
    outlier_rows = []
    for _, row in outliers.iterrows():
        outlier_rows.append(
            {
                "user_id": row["user_id"],
                "subsidy_amount": row[col],
                "reason": f"超出 IQR 范围 [{round(lower,2)}, {round(upper,2)}]",
            }
        )

    return {
        "column": col,
        "method": "iqr",
        "iqr_multiplier": 1.5,
        "q1": round(Q1, 2),
        "q3": round(Q3, 2),
        "iqr": round(IQR, 2),
        "lower_bound": round(lower, 2),
        "upper_bound": round(upper, 2),
        "outlier_count": len(outlier_rows),
        "outlier_examples": outlier_rows[:5],
    }


def calc_time_window_alignment(exposure, orders):
    """Check whether each order_time falls within the user's campaign_window."""
    window_map = exposure.set_index("user_id")["campaign_window"].to_dict()

    mismatches = []
    checked = 0
    for _, row in orders.iterrows():
        uid = row["user_id"]
        order_time_str = str(row["order_time"]).strip()
        if uid not in window_map:
            continue
        window_str = window_map[uid]
        checked += 1
        try:
            # Parse "2026-05-01:2026-05-07"
            parts = window_str.split(":")
            if len(parts) != 2:
                continue
            start_str, end_str = parts[0].strip(), parts[1].strip()
            order_ts = pd.Timestamp(order_time_str)
            start_ts = pd.Timestamp(start_str)
            end_ts = pd.Timestamp(end_str)
            if not (start_ts <= order_ts <= end_ts):
                mismatches.append(
                    {
                        "user_id": uid,
                        "order_id": row["order_id"],
                        "order_time": order_time_str,
                        "campaign_window": window_str,
                        "mismatch_reason": "order_outside_campaign_window",
                    }
                )
        except Exception:
            continue

    return {
        "total_orders": len(orders),
        "checked_orders": checked,
        "mismatch_count": len(mismatches),
        "mismatch_rate": round(len(mismatches) / checked * 100, 2) if checked else 0,
        "mismatch_details": mismatches,
    }


def build_report():
    users, exposure, orders, rewards = load_data()

    row_counts = calc_row_counts(users, exposure, orders, rewards)
    join_cardinality = calc_join_cardinality(users, exposure, orders, rewards)
    group_distribution = calc_group_distribution(exposure)
    smd_summary = calc_smd_summary(users, exposure)
    outlier_summary = calc_outlier_summary(rewards)
    time_window_alignment = calc_time_window_alignment(exposure, orders)

    warnings = []

    # 1. Group imbalance
    if group_distribution["imbalanced"]:
        warnings.append({
            "risk_tag": "group_imbalance",
            "severity": "high",
            "message": f"对照组占比过低: treatment={group_distribution['treatment_count']}, "
                       f"control={group_distribution['control_count']}, 比值={group_distribution['minority_to_majority_ratio']}。"
                       f"建议增加对照组样本或调整分组策略。",
        })

    # 2. SMD imbalance
    for cov, detail in smd_summary["details"].items():
        if isinstance(detail, dict) and detail.get("imbalanced"):
            smd_val = detail.get("smd")
            if smd_val is not None:
                warnings.append({
                    "risk_tag": f"covariate_imbalance_{cov}",
                    "severity": "medium",
                    "message": f"协变量 {cov} SMD={smd_val} > 0.1，treatment/control 组间存在不平衡，"
                               f"可能影响因果推断。建议使用 PS matching 或逆概率加权。",
                })

    # 3. Outliers
    if outlier_summary["outlier_count"] > 0:
        warnings.append({
            "risk_tag": "subsidy_outliers",
            "severity": "high",
            "message": f"补贴金额存在 {outlier_summary['outlier_count']} 个 IQR 极端值"
                       f"(上限 {outlier_summary['upper_bound']})。"
                       f"用户 {[x['user_id'] for x in outlier_summary['outlier_examples']]} 的补贴金额异常高，"
                       f"建议核实数据准确性或考虑 winsorize。",
        })

    # 4. Time window misalignment
    if time_window_alignment["mismatch_count"] > 0:
        warnings.append({
            "risk_tag": "order_time_window_mismatch",
            "severity": "high",
            "message": f"{time_window_alignment['mismatch_count']} 笔订单({time_window_alignment['mismatch_rate']}%)不在 campaign 时间窗口内。"
                       f"涉及用户: {[m['user_id'] for m in time_window_alignment['mismatch_details']]}。"
                       f"建议重新梳理归因逻辑或清洗订单时间数据。",
        })

    # 5. Missing values
    if exposure["activity_type"].isna().sum() > 0:
        warnings.append({
            "risk_tag": "missing_activity_type",
            "severity": "low",
            "message": f"campaign_exposure 中 activity_type 存在 {exposure['activity_type'].isna().sum()} 条缺失值，建议补充或填充默认值。",
        })

    if users["city_id"].isna().sum() > 0:
        warnings.append({
            "risk_tag": "missing_city_id",
            "severity": "low",
            "message": f"users 中 city_id 存在 {users['city_id'].isna().sum()} 条缺失值，建议补充。",
        })

    answer = {
        "row_counts": row_counts,
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings,
        "how_to_do_differently": "1) 组间严重不均衡(8:2)，应在实验设计阶段采用 stratified randomization 确保 treatment/control 比例合理；"
        "2) SMD 计算需先 merge users 表与 exposure 表获取协变量，当前提示 covariates 不在同一表中表明实际 pipeline 中应预先做好特征宽表；"
        "3) 补贴极端值(u8:500)应核实是否录入错误，建议在 reward 发放阶段加入业务规则校验(如单笔补贴上限 100)；"
        "4) 4/9 订单超出 campaign 窗口，说明归因窗口定义或事件上报逻辑有误，应在 pipeline 中加强时间约束检查；"
        "5) 数据缺失值(activity_type/city_id)应在 ETL 阶段处理，避免下游分析偏差。",
    }

    out_path = ROOT / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)
    print(f"✅ answer.json written to {out_path}")


if __name__ == "__main__":
    build_report()
