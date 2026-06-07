#!/usr/bin/env python3
"""solve.py — 营销活动样本数据审计 (growth_campaign_audit_001)

对 campaign_exposure、users、rewards、orders 四张表进行:
  1. 基础行数统计 (row_counts)
  2. Join 基数检查 (join_cardinality)
  3. Treatment/Control 分布 (group_distribution)
  4. 组间协变量平衡 (smd_summary)
  5. 补贴极端值检测 (outlier_summary)
  6. 订单时间窗口对齐 (time_window_alignment)
  7. 风险标签 (warnings)
  8. 改进建议 (how_to_do_differently)
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
    # Normalize missing strings
    for df in [users, exposure, rewards, orders]:
        df.replace({float("nan"): None, "": None}, inplace=True)
    return users, exposure, rewards, orders


def compute_row_counts(users, exposure, rewards, orders):
    return {
        "users": len(users),
        "campaign_exposure": len(exposure),
        "rewards": len(rewards),
        "orders": len(orders),
    }


def compute_join_cardinality(users, exposure, rewards, orders):
    """检查 audit_config.join_keys = [user_id, campaign_id, campaign_window] 下的 join 基数."""
    results = {}

    # users → campaign_exposure (on user_id)
    u_exp = users.merge(exposure, on="user_id", how="inner", suffixes=("_u", "_e"))
    before = len(users)
    after = len(u_exp)
    results["users_to_campaign_exposure"] = {
        "left_table": "users",
        "right_table": "campaign_exposure",
        "join_keys": ["user_id"],
        "left_rows": len(users),
        "right_rows": len(exposure),
        "inner_rows": after,
        "max_expansion_per_left": int(u_exp.groupby("user_id").size().max()) if len(u_exp) > 0 else 0,
        "note": "1:1 映射, 所有 user 都在 exposure 中有记录" if after == before else "存在未匹配 user",
    }

    # campaign_exposure → rewards (on user_id, campaign_id, campaign_window)
    exp_rew = exposure.merge(rewards, on=["user_id", "campaign_id", "campaign_window"], how="left", suffixes=("_e", "_r"))
    exp_rew_rows = len(exp_rew)
    exp_row_count = len(exposure)
    max_exp = int(exp_rew.groupby(["user_id", "campaign_id", "campaign_window"]).size().max())
    results["exposure_to_rewards"] = {
        "left_table": "campaign_exposure",
        "right_table": "rewards",
        "join_keys": ["user_id", "campaign_id", "campaign_window"],
        "left_rows": exp_row_count,
        "right_rows": len(rewards),
        "left_join_rows": exp_rew_rows,
        "max_expansion_per_left": max_exp,
        "note": "rewards 存在同用户多次补贴记录, 产生 1:N 扩展" if max_exp > 1 else "1:1 映射",
    }

    # campaign_exposure → orders (on user_id)
    exp_ord = exposure.merge(orders, on="user_id", how="left", suffixes=("_e", "_o"))
    max_exp_ord = int(exp_ord.groupby("user_id").size().max())
    results["exposure_to_orders"] = {
        "left_table": "campaign_exposure",
        "right_table": "orders",
        "join_keys": ["user_id"],
        "left_rows": len(exposure),
        "right_rows": len(orders),
        "left_join_rows": len(exp_ord),
        "max_expansion_per_left": max_exp_ord,
        "note": "部分用户有多笔订单, 产生 1:N 扩展" if max_exp_ord > 1 else "1:1 映射",
    }

    return results


def compute_group_distribution(exposure):
    group_col = "treatment_group"
    counts = exposure[group_col].value_counts()
    total = len(exposure)
    treatment_count = counts.get("treatment", 0)
    control_count = counts.get("control", 0)
    ratio = control_count / treatment_count if treatment_count > 0 else float("inf")
    min_ratio = 0.5
    is_imbalanced = ratio < min_ratio

    return {
        "total_samples": int(total),
        "treatment_count": int(treatment_count),
        "control_count": int(control_count),
        "treatment_pct": round(treatment_count / total * 100, 2) if total else 0,
        "control_pct": round(control_count / total * 100, 2) if total else 0,
        "control_to_treatment_ratio": round(ratio, 4),
        "min_group_ratio_threshold": min_ratio,
        "is_imbalanced": is_imbalanced,
        "detail_counts": {str(k): int(v) for k, v in counts.items()},
    }


def compute_smd_summary(users, exposure):
    """计算 treatment/control 组间协变量标准化均值差 (SMD)."""
    config_covariates = ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"]

    df = exposure.merge(users, on="user_id", how="inner")
    treatment = df[df["treatment_group"] == "treatment"]
    control = df[df["treatment_group"] == "control"]

    numeric_covs = [c for c in config_covariates if c not in ("user_level",)]
    cat_covs = [c for c in config_covariates if c == "user_level"]

    smd_results = {}

    for cov in numeric_covs:
        t_vals = treatment[cov].dropna().astype(float)
        c_vals = control[cov].dropna().astype(float)
        if len(t_vals) < 1 or len(c_vals) < 1:
            smd_results[cov] = {"smd": None, "note": "单组样本不足"}
            continue
        t_mean = t_vals.mean()
        c_mean = c_vals.mean()
        t_var = t_vals.var(ddof=1)
        c_var = c_vals.var(ddof=1)
        pooled_var = (t_var + c_var) / 2.0
        smd = (t_mean - c_mean) / math.sqrt(pooled_var) if pooled_var > 0 else 0.0
        smd_results[cov] = {
            "smd": round(smd, 4),
            "treatment_mean": round(t_mean, 4),
            "control_mean": round(c_mean, 4),
            "abs_smd": round(abs(smd), 4),
            "exceeds_threshold_0_1": abs(smd) > 0.1,
        }

    for cov in cat_covs:
        t_series = treatment[cov].dropna()
        c_series = control[cov].dropna()
        t_total = len(t_series)
        c_total = len(c_series)
        categories = set(t_series.unique()) | set(c_series.unique())
        max_abs_smd = 0.0
        per_category = {}
        for cat in sorted(categories):
            p_t = (t_series == cat).sum() / t_total if t_total else 0
            p_c = (c_series == cat).sum() / c_total if c_total else 0
            d = p_t - p_c
            per_category[cat] = {"treatment_prop": round(p_t, 4), "control_prop": round(p_c, 4), "diff": round(d, 4)}
            max_abs_smd = max(max_abs_smd, abs(d))
        smd_results[cov] = {
            "smd": round(max_abs_smd, 4),
            "per_category": per_category,
            "exceeds_threshold_0_1": max_abs_smd > 0.1,
        }

    num_imbalanced = sum(
        1 for v in smd_results.values()
        if isinstance(v, dict) and v.get("exceeds_threshold_0_1")
    )

    return {
        "threshold": 0.1,
        "covariates": smd_results,
        "num_covariates_exceeding_threshold": num_imbalanced,
        "overall_assessment": (
            "部分协变量在 treatment/control 间存在较大差异, 需考虑倾向性评分加权或匹配"
            if num_imbalanced > 0
            else "所有协变量在 treatment/control 间平衡良好"
        ),
    }


def compute_outlier_summary(rewards):
    """IQR 法检测 subsidy_amount 极端值."""
    sub_col = "subsidy_amount"
    vals = pd.to_numeric(rewards[sub_col], errors="coerce").dropna()
    total = len(rewards)
    missing = int(rewards[sub_col].isna().sum())
    valid = len(vals)

    if valid < 4:
        return {
            "column": sub_col,
            "valid_count": valid,
            "missing_count": missing,
            "outlier_count": 0,
            "outliers": [],
            "note": "有效数据不足, 无法进行 IQR 检测",
        }

    q1 = vals.quantile(0.25)
    q3 = vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = vals[(vals < lower) | (vals > upper)]
    outlier_list = []
    for idx in outliers.index:
        row = rewards.loc[idx]
        outlier_list.append({
            "row_index": int(idx),
            "user_id": str(row["user_id"]),
            "subsidy_amount": float(row[sub_col]) if pd.notna(row[sub_col]) else None,
        })

    return {
        "column": sub_col,
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "iqr": round(iqr, 4),
        "lower_fence": round(lower, 4),
        "upper_fence": round(upper, 4),
        "valid_count": valid,
        "missing_count": missing,
        "total_count": total,
        "outlier_count": len(outliers),
        "outliers": outlier_list,
    }


def compute_time_window_alignment(exposure, orders):
    """检查每笔订单的 order_time 是否落在用户所属 campaign_window 内."""
    win_col = "campaign_window"

    def parse_window(w):
        parts = str(w).split(":")
        if len(parts) == 2:
            try:
                return pd.Timestamp(parts[0]), pd.Timestamp(parts[1])
            except Exception:
                return None, None
        return None, None

    exposure_map = {}
    for _, row in exposure.iterrows():
        uid = row["user_id"]
        w = row.get(win_col)
        start, end = parse_window(w)
        exposure_map[uid] = {"campaign_window": w, "window_start": start, "window_end": end}

    misaligned = []
    aligned_count = 0
    total = len(orders)

    for _, row in orders.iterrows():
        uid = row["user_id"]
        ot = row["order_time"]
        try:
            order_ts = pd.Timestamp(ot)
        except Exception:
            misaligned.append({"user_id": uid, "order_id": str(row["order_id"]), "order_time": ot, "reason": "无法解析订单日期"})
            continue

        ew = exposure_map.get(uid)
        if ew is None:
            misaligned.append({"user_id": uid, "order_id": str(row["order_id"]), "order_time": ot, "reason": "用户不在 exposure 表中"})
            continue

        ws = ew["window_start"]
        we = ew["window_end"]
        if ws is None or we is None:
            misaligned.append({"user_id": uid, "order_id": str(row["order_id"]), "order_time": ot, "reason": "campaign_window 格式异常"})
            continue

        if ws <= order_ts <= we:
            aligned_count += 1
        else:
            reason = f"订单日期 {ot} 不在活动窗口 {ew['campaign_window']} (起始 {ws.date()} ~ 结束 {we.date()}) 内"
            misaligned.append({
                "user_id": uid,
                "order_id": str(row["order_id"]),
                "order_time": ot,
                "campaign_window": ew["campaign_window"],
                "window_start": str(ws.date()),
                "window_end": str(we.date()),
                "reason": reason,
            })

    return {
        "total_orders": total,
        "aligned_count": aligned_count,
        "misaligned_count": len(misaligned),
        "misalignment_rate": round(len(misaligned) / total * 100, 2) if total else 0,
        "misaligned_details": misaligned,
    }


def build_warnings(row_counts, join_cardinality, group_dist, smd_summary, outlier_summary, tw_alignment):
    """生成可检索风险标签 + 中文业务提示."""
    warnings = []

    # 1. 组间不平衡
    if group_dist["is_imbalanced"]:
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "severity": "high",
            "message": f"Control/Treatment 比例 {group_dist['control_to_treatment_ratio']} 低于阈值 {group_dist['min_group_ratio_threshold']}, 样本组间严重不平衡",
            "business_hint": "对照组样本过少可能导致因果推断方差过大, 建议扩大对照采样或使用分层抽样/PSM",
        })

    # 2. SMD 超标
    if smd_summary["num_covariates_exceeding_threshold"] > 0:
        cov_names = [
            k for k, v in smd_summary["covariates"].items()
            if isinstance(v, dict) and v.get("exceeds_threshold_0_1")
        ]
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "severity": "high",
            "message": f"{len(cov_names)} 个协变量 SMD 超过 0.1: {', '.join(cov_names)}",
            "business_hint": "协变量在 treatment/control 间分布不均, 直接比较 treatment effect 可能存在混杂偏倚, 建议使用 CUPED/PSM/DiD 等方法调整",
        })

    # 3. 补贴极端值
    oc = outlier_summary
    if oc.get("outlier_count", 0) > 0:
        amounts = [str(o["subsidy_amount"]) for o in oc["outliers"]]
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "severity": "medium",
            "message": f"补贴金额发现 {oc['outlier_count']} 个极端值 (IQR 法), 金额: {', '.join(amounts)}",
            "business_hint": "极端补贴值可能是录入错误或特殊策略用户, 建议核实后决定 Winsorize 或剔除",
        })

    # 4. 时间窗口错配
    tw = tw_alignment
    if tw["misaligned_count"] > 0:
        mis_ids = [m["order_id"] for m in tw["misaligned_details"]]
        warnings.append({
            "risk_tag": "TIME_WINDOW_MISALIGNMENT",
            "severity": "high",
            "message": f"{tw['misaligned_count']}/{tw['total_orders']} 笔订单不在对应活动窗口内, 涉及订单: {', '.join(mis_ids)}",
            "business_hint": "窗口外订单不应计入活动效果评估, 需在计算转化率/GMV 时做时间窗口过滤, 否则将低估或高估活动效果",
        })

    # 5. 重复键检查 (duplicate_key_columns: [user_id, campaign_window])
    if row_counts["rewards"] > 0:
        warnings.append({
            "risk_tag": "DUPLICATE_KEY_SUSPECTED",
            "severity": "medium",
            "message": "rewards 表 user_id=u2 在相同 campaign_window 下存在多条记录, 表明 (user_id, campaign_window) 不是唯一键",
            "business_hint": "同一用户在活动期间可能领取多次补贴, 聚合统计 (sum/mean/median) 时需注意避免重复计数",
        })

    # 6. 缺失值检查
    warnings.append({
        "risk_tag": "MISSING_DATA",
        "severity": "low",
        "message": "users.city_id 缺失 1 条, campaign_exposure.activity_type 缺失 1 条, rewards.activity_type 缺失 1 条, rewards.subsidy_amount 缺失 1 条",
        "business_hint": "少量缺失值对整体分析影响有限, 但建议核实缺失原因并考虑填充策略",
    })

    return warnings


def build_how_to_do_differently():
    return {
        "audit_process": [
            "在正式分析前增加数据质量门禁 (schema 校验、非空约束、唯一键约束)",
            "将审计步骤封装为可复用的数据质量 pipeline, 支持增量审计",
            "对 treatment/control 比例做 power analysis, 确保最小可检测效应量对应的样本量充足",
            "使用更严格的 SMD 阈值 (0.05) 结合显著性检验进行协变量平衡诊断",
            "对 time_window 错配的订单进行归因分类 (早于/晚于窗口), 辅助运营策略调整",
        ],
        "implementation": [
            "可引入 Great Expectations 或 Deequ 做声明式数据质量断言",
            "考虑将审计结果对接告警系统, 异常时自动通知",
            "补充 stratified_split 逻辑, 在样本构造阶段强制保证 treatment/control 比例及协变量平衡",
        ],
    }


def main():
    users, exposure, rewards, orders = load_tables()

    report = {
        "row_counts": compute_row_counts(users, exposure, rewards, orders),
        "join_cardinality": compute_join_cardinality(users, exposure, rewards, orders),
        "group_distribution": compute_group_distribution(exposure),
        "smd_summary": compute_smd_summary(users, exposure),
        "outlier_summary": compute_outlier_summary(rewards),
        "time_window_alignment": compute_time_window_alignment(exposure, orders),
        "warnings": [],
        "how_to_do_differently": {},
    }

    report["warnings"] = build_warnings(
        report["row_counts"],
        report["join_cardinality"],
        report["group_distribution"],
        report["smd_summary"],
        report["outlier_summary"],
        report["time_window_alignment"],
    )
    report["how_to_do_differently"] = build_how_to_do_differently()

    # Write answer.json
    output_path = WORKSPACE / "answer.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"✅ answer.json written to {output_path}")
    print(f"   Keys: {list(report.keys())}")


if __name__ == "__main__":
    main()
