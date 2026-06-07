"""solve.py — growth_campaign_audit_001 数据审计"""
import json
import math
import os
from datetime import datetime

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    return pd.read_csv(os.path.join(BASE, name), keep_default_na=True)


def parse_campaign_window(win_str):
    """Parse '2026-05-01:2026-05-07' -> (start_date, end_date)"""
    parts = win_str.split(":")
    if len(parts) != 2:
        return None, None
    try:
        start = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
        end = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        return start, end
    except ValueError:
        return None, None


def numerical_smd(t, c, col):
    """Compute SMD for a numerical covariate between treatment and control."""
    vt = t[col].dropna()
    vc = c[col].dropna()
    mt = vt.mean()
    mc = vc.mean()
    var_t = vt.var(ddof=1)
    var_c = vc.var(ddof=1)
    pooled_std = math.sqrt((var_t + var_c) / 2.0)
    if pooled_std == 0:
        return 0.0
    return round(abs(mt - mc) / pooled_std, 6)


def categorical_balance_gap(t, c, col):
    """Compute absolute percentage gap for categorical covariates."""
    merged = pd.concat([t.assign(_group="treatment"), c.assign(_group="control")])
    ct = pd.crosstab(merged[col], merged["_group"], margins=False)
    # convert to percentages
    ct_pct = ct.div(ct.sum()) * 100
    gaps = {}
    for cat in ct_pct.index:
        gap = abs(ct_pct.loc[cat, "treatment"] - ct_pct.loc[cat, "control"])
        gaps[str(cat)] = round(gap, 4)
    return gaps


def main():
    # ---- Load ----
    exposure = load("campaign_exposure.csv")
    users = load("users.csv")
    rewards = load("rewards.csv")
    orders = load("orders.csv")

    answer = {}

    # =========================================================
    # 1. row_counts
    # =========================================================
    answer["row_counts"] = {
        "campaign_exposure": len(exposure),
        "users": len(users),
        "rewards": len(rewards),
        "orders": len(orders),
    }

    # =========================================================
    # 2. join_cardinality
    # =========================================================
    join_keys = ["user_id", "campaign_id", "campaign_window"]

    # exposure x rewards
    er = exposure.merge(rewards, on=join_keys, how="left", suffixes=("_exp", "_rwd"))
    # exposure x orders (only on user_id since orders has no campaign_id/window)
    eo = exposure.merge(orders, on=["user_id"], how="left")
    # exposure x users
    eu = exposure.merge(users, on=["user_id"], how="left")

    # Check duplicates in exposure on the configured key
    dup_cols = ["user_id", "campaign_window"]
    exp_dupes = int(exposure.duplicated(subset=dup_cols, keep=False).sum())

    join_card = {
        "exposure_to_rewards_keys": join_keys,
        "exposure_to_orders_keys": ["user_id"],
        "exposure_to_users_keys": ["user_id"],
        "exposure_rows": len(exposure),
        "exposure_rewards_joined_rows": len(er),
        "exposure_orders_joined_rows": len(eo),
        "exposure_users_joined_rows": len(eu),
        "exposure_duplicate_rows_on_key": exp_dupes,
        "exposure_unique_keys": len(exposure.drop_duplicates(subset=join_keys)),
        "rewards_users_with_rewards": rewards["user_id"].nunique(),
        "orders_users_with_orders": orders["user_id"].nunique(),
        "exposure_users_without_rewards": set(exposure["user_id"]) - set(rewards["user_id"]),
        "exposure_users_without_orders": set(exposure["user_id"]) - set(orders["user_id"]),
    }
    # Convert sets to sorted lists for JSON
    join_card["exposure_users_without_rewards"] = sorted(
        join_card["exposure_users_without_rewards"]
    )
    join_card["exposure_users_without_orders"] = sorted(
        join_card["exposure_users_without_orders"]
    )
    answer["join_cardinality"] = join_card

    # =========================================================
    # 3. group_distribution
    # =========================================================
    group_col = "treatment_group"
    treatment_val = "treatment"
    control_val = "control"
    min_group_ratio = 0.5

    group_counts = exposure[group_col].value_counts().to_dict()
    n_treat = group_counts.get(treatment_val, 0)
    n_ctrl = group_counts.get(control_val, 0)
    ratio = round(n_ctrl / n_treat, 4) if n_treat > 0 else None
    ratio_pass = ratio >= min_group_ratio if ratio is not None else False

    god = {
        "treatment_count": int(n_treat),
        "control_count": int(n_ctrl),
        "treatment_control_ratio": ratio,
        "min_required_ratio": min_group_ratio,
        "ratio_pass": ratio_pass,
        "all_group_counts": {str(k): int(v) for k, v in group_counts.items()},
    }
    answer["group_distribution"] = god

    # =========================================================
    # 4. smd_summary (covariate balance)
    # =========================================================
    covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"]
    numeric_covs = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d"]
    cat_covs = ["user_level"]
    smd_threshold = 0.1

    # Merge exposure with users to get covariate values
    exp_users = exposure.merge(users, on="user_id", how="left")
    treat = exp_users[exp_users[group_col] == treatment_val]
    control = exp_users[exp_users[group_col] == control_val]

    smd_results = {}
    balance_fail = []

    for col in numeric_covs:
        smd = numerical_smd(treat, control, col)
        smd_results[col] = {
            "smd": smd,
            "treatment_mean": round(treat[col].mean(), 4),
            "control_mean": round(control[col].mean(), 4),
            "threshold": smd_threshold,
            "pass": smd < smd_threshold,
        }
        if smd >= smd_threshold:
            balance_fail.append(col)

    for col in cat_covs:
        gaps = categorical_balance_gap(treat, control, col)
        max_gap = max(gaps.values()) if gaps else 0.0
        smd_results[col] = {
            "balance_gaps_pct": gaps,
            "max_gap_pct": round(max_gap, 4),
            "pass": max_gap < smd_threshold * 100,
        }
        if max_gap >= smd_threshold * 100:
            balance_fail.append(col)

    answer["smd_summary"] = {
        "covariates_used": covariates,
        "smd_threshold": smd_threshold,
        "results": smd_results,
        "all_pass": len(balance_fail) == 0,
        "failed_covariates": balance_fail,
    }

    # =========================================================
    # 5. outlier_summary (subsidy_amount IQR)
    # =========================================================
    subsidy_col = "subsidy_amount"
    subs = rewards[subsidy_col].dropna().astype(float)
    q1 = subs.quantile(0.25)
    q3 = subs.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = subs[(subs < lower) | (subs > upper)]
    outlier_details = []
    max_amount = None
    if len(outliers) > 0:
        for idx in outliers.index:
            row = rewards.loc[idx]
            outlier_details.append({
                "user_id": str(row["user_id"]),
                "subsidy_amount": float(outliers.loc[idx]),
            })
        max_amount = float(outliers.max())

    answer["outlier_summary"] = {
        "column": subsidy_col,
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_bound": round(float(lower), 2),
        "upper_bound": round(float(upper), 2),
        "outlier_count": int(len(outliers)),
        "total_non_null": int(subs.count()),
        "outlier_details": outlier_details,
        "max_subsidy_amount": max_amount,
        "has_outliers": len(outliers) > 0,
    }

    # =========================================================
    # 6. time_window_alignment
    # =========================================================
    # Parse campaign_window from exposure (each user may have different window)
    exp_orders = exposure.merge(orders, on="user_id", how="inner")
    misaligned = []
    aligned_count = 0
    misaligned_count = 0

    for _, row in exp_orders.iterrows():
        win_start, win_end = parse_campaign_window(row["campaign_window"])
        if win_start is None or win_end is None:
            misaligned_count += 1
            misaligned.append({
                "user_id": str(row["user_id"]),
                "order_id": str(row["order_id"]),
                "order_time": str(row["order_time"]),
                "campaign_window": str(row["campaign_window"]),
                "issue": "unparseable_campaign_window",
            })
            continue
        try:
            ot = datetime.strptime(row["order_time"], "%Y-%m-%d").date()
        except ValueError:
            misaligned_count += 1
            misaligned.append({
                "user_id": str(row["user_id"]),
                "order_id": str(row["order_id"]),
                "order_time": str(row["order_time"]),
                "campaign_window": str(row["campaign_window"]),
                "issue": "unparseable_order_time",
            })
            continue
        if win_start <= ot <= win_end:
            aligned_count += 1
        else:
            misaligned_count += 1
            days_off = (ot - win_start).days if ot < win_start else (ot - win_end).days
            misaligned.append({
                "user_id": str(row["user_id"]),
                "order_id": str(row["order_id"]),
                "order_time": str(row["order_time"]),
                "campaign_window": str(row["campaign_window"]),
                "issue": "outside_window",
                "days_offset": days_off,
            })

    # Also check users in exposure who have NO orders at all
    exposed_users = set(exposure["user_id"])
    ordered_users = set(orders["user_id"])
    no_order_users = sorted(exposed_users - ordered_users)

    answer["time_window_alignment"] = {
        "exposed_users_with_orders": int(exp_orders["user_id"].nunique()),
        "orders_in_window": aligned_count,
        "orders_outside_window": misaligned_count,
        "total_orders_exposed": int(len(exp_orders)),
        "exposed_users_without_orders": no_order_users,
        "misalignment_rate": round(misaligned_count / len(exp_orders), 4) if len(exp_orders) > 0 else 0.0,
        "details": misaligned,
    }

    # =========================================================
    # 7. warnings
    # =========================================================
    warnings = []

    # Group imbalance
    if not ratio_pass:
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "description": f"对照组/实验组比例 {ratio} 低于最低要求 {min_group_ratio}，样本分组严重不均衡",
            "severity": "high",
        })

    # Covariate imbalance
    if balance_fail:
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "description": f"以下协变量在组间存在显著差异 (SMD >= {smd_threshold}): {balance_fail}，可能影响效应估计",
            "severity": "high",
            "failed_covariates": balance_fail,
        })

    # Subsidy outliers
    if len(outliers) > 0:
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "description": f"补贴金额存在 {len(outliers)} 个极端值 (上限 {round(upper, 2)})，最高值 {max_amount}，需排查是否为录入错误或特殊策略",
            "severity": "medium",
            "outlier_count": int(len(outliers)),
        })

    # Time window misalignment
    if misaligned_count > 0:
        warnings.append({
            "risk_tag": "TIME_WINDOW_MISMATCH",
            "description": f"有 {misaligned_count}/{len(exp_orders)} 笔订单不在活动窗口内，转化的归因口径可能不准确",
            "severity": "high",
            "misaligned_count": misaligned_count,
        })

    # Missing exposure activity_type
    missing_act = int(exposure["activity_type"].isna().sum())
    if missing_act > 0:
        warnings.append({
            "risk_tag": "MISSING_EXPOSURE_ACTIVITY",
            "description": f"campaign_exposure 中有 {missing_act} 条记录的 activity_type 为空",
            "severity": "low",
        })

    # Missing rewards
    no_reward_users = sorted(set(exposure["user_id"]) - set(rewards["user_id"]))
    if no_reward_users:
        warnings.append({
            "risk_tag": "REWARDS_GAP",
            "description": f"以下曝光用户未在 rewards 表中出现: {no_reward_users}，可能缺少补贴记录",
            "severity": "medium",
            "users": no_reward_users,
        })

    # Users without orders
    if no_order_users:
        warnings.append({
            "risk_tag": "NO_ORDER_USERS",
            "description": f"以下曝光用户没有任何订单记录: {no_order_users}",
            "severity": "medium",
            "users": no_order_users,
        })

    answer["warnings"] = warnings

    # =========================================================
    # 8. how_to_do_differently
    # =========================================================
    answer["how_to_do_differently"] = {
        "note": "以下是针对本数据审计流程的改进方向",
        "suggestions": [
            "在实验设计阶段使用分层随机化(stratified randomization)或PSM来确保treatment/control组间协变量均衡，避免事后才发现严重不平衡",
            "对subsidy_amount设置业务合理的上下限阈值，在数据入库环节做校验拦截，而非事后排查",
            "建立campaign_window与order_time的入库级联约束，确保只有窗口内的订单才能关联到活动曝光记录",
            "完善数据完整性约束：campaign_exposure的activity_type应有非空约束，rewards的subsidy_amount应有非空约束",
            "增加exposure-rewards之间的外键引用或定期对账机制，避免曝光用户缺少对应的奖励记录",
            "审计流程本身可以自动化配置化，每次活动投放后自动生成审计报告",
        ],
    }

    # ---- Write answer.json ----
    out_path = os.path.join(BASE, "answer.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ answer.json written to {out_path}")
    print(f"   keys: {list(answer.keys())}")


if __name__ == "__main__":
    main()
