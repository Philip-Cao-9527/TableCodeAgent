#!/usr/bin/env python
# solve.py — growth_campaign_audit_001
# 对营销活动样本构造进行数据审计

import json
import math
import sys
from pathlib import Path

# ── workspace root ──
WORKSPACE = Path(__file__).resolve().parent

# ── try to use project helper, fallback to pure pandas ──
_HAS_HELPER = False
try:
    # 将项目根加入 sys.path 以便 import
    _proj_root = WORKSPACE.parents[5]  # 回溯到 TableCodeAgent/
    if str(_proj_root) not in sys.path:
        sys.path.insert(0, str(_proj_root))
    from tablecodeagent.workflows.growth_campaign_audit import build_growth_campaign_audit_report  # noqa
    _HAS_HELPER = True
except ImportError:
    _HAS_HELPER = False


def _parse_window(win_str):
    """Parse 'YYYY-MM-DD:YYYY-MM-DD' into (start, end) date strings."""
    parts = win_str.split(":")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None


def _calculate_smd(series_t, series_c):
    """Calculate standardized mean difference between two numeric series."""
    mt = series_t.mean()
    mc = series_c.mean()
    vt = series_t.var(ddof=1)
    vc = series_c.var(ddof=1)
    nt = len(series_t)
    nc = len(series_c)
    pooled_std = math.sqrt(((nt - 1) * vt + (nc - 1) * vc) / (nt + nc - 2))
    if pooled_std == 0 or math.isnan(pooled_std):
        return 0.0
    return abs(mt - mc) / pooled_std


def _categorical_balance_gap(series_t, series_c, col_name):
    """Calculate balance gap for categorical variable: max difference in proportion."""
    t_counts = series_t.value_counts(normalize=True)
    c_counts = series_c.value_counts(normalize=True)
    all_cats = set(t_counts.index) | set(c_counts.index)
    max_gap = max(abs(t_counts.get(c, 0) - c_counts.get(c, 0)) for c in all_cats)
    return round(max_gap, 4)


def compute_audit_report(workspace: Path) -> dict:
    """Core audit logic using pandas."""
    import pandas as pd

    # ── read tables ──
    users = pd.read_csv(workspace / "users.csv")
    exposure = pd.read_csv(workspace / "campaign_exposure.csv")
    rewards = pd.read_csv(workspace / "rewards.csv")
    orders = pd.read_csv(workspace / "orders.csv")

    cfg = {
        "duplicate_key_columns": ["user_id", "campaign_window"],
        "join_keys": ["user_id", "campaign_id", "campaign_window"],
        "group_column": "treatment_group",
        "treatment_value": "treatment",
        "control_value": "control",
        "min_group_ratio": 0.5,
        "covariates": ["historical_orders_30d", "historical_gmv_30d", "active_days_30d", "user_level"],
        "smd_threshold": 0.1,
        "subsidy_column": "subsidy_amount",
        "order_time_column": "order_time",
        "campaign_window_column": "campaign_window",
    }

    warnings = []

    # ── 1. row_counts ──
    row_counts = {
        "users": int(len(users)),
        "campaign_exposure": int(len(exposure)),
        "rewards": int(len(rewards)),
        "orders": int(len(orders)),
    }

    # ── 2. join_cardinality ──
    # 检查 campaign_exposure + rewards 按 join_keys 关联后的行数膨胀
    join_keys = cfg["join_keys"]
    exp_rew = exposure.merge(rewards, on=join_keys, how="left", suffixes=("_exp", "_rew"))
    join_cardinality = {
        "exposure_rows": int(len(exposure)),
        "rewards_rows": int(len(rewards)),
        "left_join_rows": int(len(exp_rew)),
        "expansion_factor": round(len(exp_rew) / max(len(exposure), 1), 4),
    }
    if join_cardinality["expansion_factor"] > 1.5:
        warnings.append({
            "tag": "join_cardinality_inflation",
            "message": f"左表关联后行数膨胀 {join_cardinality['expansion_factor']}x，"
                       f"可能因 rewards 多行匹配同一 exposure 记录。"
        })

    # ── 3. group_distribution ──
    group_col = cfg["group_column"]
    treatment_val = cfg["treatment_value"]
    control_val = cfg["control_value"]
    group_counts = exposure[group_col].value_counts().to_dict()
    group_distribution = {str(k): int(v) for k, v in group_counts.items()}
    n_t = group_counts.get(treatment_val, 0)
    n_c = group_counts.get(control_val, 0)
    ratio = n_t / max(n_c, 1)
    group_distribution["ratio_treatment_over_control"] = round(ratio, 4)
    if n_c == 0:
        warnings.append({
            "tag": "missing_control_group",
            "message": "对照组用户数为 0，无法进行有效的组间比较。"
        })
    elif ratio > (1 / cfg["min_group_ratio"]) or ratio < cfg["min_group_ratio"]:
        warnings.append({
            "tag": "group_imbalance",
            "message": f"Treatment/Control 比例 {ratio:.2f} 超出阈值 [{cfg['min_group_ratio']}, {1 / cfg['min_group_ratio']}]，"
                       f"可能导致统计功效下降。"
        })

    # ── 4. smd_summary ──
    covariate_cols = cfg["covariates"]
    # 将 exposure 与 users 关联以获取协变量
    exp_users = exposure.merge(users, on="user_id", how="left")
    treat_df = exp_users[exp_users[group_col] == treatment_val]
    control_df = exp_users[exp_users[group_col] == control_val]

    smd_results = {}
    for cov in covariate_cols:
        if cov not in exp_users.columns:
            continue
        if pd.api.types.is_numeric_dtype(exp_users[cov]):
            t_vals = treat_df[cov].dropna().astype(float)
            c_vals = control_df[cov].dropna().astype(float)
            if len(t_vals) > 0 and len(c_vals) > 0:
                smd = round(_calculate_smd(t_vals, c_vals), 4)
            else:
                smd = None
            smd_results[cov] = {
                "type": "numeric",
                "smd": smd,
                "treatment_mean": round(float(t_vals.mean()), 2) if len(t_vals) > 0 else None,
                "control_mean": round(float(c_vals.mean()), 2) if len(c_vals) > 0 else None,
            }
        else:
            # categorical variable
            t_cats = treat_df[cov].dropna()
            c_cats = control_df[cov].dropna()
            gap = _categorical_balance_gap(t_cats, c_cats, cov) if len(t_cats) > 0 and len(c_cats) > 0 else None
            smd_results[cov] = {
                "type": "categorical",
                "balance_gap": gap,
                "treatment_distribution": t_cats.value_counts().to_dict() if len(t_cats) > 0 else {},
                "control_distribution": c_cats.value_counts().to_dict() if len(c_cats) > 0 else {},
            }

    smd_summary = {
        "threshold": cfg["smd_threshold"],
        "variables": smd_results,
    }
    # 检查哪些变量不平衡
    imbalanced_vars = []
    for cov, info in smd_results.items():
        if info["type"] == "numeric" and info["smd"] is not None and info["smd"] > cfg["smd_threshold"]:
            imbalanced_vars.append(cov)
        elif info["type"] == "categorical" and info["balance_gap"] is not None and info["balance_gap"] > cfg["smd_threshold"]:
            imbalanced_vars.append(cov)
    if imbalanced_vars:
        warnings.append({
            "tag": "covariate_imbalance",
            "message": f"以下协变量在 treatment/control 组间不平衡（SMD>{cfg['smd_threshold']}）：{', '.join(imbalanced_vars)}。"
                       f"建议使用 CUPED 或分层采样进行调整。"
        })

    # ── 5. outlier_summary ──
    subsidy_col = cfg["subsidy_column"]
    rew = rewards.copy()
    rew[subsidy_col] = pd.to_numeric(rew[subsidy_col], errors="coerce")

    q1 = rew[subsidy_col].quantile(0.25)
    q3 = rew[subsidy_col].quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    outliers = rew[(rew[subsidy_col] < lower_bound) | (rew[subsidy_col] > upper_bound)]
    outlier_summary = {
        "subsidy_column": subsidy_col,
        "total_rewards": int(len(rew)),
        "outlier_count": int(len(outliers)),
        "outlier_rate": round(len(outliers) / max(len(rew), 1), 4),
        "q1": round(float(q1), 2) if not math.isnan(q1) else None,
        "q3": round(float(q3), 2) if not math.isnan(q3) else None,
        "iqr": round(float(iqr), 2) if not math.isnan(iqr) else None,
        "lower_bound": round(float(lower_bound), 2) if not math.isnan(lower_bound) else None,
        "upper_bound": round(float(upper_bound), 2) if not math.isnan(upper_bound) else None,
        "outlier_examples": outliers.to_dict(orient="records") if len(outliers) > 0 else [],
    }
    if len(outliers) > 0:
        warnings.append({
            "tag": "subsidy_outliers",
            "message": f"补贴金额检测到 {len(outliers)} 个异常值（IQR 法），最大值为 {float(outliers[subsidy_col].max())}。"
                       f"建议人工复核异常补贴记录。"
        })

    # ── 6. time_window_alignment ──
    # 检查 orders 的 order_time 是否在 exposure 的 campaign_window 范围内
    order_col = cfg["order_time_column"]
    window_col = cfg["campaign_window_column"]

    # 解析 campaign_window -> start/end
    exp_windows = exposure[[window_col]].drop_duplicates()
    window_map = {}
    for _, row in exp_windows.iterrows():
        s, e = _parse_window(str(row[window_col]))
        if s and e:
            window_map[row[window_col]] = (s, e)

    orders_merged = orders.merge(exposure[["user_id", window_col]].drop_duplicates(), on="user_id", how="left")
    misaligned = []
    aligned_count = 0
    total_checked = 0
    for _, row in orders_merged.iterrows():
        total_checked += 1
        win_str = row.get(window_col)
        if pd.isna(win_str) or win_str not in window_map:
            misaligned.append({
                "user_id": row["user_id"],
                "order_id": row.get("order_id"),
                "order_time": str(row[order_col]),
                "reason": "无法匹配 campaign_window"
            })
            continue
        win_start, win_end = window_map[win_str]
        ot = str(row[order_col])
        if ot < win_start or ot > win_end:
            misaligned.append({
                "user_id": row["user_id"],
                "order_id": row.get("order_id"),
                "order_time": ot,
                "campaign_window": win_str,
                "reason": f"order_time {ot} 不在窗口 [{win_start}, {win_end}] 内"
            })
        else:
            aligned_count += 1

    time_window_alignment = {
        "total_orders_checked": total_checked,
        "aligned_in_window": aligned_count,
        "misaligned_count": len(misaligned),
        "misaligned_examples": misaligned[:10] if misaligned else [],
    }
    if len(misaligned) > 0:
        warnings.append({
            "tag": "time_window_mismatch",
            "message": f"检测到 {len(misaligned)} 笔订单的 order_time 不在对应的 campaign_window 内。"
                       f"这些订单可能不应计入对应营销活动的转化效果。"
        })

    # ── 7. how_to_do_differently ──
    how_to_do_differently = [
        "使用 CUPED 或分层采样修复 treatment/control 组间协变量不平衡问题。",
        "对异常补贴记录进行人工审核或 Winsorize 处理。",
        "核实 campaign_window 范围是否准确，确保 order_time 在窗口内的订单才计入转化。",
        "增加样本量或使用 PS matching 改善组间可比性。",
    ]

    return {
        "row_counts": row_counts,
        "join_cardinality": join_cardinality,
        "group_distribution": group_distribution,
        "smd_summary": smd_summary,
        "outlier_summary": outlier_summary,
        "time_window_alignment": time_window_alignment,
        "warnings": warnings,
        "how_to_do_differently": how_to_do_differently,
    }


def main():
    """Entry point: write answer.json to workspace."""
    if _HAS_HELPER:
        report = build_growth_campaign_audit_report(WORKSPACE)
    else:
        report = compute_audit_report(WORKSPACE)

    out_path = WORKSPACE / "answer.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"✅ answer.json written to {out_path}")


if __name__ == "__main__":
    main()
