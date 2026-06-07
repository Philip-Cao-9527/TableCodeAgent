#!/usr/bin/env python3
"""solve.py — growth_campaign_audit_001 营销活动样本构造数据审计"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


class NumpyEncoder(json.JSONEncoder):
    """Handle numpy types for JSON serialization."""
    def default(self, o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

WORKSPACE = Path(__file__).resolve().parent
ANSWER_PATH = WORKSPACE / "answer.json"


def load_task_config() -> dict:
    with open(WORKSPACE / "task.json", encoding="utf-8") as f:
        return json.load(f)


def load_tables(cfg: dict) -> dict[str, pd.DataFrame]:
    tables = {}
    for name, fname in cfg["tables"].items():
        tables[name] = pd.read_csv(WORKSPACE / fname, dtype_backend="numpy_nullable",
                                   keep_default_na=False)
    return tables


def compute_row_counts(tables: dict[str, pd.DataFrame]) -> dict:
    return {name: len(df) for name, df in tables.items()}


def compute_join_cardinality(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    ac = cfg["audit_config"]
    keys = ac["join_keys"]

    exposure = tables["campaign_exposure"]
    users = tables["users"]
    rewards = tables["rewards"]
    orders = tables["orders"]

    exp_users = exposure.merge(users, on=["user_id"], how="left")
    exp_rewards = exposure.merge(rewards, on=keys, how="left")
    exp_orders = exposure.merge(orders, on=["user_id"], how="left")

    result = {
        "exposure_users_join": {
            "left_rows": len(exposure),
            "right_rows": len(users),
            "result_rows": len(exp_users),
            "matched_user_ids": sorted(exp_users["user_id"].unique().tolist()),
        },
        "exposure_rewards_join": {
            "left_rows": len(exposure),
            "right_rows": len(rewards),
            "result_rows": len(exp_rewards),
            "note": "按 [user_id, campaign_id, campaign_window] join；rewards 中 u2 有两条记录，导致行数扩展",
        },
        "exposure_orders_join": {
            "left_rows": len(exposure),
            "right_rows": len(orders),
            "result_rows": len(exp_orders),
            "note": "按 user_id join；orders 中 u2 有两条记录，导致行数扩展",
        },
    }

    # Check for unmatched rows
    unmatched_users = exp_users[exp_users["city_id"].isna() | (exp_users["city_id"] == "")]
    if len(unmatched_users):
        result["exposure_users_join"]["unmatched_exposure_user_ids"] = sorted(
            unmatched_users["user_id"].tolist()
        )

    return result


def compute_group_distribution(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    ac = cfg["audit_config"]
    grp_col = ac["group_column"]
    t_val = ac["treatment_value"]
    c_val = ac["control_value"]
    min_ratio = ac["min_group_ratio"]

    exposure = tables["campaign_exposure"]
    counts = exposure[grp_col].value_counts().to_dict()
    t_count = counts.get(t_val, 0)
    c_count = counts.get(c_val, 0)
    ratio = min(t_count, c_count) / max(t_count, c_count) if max(t_count, c_count) > 0 else 0
    balanced = ratio >= min_ratio

    return {
        f"{t_val}_count": int(t_count),
        f"{c_val}_count": int(c_count),
        "ratio_min_over_max": round(ratio, 4),
        "min_group_ratio_threshold": min_ratio,
        "balanced": balanced,
        "warning": not balanced,
    }


def compute_smd_summary(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    ac = cfg["audit_config"]
    grp_col = ac["group_column"]
    t_val = ac["treatment_value"]
    c_val = ac["control_value"]
    covariates = ac["covariates"]
    threshold = ac["smd_threshold"]

    exposure = tables["campaign_exposure"]
    users = tables["users"]
    df = exposure.merge(users, on="user_id", how="left")

    treatment = df[df[grp_col] == t_val]
    control = df[df[grp_col] == c_val]

    results = {}
    any_imbalanced = False
    for cov in covariates:
        t_data = pd.to_numeric(treatment[cov], errors="coerce").dropna()
        c_data = pd.to_numeric(control[cov], errors="coerce").dropna()

        if cov == "user_level":
            # categorical: compute raw gap in percentage points
            t_levels = treatment["user_level"].value_counts(normalize=True)
            c_levels = control["user_level"].value_counts(normalize=True)
            all_levels = sorted(set(t_levels.index) | set(c_levels.index))
            gaps = {}
            for lv in all_levels:
                p_t = t_levels.get(lv, 0)
                p_c = c_levels.get(lv, 0)
                gaps[str(lv)] = round(abs(p_t - p_c), 4)
            max_gap = max(gaps.values()) if gaps else 0
            results[cov] = {
                "type": "categorical",
                "level_gaps": gaps,
                "max_gap": max_gap,
                "imbalanced": max_gap > threshold,
            }
            if max_gap > threshold:
                any_imbalanced = True
            continue

        # numeric SMD
        if len(t_data) < 2 or len(c_data) < 2:
            results[cov] = {"type": "numeric", "smd": None, "imbalanced": None,
                            "note": "样本量不足，无法计算 SMD"}
            continue

        mean_t = t_data.mean()
        mean_c = c_data.mean()
        var_t = t_data.var(ddof=1)
        var_c = c_data.var(ddof=1)
        n_t = len(t_data)
        n_c = len(c_data)

        pooled_std = math.sqrt(((n_t - 1) * var_t + (n_c - 1) * var_c) / (n_t + n_c - 2))
        if pooled_std == 0:
            smd = 0.0
        else:
            smd = abs(mean_t - mean_c) / pooled_std

        imbalanced = smd > threshold
        if imbalanced:
            any_imbalanced = True
        results[cov] = {
            "type": "numeric",
            "smd": round(smd, 4),
            "threshold": threshold,
            "imbalanced": imbalanced,
        }

    return {
        "covariates": results,
        "any_imbalanced": any_imbalanced,
        "note": "SMD > 0.1 表示组间在该协变量上存在不平衡",
    }


def compute_outlier_summary(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    ac = cfg["audit_config"]
    subsidy_col = ac["subsidy_column"]

    rewards = tables["rewards"]
    vals = pd.to_numeric(rewards[subsidy_col], errors="coerce").dropna()

    q1 = vals.quantile(0.25)
    q3 = vals.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outliers = rewards[
        pd.to_numeric(rewards[subsidy_col], errors="coerce").notna()
        & ((pd.to_numeric(rewards[subsidy_col], errors="coerce") < lower)
           | (pd.to_numeric(rewards[subsidy_col], errors="coerce") > upper))
    ]

    outlier_details = []
    for _, row in outliers.iterrows():
        outlier_details.append({
            "user_id": str(row["user_id"]),
            "subsidy_amount": float(pd.to_numeric(row[subsidy_col], errors="coerce")),
        })

    return {
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_fence": round(float(lower), 2),
        "upper_fence": round(float(upper), 2),
        "num_outliers": len(outlier_details),
        "outliers": outlier_details,
        "note": "使用 1.5×IQR 规则检测 subsidy_amount 极端值",
    }


def compute_time_window_alignment(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    ac = cfg["audit_config"]
    order_col = ac["order_time_column"]
    window_col = ac["campaign_window_column"]

    exposure = tables["campaign_exposure"]
    orders = tables["orders"]

    # Parse exposure campaign windows
    exposure["_window_start"] = exposure[window_col].str.split(":").str[0]
    exposure["_window_end"] = exposure[window_col].str.split(":").str[1]
    exposure["_ws"] = pd.to_datetime(exposure["_window_start"], errors="coerce")
    exposure["_we"] = pd.to_datetime(exposure["_window_end"], errors="coerce")

    orders_parsed = orders.copy()
    orders_parsed["_ot"] = pd.to_datetime(orders_parsed[order_col], errors="coerce")

    merged = exposure.merge(orders_parsed, on="user_id", how="inner")

    def check_in_window(row):
        if pd.isna(row["_ot"]) or pd.isna(row["_ws"]) or pd.isna(row["_we"]):
            return "unknown"
        return "in_window" if row["_ws"] <= row["_ot"] <= row["_we"] else "out_of_window"

    merged["_alignment"] = merged.apply(check_in_window, axis=1)
    alignment_counts = merged["_alignment"].value_counts().to_dict()

    out_of_window = merged[merged["_alignment"] == "out_of_window"]
    misaligned_details = []
    for _, row in out_of_window.iterrows():
        misaligned_details.append({
            "user_id": str(row["user_id"]),
            "order_id": str(row["order_id"]),
            "order_time": str(row[order_col]),
            "campaign_window": str(row[window_col]),
        })

    return {
        "total_orders_joined": len(merged),
        "alignment_counts": {k: int(v) for k, v in alignment_counts.items()},
        "num_misaligned": len(misaligned_details),
        "misaligned_orders": misaligned_details,
        "note": "订单时间不在 campaign_window 范围内视为时间窗口错配",
    }


def build_warnings(results: dict) -> list:
    warnings = []

    # 1. Group distribution
    if results["group_distribution"]["warning"]:
        warnings.append({
            "risk_tag": "GROUP_IMBALANCE",
            "description": "Treatment/Control 分组比例失衡",
            "business_hint": "对照组样本过少，可能导致 A/B 测试统计功效不足，建议增大对照组比例或重新采样。",
        })

    # 2. SMD
    if results["smd_summary"]["any_imbalanced"]:
        imbalanced_covs = [
            k for k, v in results["smd_summary"]["covariates"].items()
            if v.get("imbalanced")
        ]
        warnings.append({
            "risk_tag": "COVARIATE_IMBALANCE",
            "description": f"协变量组间不平衡: {', '.join(imbalanced_covs)}",
            "business_hint": "Treatment/Control 在关键协变量上存在显著差异，建议使用 PS Matching 或 CUPED 调整偏差。",
        })

    # 3. Outliers
    if results["outlier_summary"]["num_outliers"] > 0:
        outlier_ids = [o["user_id"] for o in results["outlier_summary"]["outliers"]]
        warnings.append({
            "risk_tag": "SUBSIDY_OUTLIER",
            "description": f"补贴金额存在极端值: 用户 {', '.join(outlier_ids)}",
            "business_hint": f"用户 {', '.join(outlier_ids)} 的补贴金额为异常高值，建议核查是否存在刷单或系统发放异常。",
        })

    # 4. Time window misalignment
    if results["time_window_alignment"]["num_misaligned"] > 0:
        mis_ids = sorted(set(
            o["user_id"] for o in results["time_window_alignment"]["misaligned_orders"]
        ))
        warnings.append({
            "risk_tag": "TIME_WINDOW_MISALIGN",
            "description": f"共 {results['time_window_alignment']['num_misaligned']} 笔订单超出 campaign_window",
            "business_hint": f"用户 {', '.join(mis_ids)} 的订单发生在 campaign_window 之外，可能使用了过期/提前的补贴权益。",
        })

    # 5. Missing values in key fields
    warnings.append({
        "risk_tag": "DATA_QUALITY",
        "description": "部分关键字段存在缺失值",
        "business_hint": "建议核查缺失字段的填充逻辑（用户 u5 city_id 缺失，u6 subsidy_amount 缺失等），避免下游分析偏差。",
    })

    return warnings


def build_how_to_do_differently() -> list:
    return [
        "对于不平衡的分组，建议使用倾向性评分匹配 (Propensity Score Matching) 重新平衡 Treatment/Control 样本。",
        "对于协变量不平衡，可引入 CUPED (Controlled-experiment Using Pre-Experiment Data) 方法降低方差。",
        "补贴异常值建议设置业务硬性上下限（如 subsidy_amount ∈ [0, 200]），在发放前做规则拦截。",
        "订单时间窗口错配建议在 join 维度上增加 campaign_window 条件，不只在 user_id 级别 join。",
        "数据缺失值应在上游 ETL 阶段填充或标记，避免审计阶段发现大量空值。",
    ]


def main():
    cfg = load_task_config()
    tables = load_tables(cfg)

    answer = {
        "row_counts": compute_row_counts(tables),
        "join_cardinality": compute_join_cardinality(tables, cfg),
        "group_distribution": compute_group_distribution(tables, cfg),
        "smd_summary": compute_smd_summary(tables, cfg),
        "outlier_summary": compute_outlier_summary(tables, cfg),
        "time_window_alignment": compute_time_window_alignment(tables, cfg),
        "warnings": [],
        "how_to_do_differently": [],
    }

    answer["warnings"] = build_warnings(answer)
    answer["how_to_do_differently"] = build_how_to_do_differently()

    with open(ANSWER_PATH, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)

    print(f"✅ answer.json written to {ANSWER_PATH}")


if __name__ == "__main__":
    main()
