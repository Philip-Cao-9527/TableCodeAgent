"""solve.py — credit_risk_scoring_001 风险评分规则卡实现"""
import json
import math
from pathlib import Path

import pandas as pd

WORKSPACE = Path(__file__).resolve().parent
CSV_PATH = WORKSPACE / "applications.csv"
ANSWER_PATH = WORKSPACE / "answer.json"

# ── 读取数据 ──────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)
df_orig = df.copy()

# ── 1. row_counts ────────────────────────────────────────
row_counts = {
    "total_rows": len(df),
    "duplicate_rows": int(df.duplicated().sum()),
    "unique_applications": int(df["application_id"].nunique()),
}

# ── 2. field_summary ─────────────────────────────────────
field_summary = {}
for col in df.columns:
    info = {
        "dtype": str(df[col].dtype),
        "missing": int(df[col].isna().sum()),
        "missing_rate": round(float(df[col].isna().mean()), 4),
        "unique": int(df[col].nunique()),
    }
    if pd.api.types.is_numeric_dtype(df[col]):
        info["min"] = None if info["missing"] == len(df) else float(df[col].min())
        info["max"] = None if info["missing"] == len(df) else float(df[col].max())
        info["mean"] = None if info["missing"] == len(df) else round(float(df[col].mean()), 2)
    field_summary[col] = info

# ── 3. data_quality ──────────────────────────────────────
# duplicate_keys: check application_id uniqueness
dup_keys = df[df.duplicated(subset=["application_id"], keep=False)]
duplicate_keys = (
    [
        {"application_id": k, "count": int(c)}
        for k, c in df["application_id"].value_counts().items()
        if c > 1
    ]
    if dup_keys.empty
    else [
        {"application_id": str(row["application_id"]), "count": 2}
        for _, row in dup_keys.drop_duplicates(subset=["application_id"]).iterrows()
    ]
)
# Recalculate properly
dup_counts = df["application_id"].value_counts()
duplicate_keys = [
    {"application_id": k, "count": int(c)}
    for k, c in dup_counts.items()
    if c > 1
]

# invalid_age: age < 18 or age > 100
invalid_age_mask = df["age"].notna() & ((df["age"].astype(float) < 18) | (df["age"].astype(float) > 100))
invalid_age_count = int(invalid_age_mask.sum())

# leakage columns
leakage_columns_present = []
leakage_candidates = ["post_loan_collection_calls"]
for col in leakage_candidates:
    if col in df.columns:
        leakage_columns_present.append({
            "column": col,
            "reason": f"'{col}' 是贷后催收字段，在申请时不可知，不能用作贷前评分特征。"
        })

# missing value detail
missing_detail = {}
for col in df.columns:
    m = int(df[col].isna().sum())
    if m > 0:
        missing_detail[col] = {"missing_count": m, "missing_rate": round(m / len(df), 4)}

data_quality = {
    "duplicate_keys": duplicate_keys,
    "duplicate_key_count": len(duplicate_keys),
    "invalid_age_count": invalid_age_count,
    "invalid_age_examples": (
        df.loc[invalid_age_mask, ["application_id", "age"]].to_dict("records")
        if invalid_age_count > 0
        else []
    ),
    "missing_values": missing_detail,
    "leakage_columns_present": leakage_columns_present,
}

# ── 4. feature_processing ────────────────────────────────
feature_processing = {
    "numeric_features_used": [
        "loan_amount", "income", "age", "credit_score",
        "existing_debt", "employment_years"
    ],
    "categorical_features_used": ["region"],
    "excluded_features": [
        {
            "column": "default_90d",
            "reason": "目标变量，贷前不可知，不能用作评分特征。"
        },
        {
            "column": "post_loan_collection_calls",
            "reason": "贷后催收数据，在申请时不可知，泄漏字段。"
        }
    ],
    "processing_steps": [
        "1. 缺失年龄用中位数填充（规则卡推理时）；此处仅标记不填充。",
        "2. 构造 debt_to_income = existing_debt / max(income, 1)，避免除零。",
        "3. age < 18 标记为异常年龄，评分扣减。",
        "4. credit_score、employment_years 分段打分。",
        "5. region 按简单风险映射编码。",
    ],
}

# ── 5. scoring_result (规则卡, 不使用 default_90d / post_loan_collection_calls) ──
def score_application(row):
    """可解释规则卡：总分 0~10，越高风险越低。"""
    points = 0.0
    reasons = []

    # credit_score
    cs = row["credit_score"]
    if pd.notna(cs):
        cs = float(cs)
        if cs >= 700:
            points += 3
            reasons.append("credit_score>=700 (+3)")
        elif cs >= 650:
            points += 1
            reasons.append("credit_score 650-699 (+1)")
        else:
            reasons.append("credit_score<650 (+0)")

    # employment_years
    ey = row["employment_years"]
    if pd.notna(ey):
        ey = float(ey)
        if ey >= 3:
            points += 2
            reasons.append("employment_years>=3 (+2)")
        elif ey >= 1:
            points += 1
            reasons.append("employment_years 1-3 (+1)")
        else:
            reasons.append("employment_years<1 (+0)")

    # debt_to_income ratio
    inc = float(row["income"]) if pd.notna(row["income"]) else 0
    ed = float(row["existing_debt"]) if pd.notna(row["existing_debt"]) else 0
    dti = ed / max(inc, 1)
    if dti < 0.3:
        points += 2
        reasons.append(f"debt_to_income={dti:.2f}<0.3 (+2)")
    elif dti < 0.6:
        points += 1
        reasons.append(f"debt_to_income={dti:.2f} 0.3-0.6 (+1)")
    else:
        reasons.append(f"debt_to_income={dti:.2f}>=0.6 (+0)")

    # age
    age = row["age"]
    if pd.isna(age):
        reasons.append("age缺失 (+0)")
    else:
        age = float(age)
        if age < 18 or age > 100:
            points -= 1
            reasons.append(f"age={age} 异常 (-1)")
        elif 18 <= age <= 65:
            points += 1
            reasons.append(f"age={age} 正常 (+1)")
        else:
            reasons.append(f"age={age} (+0)")

    # region simple mapping
    region = str(row.get("region", ""))
    region_risk = {"North": 1, "South": 0, "East": 0, "West": 0}
    rp = region_risk.get(region, 0)
    points += rp
    if rp > 0:
        reasons.append(f"region={region} (+{rp})")
    else:
        reasons.append(f"region={region} (+0)")

    # loan_amount / income stability check
    if inc > 0 and float(row["loan_amount"]) > inc * 0.5:
        points -= 1
        reasons.append("loan_amount>50% income (-1)")

    return round(points, 1), reasons


scoring_details = []
for idx, row in df.iterrows():
    score, reasons = score_application(row)
    risk_level = "low" if score >= 5 else "medium" if score >= 3 else "high"
    scoring_details.append({
        "application_id": str(row["application_id"]),
        "score": score,
        "risk_level": risk_level,
        "max_possible_score": 10.0,
        "reasons": reasons,
    })

scoring_result = {
    "rule_card_name": "基础可解释规则卡 v1",
    "max_possible_score": 10.0,
    "risk_thresholds": {"low": ">=5", "medium": "3-4.9", "high": "<3"},
    "applications": scoring_details,
}

# ── 6. business_rule_checks ──────────────────────────────
business_rule_checks = []
# Rule 1: age < 18
underage = df["age"].notna() & (df["age"].astype(float) < 18)
if underage.any():
    for _, r in df[underage].iterrows():
        business_rule_checks.append({
            "rule": "年龄下限检查",
            "application_id": str(r["application_id"]),
            "status": "FAIL",
            "detail": f"年龄 {r['age']} 小于 18 岁，不符合信贷申请年龄要求。",
        })

# Rule 2: income = 0
zero_income = df["income"].notna() & (df["income"].astype(float) == 0)
if zero_income.any():
    for _, r in df[zero_income].iterrows():
        business_rule_checks.append({
            "rule": "收入有效检查",
            "application_id": str(r["application_id"]),
            "status": "FAIL",
            "detail": "收入为 0，无法评估还款能力。",
        })

# Rule 3: credit_score < 600
low_cs = df["credit_score"].notna() & (df["credit_score"].astype(float) < 600)
if low_cs.any():
    for _, r in df[low_cs].iterrows():
        business_rule_checks.append({
            "rule": "信用分下限检查",
            "application_id": str(r["application_id"]),
            "status": "FAIL",
            "detail": f"信用分 {r['credit_score']} 低于 600，风险较高。",
        })

# Rule 4: missing age
missing_age = df["age"].isna()
if missing_age.any():
    for _, r in df[missing_age].iterrows():
        business_rule_checks.append({
            "rule": "年龄缺失检查",
            "application_id": str(r["application_id"]),
            "status": "WARN",
            "detail": "年龄字段缺失，需要补充。",
        })

if not business_rule_checks:
    business_rule_checks.append({"rule": "全量检查", "status": "PASS", "detail": "所有业务规则通过。"})

# ── 7. explanations ──────────────────────────────────────
explanations = {
    "scoring_method": "使用可解释规则卡 (scorecard) 对每笔申请评分，避免使用黑盒模型。仅使用贷前已知特征。",
    "feature_engineering": [
        "debt_to_income = existing_debt / max(income, 1) 衡量负债水平。",
        "credit_score 按 >=700 / 650-699 / <650 三段加分。",
        "employment_years 按 >=3 / 1-3 / <1 三段加分。",
        "age < 18 或 > 100 视为异常并扣分。",
        "region 按地区风险简化为 0/1 编码。",
    ],
    "leakage_prevention": (
        "default_90d 是目标变量（贷后表现），post_loan_collection_calls 是贷后催收统计，"
        "两者在贷前均不可知，已从评分特征中排除。"
    ),
}

# ── 8. warnings ──────────────────────────────────────────
warnings = [
    f"发现 {data_quality['duplicate_key_count']} 个重复 application_id，需确认是否为录入错误。",
    f"发现 {invalid_age_count} 条异常年龄记录。",
    "发现贷后泄漏字段: post_loan_collection_calls，已在评分中排除。",
    f"发现 {len(missing_detail)} 个字段存在缺失值，建议补充完整。",
    "规则卡评分仅基于基础规则，未经过生产环境校准，不可直接用于放款决策。",
]

# ── 9. how_to_do_differently ─────────────────────────────
how_to_do_differently = [
    "使用更细粒度的 WOE 编码和逻辑回归构建标准评分卡。",
    "引入外部征信数据（如征信报告、多头借贷查询）增强特征。",
    "缺失值采用更稳健的插补策略（如模型预测填充）。",
    "对 region 等类别特征做 target encoding 或 frequency encoding。",
    "使用时间序列特征（如同一用户历史申请频率）。",
    "构建 A/B 测试框架验证规则卡在实际业务中的效果。",
]

# ── 10. validation ───────────────────────────────────────
validation = {
    "output_contract_keys_present": [
        "row_counts", "field_summary", "data_quality", "feature_processing",
        "scoring_result", "business_rule_checks", "explanations", "warnings",
        "how_to_do_differently", "validation"
    ],
    "score_excludes_leakage": True,
    "score_excludes_target": True,
}

# ── 写出 answer.json ─────────────────────────────────────
answer = {
    "row_counts": row_counts,
    "field_summary": field_summary,
    "data_quality": data_quality,
    "feature_processing": feature_processing,
    "scoring_result": scoring_result,
    "business_rule_checks": business_rule_checks,
    "explanations": explanations,
    "warnings": warnings,
    "how_to_do_differently": how_to_do_differently,
    "validation": validation,
}

ANSWER_PATH.write_text(
    json.dumps(answer, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"✅ answer.json written to {ANSWER_PATH}")
print(f"   Total applications: {row_counts['total_rows']}")
print(f"   Duplicate rows: {row_counts['duplicate_rows']}")
print(f"   Unique applications: {row_counts['unique_applications']}")
print(f"   Invalid age count: {invalid_age_count}")
print(f"   Scoring results: {len(scoring_details)} applications scored")
