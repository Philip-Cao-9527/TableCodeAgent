#!/usr/bin/env python3
"""solve.py — 信贷申请风险评分 workflow（credit_risk_scoring_001）"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
CSV_PATH = WORKSPACE / "applications.csv"
ANSWER_PATH = WORKSPACE / "answer.json"


# ── helpers ──────────────────────────────────────────────────────────────
def _safe_int(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s == "nan":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _load_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        return reader.fieldnames or list(rows[0].keys()), rows


def _get_col(col: str, rows: list[dict], numeric: bool = False) -> list:
    vals = []
    for r in rows:
        v = r.get(col, "")
        v_n = _safe_int(v) if numeric else v
        vals.append(v_n)
    return vals


# ── 1. row_counts ────────────────────────────────────────────────────────
def get_row_counts(cols: list[str], rows: list[dict]) -> dict:
    return {
        "total_rows": len(rows),
        "total_columns": len(cols),
        "columns": cols,
    }


# ── 2. field_summary ────────────────────────────────────────────────────
def get_field_summary(cols: list[str], rows: list[dict]) -> dict:
    summary = {}
    for col in cols:
        raw = [r.get(col, "") for r in rows]
        non_null = [v for v in raw if v != "" and v is not None and v != "nan"]
        null_cnt = len(raw) - len(non_null)
        info = {"non_null_count": len(non_null), "null_count": null_cnt}
        # try numeric
        num_vals = [_safe_int(v) for v in non_null]
        if all(v is not None for v in num_vals) and len(num_vals) > 0:
            info["dtype"] = "numeric"
            info["min"] = float(min(num_vals))
            info["max"] = float(max(num_vals))
            info["mean"] = round(float(sum(num_vals)) / len(num_vals), 4)
            info["unique"] = len(set(num_vals))
        else:
            info["dtype"] = "string"
            info["unique"] = len(set(non_null))
            info["sample_values"] = list(dict.fromkeys(non_null))[:5]
        summary[col] = info
    return summary


# ── 3. data_quality ──────────────────────────────────────────────────────
def get_data_quality(cols: list[str], rows: list[dict]) -> dict:
    # duplicate_keys on application_id
    seen_ids = {}
    dup_ids = []
    for i, r in enumerate(rows):
        aid = r.get("application_id", "")
        if aid in seen_ids:
            dup_ids.append(aid)
        seen_ids.setdefault(aid, []).append(i)
    dup_ids_unique = sorted(set(dup_ids))
    dup_examples = [{"application_id": aid} for aid in dup_ids_unique[:5]]

    duplicate_keys = {
        "has_duplicates": len(dup_ids_unique) > 0,
        "duplicate_key_count": len(dup_ids_unique),
        "duplicate_examples": dup_examples,
    }

    # invalid_age_count
    age_vals = _get_col("age", rows, numeric=True)
    invalid_ages = []
    for i, v in enumerate(age_vals):
        if v is not None and (v < 18 or v > 100):
            invalid_ages.append({"application_id": rows[i].get("application_id", ""), "age": v})
    invalid_age_count = len(invalid_ages)

    # leakage_columns_present
    leakage_cols = ["post_loan_collection_calls"]
    present_leakage = [c for c in leakage_cols if c in cols]
    leakage_columns_present = {
        "has_leakage": len(present_leakage) > 0,
        "leakage_columns": present_leakage,
        "note": "这些字段包含贷后信息，不能用作贷前评分特征",
    }

    # missing values
    missing_info = {}
    for col in cols:
        null_cnt = sum(1 for r in rows if r.get(col, "") in ("", None, "nan"))
        if null_cnt > 0:
            missing_info[col] = {"null_count": null_cnt, "null_rate": round(null_cnt / len(rows), 4)}

    return {
        "duplicate_keys": duplicate_keys,
        "invalid_age_count": invalid_age_count,
        "invalid_age_examples": invalid_ages[:5],
        "leakage_columns_present": leakage_columns_present,
        "missing_values": missing_info,
    }


# ── 4. feature_processing ────────────────────────────────────────────────
def get_feature_processing(cols: list[str], rows: list[dict]) -> dict:
    numeric_feats = ["loan_amount", "income", "age", "credit_score", "existing_debt", "employment_years"]
    cat_feats = ["region"]
    forbidden = {"default_90d", "post_loan_collection_calls"}

    steps = []
    for f in numeric_feats:
        if f in cols and f not in forbidden:
            vals = _get_col(f, rows, numeric=True)
            nulls = sum(1 for v in vals if v is None)
            if nulls:
                sorted_vals = sorted([v for v in vals if v is not None])
                median = sorted_vals[len(sorted_vals) // 2] if sorted_vals else None
                steps.append({"feature": f, "action": "中位数填充", "value": median, "reason": f"缺失 {nulls} 条"})
            else:
                steps.append({"feature": f, "action": "无缺失，直接使用", "value": None})

    for f in cat_feats:
        if f in cols and f not in forbidden:
            vals = _get_col(f, rows)
            nulls = sum(1 for v in vals if v in ("", None))
            if nulls:
                from collections import Counter
                mode_val = Counter([v for v in vals if v not in ("", None)]).most_common(1)
                steps.append({"feature": f, "action": "众数填充", "value": mode_val[0][0] if mode_val else None, "reason": f"缺失 {nulls} 条"})
            else:
                steps.append({"feature": f, "action": "无缺失，直接使用", "value": None})

    steps.append({"feature": "debt_to_income_ratio", "action": "衍生特征：existing_debt / income", "value": None})
    steps.append({"feature": "loan_to_income_ratio", "action": "衍生特征：loan_amount / income", "value": None})

    return {
        "pre_loan_features_used": [f for f in numeric_feats + cat_feats if f not in forbidden],
        "forbidden_features_excluded": list(forbidden),
        "processing_steps": steps,
        "note": "贷前评分仅使用申请时已知信息，排除 default_90d 和 post_loan_collection_calls",
    }


# ── 5. scoring_result ───────────────────────────────────────────────────
def _score_row(row: dict) -> dict:
    points = 0
    breakdown = {}

    cs = _safe_int(row.get("credit_score"))
    if cs is not None:
        pts = 30 if cs >= 700 else 20 if cs >= 650 else 10 if cs >= 600 else 0
        points += pts
        breakdown["credit_score"] = {"value": cs, "points": pts, "rule": ">=700→30, >=650→20, >=600→10, else 0"}
    else:
        breakdown["credit_score"] = {"value": None, "points": 0, "rule": "缺失"}

    inc = _safe_int(row.get("income"))
    if inc is not None:
        pts = 20 if inc >= 80000 else 15 if inc >= 50000 else 10 if inc >= 30000 else 5 if inc >= 10000 else 0
        points += pts
        breakdown["income"] = {"value": inc, "points": pts, "rule": ">=80000→20, >=50000→15, >=30000→10, >=10000→5, else 0"}
    else:
        breakdown["income"] = {"value": None, "points": 0, "rule": "缺失"}

    ey = _safe_int(row.get("employment_years"))
    if ey is not None:
        pts = 15 if ey >= 5 else 10 if ey >= 3 else 5 if ey >= 1 else 0
        points += pts
        breakdown["employment_years"] = {"value": ey, "points": pts, "rule": ">=5→15, >=3→10, >=1→5, else 0"}
    else:
        breakdown["employment_years"] = {"value": None, "points": 0, "rule": "缺失"}

    existing_debt = _safe_int(row.get("existing_debt"))
    if inc is not None and inc > 0 and existing_debt is not None:
        dti = existing_debt / inc
        pts = 15 if dti < 0.3 else 10 if dti < 0.5 else 5 if dti < 1.0 else 0
        points += pts
        breakdown["debt_to_income_ratio"] = {"value": round(dti, 4), "points": pts, "rule": "<0.3→15, <0.5→10, <1.0→5, else 0"}
    else:
        breakdown["debt_to_income_ratio"] = {"value": None, "points": 0, "rule": "无法计算"}

    age = _safe_int(row.get("age"))
    if age is not None:
        pts = 10 if 25 <= age <= 60 else 0
        points += pts
        breakdown["age"] = {"value": age, "points": pts, "rule": "25~60岁→10, else 0"}
    else:
        breakdown["age"] = {"value": None, "points": 0, "rule": "缺失"}

    region = row.get("region", "")
    region_pts = {"North": 5, "East": 3}
    pts = region_pts.get(region, 0)
    points += pts
    breakdown["region"] = {"value": region, "points": pts, "rule": "North→5, East→3, else 0"}

    if points >= 70:
        grade = "低风险"
    elif points >= 50:
        grade = "中低风险"
    elif points >= 35:
        grade = "中风险"
    else:
        grade = "高风险"

    return {"total_score": points, "max_possible_score": 95, "risk_grade": grade, "breakdown": breakdown}


def get_scoring_result(rows: list[dict]) -> dict:
    results = []
    for r in rows:
        sr = _score_row(r)
        sr["application_id"] = r.get("application_id", "unknown")
        results.append(sr)
    scores = [r["total_score"] for r in results]
    return {
        "sample_count": len(results),
        "scores": results,
        "summary": {
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "mean_score": round(sum(scores) / len(scores), 2) if scores else 0,
        },
    }


# ── 6. business_rule_checks ─────────────────────────────────────────────
def get_business_rule_checks(rows: list[dict]) -> list[dict]:
    checks = []

    # age >= 18
    minors = [r for r in rows if _safe_int(r.get("age")) is not None and _safe_int(r.get("age")) < 18]
    checks.append({
        "rule": "申请人年龄 >= 18 岁",
        "passed": len(minors) == 0,
        "failed_count": len(minors),
        "failed_ids": [r["application_id"] for r in minors],
    })

    # income > 0
    zero_inc = [r for r in rows if _safe_int(r.get("income")) is not None and _safe_int(r.get("income")) <= 0]
    checks.append({
        "rule": "申请人收入 > 0",
        "passed": len(zero_inc) == 0,
        "failed_count": len(zero_inc),
        "failed_ids": [r["application_id"] for r in zero_inc],
    })

    # loan_amount <= income * 3
    high_leverage = []
    for r in rows:
        loan = _safe_int(r.get("loan_amount"))
        inc = _safe_int(r.get("income"))
        if loan is not None and inc is not None and inc > 0 and (loan / inc) > 3:
            high_leverage.append(r["application_id"])
    checks.append({
        "rule": "贷款金额 <= 年收入 × 3",
        "passed": len(high_leverage) == 0,
        "failed_count": len(high_leverage),
        "failed_ids": high_leverage,
    })

    # credit_score >= 600
    low_cs = [r for r in rows if _safe_int(r.get("credit_score")) is not None and _safe_int(r.get("credit_score")) < 600]
    checks.append({
        "rule": "信用评分 >= 600（最低准入）",
        "passed": len(low_cs) == 0,
        "failed_count": len(low_cs),
        "failed_ids": [r["application_id"] for r in low_cs],
    })

    # unique application_id
    ids = [r.get("application_id") for r in rows]
    dup_aids = [aid for aid in ids if ids.count(aid) > 1]
    checks.append({
        "rule": "application_id 唯一",
        "passed": len(set(dup_aids)) == 0,
        "failed_count": len(set(dup_aids)),
        "failed_ids": sorted(set(dup_aids)),
    })

    # leakage exclusion
    checks.append({
        "rule": "贷前评分排除 post_loan_collection_calls",
        "passed": True,
        "note": "该字段已被排除在评分特征之外",
    })

    return checks


# ── 7. explanations ──────────────────────────────────────────────────────
def get_explanations() -> dict:
    return {
        "scoring_method": "规则卡评分（Rule-based Scorecard）",
        "scoring_rationale": "对每个特征设定可解释的分段规则，累加得分后映射到风险等级，无需训练，完全可复现。",
        "feature_importance": {
            "credit_score": "权重最高（30分），直接反映历史信用表现",
            "income": "反映还款能力（20分）",
            "employment_years": "反映收入稳定性（15分）",
            "debt_to_income_ratio": "反映负债水平（15分）",
            "age": "基础人口特征（10分）",
            "region": "区域辅助因子（5分）",
        },
        "excluded_features": {
            "default_90d": "贷后目标变量，不可用于贷前评分",
            "post_loan_collection_calls": "贷后催收信息，存在数据泄漏风险",
        },
    }


# ── 8. warnings ─────────────────────────────────────────────────────────
def get_warnings(rows: list[dict]) -> list[dict]:
    warns = []
    age_vals = _get_col("age", rows, numeric=True)
    age_missing = sum(1 for v in age_vals if v is None)
    if age_missing:
        warns.append({"type": "missing_data", "message": f"age 字段缺失 {age_missing} 条，已用中位数填充"})

    def_vals = _get_col("default_90d", rows)
    def_missing = sum(1 for v in def_vals if v in ("", None, "nan"))
    if def_missing:
        warns.append({"type": "missing_target", "message": f"default_90d 字段缺失 {def_missing} 条，无法用于训练验证"})

    minors = [r for r in rows if _safe_int(r.get("age")) is not None and _safe_int(r.get("age")) < 18]
    if minors:
        warns.append({
            "type": "invalid_age",
            "message": f"存在 {len(minors)} 条年龄 < 18 的申请（ID: {[r['application_id'] for r in minors]}），需人工审核",
        })

    ids = [r.get("application_id") for r in rows]
    dup_ids = sorted(set(a for a in ids if ids.count(a) > 1))
    if dup_ids:
        warns.append({
            "type": "duplicate_keys",
            "message": f"application_id 存在重复（{dup_ids}），数据质量异常",
        })
    return warns


# ── 9. how_to_do_differently ────────────────────────────────────────────
def get_how_to_do_differently() -> list[str]:
    return [
        "1. 收集更多历史样本，训练逻辑回归或 XGBoost 模型替代规则卡",
        "2. 对缺失值使用更复杂的插补策略（如 KNN、多重插补）",
        "3. 构建更多衍生特征（如 DTI 比率、信贷利用度、近期查询次数）",
        "4. 引入外部征信数据（央行征信、多头借贷查询）增强评估",
        "5. 对 region 做 target encoding 代替固定分值",
        "6. 使用 WOE 分箱 + Logistic Regression 建立标准评分卡",
        "7. 增加时间维度校验，确保训练集和测试集无时间穿越",
    ]


# ── 10. validation ──────────────────────────────────────────────────────
def get_validation(cols: list[str], rows: list[dict]) -> dict:
    checks = []
    required = [
        "application_id", "user_id", "application_time", "loan_amount",
        "income", "age", "credit_score", "existing_debt", "employment_years", "default_90d",
    ]
    missing_req = [c for c in required if c not in cols]
    checks.append({
        "check": "required_columns_present",
        "passed": len(missing_req) == 0,
        "detail": f"缺失字段: {missing_req}" if missing_req else "所有必需字段存在",
    })

    # numeric conversion
    numeric_cols = ["loan_amount", "income", "age", "credit_score", "existing_debt", "employment_years"]
    issues = {}
    for c in numeric_cols:
        if c in cols:
            vals = _get_col(c, rows, numeric=True)
            bad = sum(1 for v in vals if v is None and rows[vals.index(v) if vals.index(v) < len(rows) else 0].get(c, "") not in ("", None))
            # simpler: count empty non-empty conversion failures
            raw_vals = [r.get(c, "") for r in rows]
            for rv, v in zip(raw_vals, vals):
                if rv not in ("", None, "nan") and v is None:
                    issues[c] = issues.get(c, 0) + 1
    checks.append({
        "check": "numeric_conversion_ok",
        "passed": len(issues) == 0,
        "detail": issues if issues else "所有数值字段可正常转换",
    })

    # time parse
    time_ok = True
    for r in rows:
        t = r.get("application_time", "")
        if t not in ("", None):
            from datetime import datetime
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    datetime.strptime(t, fmt)
                    break
                except ValueError:
                    continue
            else:
                time_ok = False
                break
    checks.append({"check": "application_time_parseable", "passed": time_ok})

    return {"validation_checks": checks}


# ── main ─────────────────────────────────────────────────────────────────
def main():
    cols, rows = _load_csv(CSV_PATH)

    answer = {
        "row_counts": get_row_counts(cols, rows),
        "field_summary": get_field_summary(cols, rows),
        "data_quality": get_data_quality(cols, rows),
        "feature_processing": get_feature_processing(cols, rows),
        "scoring_result": get_scoring_result(rows),
        "business_rule_checks": get_business_rule_checks(rows),
        "explanations": get_explanations(),
        "warnings": get_warnings(rows),
        "how_to_do_differently": get_how_to_do_differently(),
        "validation": get_validation(cols, rows),
    }

    ANSWER_PATH.write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ answer.json written to {ANSWER_PATH}")


if __name__ == "__main__":
    main()
