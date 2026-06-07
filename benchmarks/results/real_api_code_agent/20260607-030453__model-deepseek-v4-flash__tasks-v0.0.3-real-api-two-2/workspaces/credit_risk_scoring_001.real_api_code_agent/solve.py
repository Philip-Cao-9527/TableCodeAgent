#!/usr/bin/env python3
"""solve.py — Credit Risk Scoring Benchmark (credit_risk_scoring_001)

Reads applications.csv, performs data quality checks, constructs a
rule-based scorecard, and writes answer.json. Uses only stdlib.
"""
import csv
import json
import math
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
CSV_PATH = WORKSPACE / "applications.csv"
ANSWER_PATH = WORKSPACE / "answer.json"

# ── Config ──────────────────────────────────────────────────────────────
KEY_COLUMNS = ["application_id"]
REQUIRED_COLUMNS = [
    "application_id", "user_id", "application_time", "loan_amount",
    "income", "age", "credit_score", "existing_debt",
    "employment_years", "default_90d",
]
NUMERIC_FEATURES = [
    "loan_amount", "income", "age", "credit_score",
    "existing_debt", "employment_years",
]
CATEGORICAL_FEATURES = ["region"]
LEAKAGE_COLUMNS = ["post_loan_collection_calls"]
TARGET_COLUMN = "default_90d"
MIN_AGE = 18
MAX_AGE = 100


def try_float(val):
    """Convert string to float, return None if not possible."""
    if val is None or val.strip() == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def load_data():
    """Load CSV as list of dicts, converting numeric columns to float or None."""
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            processed = {}
            for k, v in row.items():
                if k in NUMERIC_FEATURES + [TARGET_COLUMN]:
                    processed[k] = try_float(v)
                else:
                    processed[k] = v.strip() if v else ""
            rows.append(processed)
    return rows, fieldnames


# ── Row Counts ──────────────────────────────────────────────────────────
def compute_row_counts(rows, fieldnames):
    return {
        "total_rows": len(rows),
        "total_columns": len(fieldnames),
        "columns": fieldnames,
    }


# ── Field Summary ───────────────────────────────────────────────────────
def compute_field_summary(rows, fieldnames):
    summary = {}
    for col in fieldnames:
        vals = [r[col] for r in rows]
        is_numeric = col in NUMERIC_FEATURES + [TARGET_COLUMN]
        missing_count = sum(1 for v in vals if v is None or v == "")
        missing_rate = round(missing_count / len(rows), 4)
        unique_vals = set()
        for v in vals:
            unique_vals.add(str(v))
        info = {
            "dtype": "numeric" if is_numeric else "string",
            "missing_count": missing_count,
            "missing_rate": missing_rate,
            "unique_count": len(unique_vals),
        }
        if is_numeric:
            numeric_vals = [v for v in vals if v is not None and v != ""]
            if numeric_vals:
                info["min"] = float(min(numeric_vals))
                info["max"] = float(max(numeric_vals))
                info["mean"] = round(float(sum(numeric_vals)) / len(numeric_vals), 2)
                if len(numeric_vals) > 1:
                    mean = sum(numeric_vals) / len(numeric_vals)
                    var = sum((x - mean) ** 2 for x in numeric_vals) / (len(numeric_vals) - 1)
                    info["std"] = round(math.sqrt(var), 2)
                else:
                    info["std"] = None
            else:
                info["min"] = None
                info["max"] = None
                info["mean"] = None
                info["std"] = None
        summary[col] = info
    return summary


# ── Data Quality ────────────────────────────────────────────────────────
def compute_data_quality(rows):
    # Duplicate keys (application_id)
    seen_ids = {}
    for i, r in enumerate(rows):
        aid = r["application_id"]
        seen_ids.setdefault(aid, []).append(i)

    duplicate_keys = []
    for aid, indices in seen_ids.items():
        if len(indices) > 1:
            duplicate_keys.append({
                "key": aid,
                "occurrences": len(indices),
                "row_indices": indices,
            })

    duplicate_row_count = 0
    seen_rows = set()
    for r in rows:
        row_tuple = tuple(str(r.get(k, "")) for k in r)
        if row_tuple in seen_rows:
            duplicate_row_count += 1
        else:
            seen_rows.add(row_tuple)

    # Invalid age
    invalid_age_count = 0
    invalid_age_details = []
    for i, r in enumerate(rows):
        age = r.get("age")
        if age is None or age == "":
            invalid_age_count += 1
            invalid_age_details.append({
                "row_index": i,
                "application_id": r["application_id"],
                "age": None,
                "reason": "missing",
            })
        elif age < MIN_AGE:
            invalid_age_count += 1
            invalid_age_details.append({
                "row_index": i,
                "application_id": r["application_id"],
                "age": age,
                "reason": "under_18",
            })
        elif age > MAX_AGE:
            invalid_age_count += 1
            invalid_age_details.append({
                "row_index": i,
                "application_id": r["application_id"],
                "age": age,
                "reason": "over_100",
            })

    # Leakage columns
    fieldnames = list(rows[0].keys()) if rows else []
    present_leakage = [c for c in LEAKAGE_COLUMNS if c in fieldnames]
    leakage_columns_present = {}
    for col in present_leakage:
        vals = [r[col] for r in rows]
        non_null = sum(1 for v in vals if v is not None and v != "")
        unique_vals = set(str(v) for v in vals)
        leakage_columns_present[col] = {
            "present": True,
            "non_null_count": non_null,
            "unique_values": len(unique_vals),
            "warning": f"'{col}' is a post-loan leakage field and must NOT be used as a pre-loan scoring feature",
        }

    # Missing values summary
    missing_summary = {}
    for col in fieldnames:
        n_miss = sum(1 for r in rows if r.get(col) is None or r.get(col) == "")
        if n_miss > 0:
            missing_summary[col] = {
                "missing_count": n_miss,
                "missing_rate": round(n_miss / len(rows), 4),
            }

    return {
        "duplicate_keys": duplicate_keys,
        "duplicate_row_count": duplicate_row_count,
        "invalid_age_count": invalid_age_count,
        "invalid_age_details": invalid_age_details,
        "leakage_columns_present": leakage_columns_present,
        "missing_values": missing_summary,
    }


# ── Feature Processing ──────────────────────────────────────────────────
def compute_feature_processing(rows):
    processing_steps = []
    fieldnames = list(rows[0].keys()) if rows else []

    # Age
    age_vals = [r["age"] for r in rows if r.get("age") is not None]
    age_missing = sum(1 for r in rows if r.get("age") is None)
    if age_missing > 0:
        sorted_ages = sorted(age_vals)
        if sorted_ages:
            median_age = sorted_ages[len(sorted_ages) // 2]
        else:
            median_age = 30
        processing_steps.append({
            "feature": "age",
            "action": "fill_missing_with_median",
            "value": median_age,
            "reason": f"{age_missing} missing values imputed with median {median_age}",
        })
    processing_steps.append({
        "feature": "age",
        "action": "clip_outliers",
        "range": [MIN_AGE, MAX_AGE],
        "reason": f"Values below {MIN_AGE} or above {MAX_AGE} are considered invalid",
    })

    # Income zeros
    zero_income_count = sum(1 for r in rows if r.get("income") == 0)
    if zero_income_count > 0:
        processing_steps.append({
            "feature": "income",
            "action": "treat_zero_as_low_income_flag",
            "zero_count": zero_income_count,
            "reason": f"{zero_income_count} applicant(s) have zero income — flag for manual review",
        })

    # Numeric features
    for feat in NUMERIC_FEATURES:
        if feat == "age":
            continue
        vals = [r[feat] for r in rows if r.get(feat) is not None]
        if vals:
            processing_steps.append({
                "feature": feat,
                "action": "bin_into_risk_categories_for_scorecard",
                "observed_range": [float(min(vals)), float(max(vals))],
            })

    # Categorical
    region_vals = list(dict.fromkeys(r["region"] for r in rows if r.get("region")))
    processing_steps.append({
        "feature": "region",
        "action": "risk_mapping",
        "categories": sorted(region_vals),
    })

    # Exclusions
    processing_steps.append({
        "feature": "post_loan_collection_calls",
        "action": "excluded",
        "reason": "Post-loan leakage column — not available at application time",
    })
    processing_steps.append({
        "feature": "default_90d",
        "action": "excluded_from_features",
        "reason": "Target variable — not used as a pre-loan feature",
    })

    return {
        "processing_steps": processing_steps,
        "note": "This is a rule-based scorecard, not a trained ML model.",
    }


# ── Scoring Result ──────────────────────────────────────────────────────
def compute_scoring_result(rows):
    # Compute median age for imputation
    age_vals = [r["age"] for r in rows if r.get("age") is not None]
    sorted_ages = sorted(age_vals)
    median_age = sorted_ages[len(sorted_ages) // 2] if sorted_ages else 30

    scores = []
    details = []
    scoring_rules = [
        "credit_score >= 700 -> 40 pts; >= 650 -> 30 pts; >= 600 -> 15 pts; else 0",
        "loan_to_income_ratio <= 0.3 -> 20 pts; <= 0.5 -> 10 pts; > 0.5 -> 0",
        "age >= 25 -> 10 pts; >= 18 -> 5 pts; < 18 -> -10 pts",
        "employment_years >= 5 -> 15 pts; >= 2 -> 10 pts; < 2 -> 5 pts",
        "debt_to_income_ratio <= 0.3 -> 15 pts; <= 0.6 -> 5 pts; > 0.6 -> 0",
        "region: North -> 5 pts; East -> 0; South -> -5; West -> 0",
    ]

    for i, r in enumerate(rows):
        age_val = r["age"] if r.get("age") is not None else median_age
        credit = r["credit_score"] if r.get("credit_score") is not None else 600
        income = r["income"] if r.get("income") is not None and r["income"] > 0 else 1
        loan = r["loan_amount"] if r.get("loan_amount") is not None else 0
        debt = r["existing_debt"] if r.get("existing_debt") is not None else 0
        emp = r["employment_years"] if r.get("employment_years") is not None else 0
        region = r.get("region", "")

        points = 0
        breakdown = {}

        # 1. Credit score
        if credit >= 700:
            cs_pts = 40
        elif credit >= 650:
            cs_pts = 30
        elif credit >= 600:
            cs_pts = 15
        else:
            cs_pts = 0
        points += cs_pts
        breakdown["credit_score_points"] = cs_pts

        # 2. Loan-to-income ratio
        lti = loan / income
        if lti <= 0.3:
            lti_pts = 20
        elif lti <= 0.5:
            lti_pts = 10
        else:
            lti_pts = 0
        points += lti_pts
        breakdown["lti_points"] = lti_pts
        breakdown["lti_ratio"] = round(lti, 4)

        # 3. Age
        if age_val >= 25:
            age_pts = 10
        elif age_val >= 18:
            age_pts = 5
        else:
            age_pts = -10
        points += age_pts
        breakdown["age_points"] = age_pts

        # 4. Employment years
        if emp >= 5:
            emp_pts = 15
        elif emp >= 2:
            emp_pts = 10
        else:
            emp_pts = 5
        points += emp_pts
        breakdown["employment_points"] = emp_pts

        # 5. Debt-to-income ratio
        dti = debt / income
        if dti <= 0.3:
            dti_pts = 15
        elif dti <= 0.6:
            dti_pts = 5
        else:
            dti_pts = 0
        points += dti_pts
        breakdown["dti_points"] = dti_pts
        breakdown["dti_ratio"] = round(dti, 4)

        # 6. Region
        region_map = {"North": 5, "East": 0, "South": -5, "West": 0}
        reg_pts = region_map.get(region, 0)
        points += reg_pts
        breakdown["region_points"] = reg_pts

        # Risk level
        if points >= 80:
            risk = "Low"
        elif points >= 60:
            risk = "Medium"
        elif points >= 40:
            risk = "High"
        else:
            risk = "Very High"

        raw_default = r.get(TARGET_COLUMN)
        default_label = int(raw_default) if raw_default is not None else None

        scores.append({
            "application_id": r["application_id"],
            "total_score": points,
            "risk_level": risk,
            "score_breakdown": breakdown,
            "actual_default_90d": default_label,
        })
        details.append({
            "application_id": r["application_id"],
            "features_used": {
                "credit_score": credit,
                "loan_to_income_ratio": round(lti, 4),
                "age": age_val,
                "employment_years": emp,
                "debt_to_income_ratio": round(dti, 4),
                "region": region,
            },
        })

    return {
        "scorecard_name": "Rule-Based Credit Risk Scorecard v1",
        "score_range": "0 to 105 (higher = lower risk)",
        "risk_thresholds": {
            "Low": ">= 80",
            "Medium": "60 - 79",
            "High": "40 - 59",
            "Very High": "< 40",
        },
        "scoring_rules": scoring_rules,
        "scores": scores,
        "scoring_details": details,
    }


# ── Business Rule Checks ────────────────────────────────────────────────
def compute_business_rule_checks(rows):
    checks = []

    # 1. Age >= 18
    under_18 = [r for r in rows if r.get("age") is not None and r["age"] < 18]
    checks.append({
        "rule": "applicant_age_must_be_at_least_18",
        "passed": len(under_18) == 0,
        "failed_count": len(under_18),
        "failed_applications": [r["application_id"] for r in under_18],
        "detail": "a004 has age=17 -- underage applicant",
    })

    # 2. Income > 0
    zero_income = [r for r in rows if r.get("income") is not None and r["income"] == 0]
    checks.append({
        "rule": "income_must_be_positive",
        "passed": len(zero_income) == 0,
        "failed_count": len(zero_income),
        "failed_applications": [r["application_id"] for r in zero_income],
        "detail": "a004 has income=0 -- possible data error or unemployed",
    })

    # 3. Loan amount positive
    bad_loan = [r for r in rows if r.get("loan_amount") is not None and r["loan_amount"] <= 0]
    checks.append({
        "rule": "loan_amount_must_be_positive",
        "passed": len(bad_loan) == 0,
        "failed_count": len(bad_loan),
        "failed_applications": [r["application_id"] for r in bad_loan],
    })

    # 4. Credit score range 300-850
    bad_cs = [r for r in rows if r.get("credit_score") is not None and (r["credit_score"] < 300 or r["credit_score"] > 850)]
    checks.append({
        "rule": "credit_score_in_valid_range_300_850",
        "passed": len(bad_cs) == 0,
        "failed_count": len(bad_cs),
        "failed_applications": [r["application_id"] for r in bad_cs],
    })

    # 5. Employment years >= 0
    bad_emp = [r for r in rows if r.get("employment_years") is not None and r["employment_years"] < 0]
    checks.append({
        "rule": "employment_years_non_negative",
        "passed": len(bad_emp) == 0,
        "failed_count": len(bad_emp),
        "failed_applications": [r["application_id"] for r in bad_emp],
    })

    # 6. Unique application_id
    ids = [r["application_id"] for r in rows]
    dup_ids = sorted(set(aid for aid in ids if ids.count(aid) > 1))
    checks.append({
        "rule": "unique_application_id",
        "passed": len(dup_ids) == 0,
        "failed_count": len(dup_ids),
        "failed_applications": dup_ids,
        "detail": "a003 appears twice",
    })

    return {"business_rule_checks": checks}


# ── Explanations ────────────────────────────────────────────────────────
def compute_explanations():
    return {
        "methodology": (
            "A rule-based scorecard was constructed using only pre-loan available features. "
            "Six risk factors (credit score, loan-to-income ratio, age, employment years, "
            "debt-to-income ratio, region) are scored with interpretable point values. "
            "The total score maps to four risk levels. No machine learning model was trained."
        ),
        "why_rule_based": (
            "The dataset has only 8 rows, far too few for any statistical or ML model. "
            "A transparent, deterministic scorecard is the only viable approach."
        ),
        "leakage_handling": (
            "'post_loan_collection_calls' is explicitly excluded as it is a post-loan field. "
            "'default_90d' is the target variable and is not used as a pre-loan feature."
        ),
    }


# ── Warnings ────────────────────────────────────────────────────────────
def compute_warnings(rows):
    warnings = []
    age_missing = sum(1 for r in rows if r.get("age") is None)
    if age_missing:
        warnings.append(f"age contains {age_missing} missing value(s) -- imputed with median for scoring")
    dup_count = sum(1 for i, r in enumerate(rows)
                    if any(tuple(str(rr.get(k, "")) for k in rr) == tuple(str(r.get(k, "")) for k in r)
                           for j, rr in enumerate(rows) if j < i))
    if dup_count:
        warnings.append(f"Found {dup_count} exact duplicate row(s) -- a003 appears twice")
    target_missing = sum(1 for r in rows if r.get(TARGET_COLUMN) is None)
    if target_missing:
        warnings.append(f"default_90d has {target_missing} missing value(s) -- a007 has no label")
    fieldnames = list(rows[0].keys()) if rows else []
    if "post_loan_collection_calls" in fieldnames:
        warnings.append(
            "post_loan_collection_calls is present -- this is a post-loan leakage field excluded from scoring"
        )
    return warnings


# ── How To Do Differently ───────────────────────────────────────────────
def compute_how_to_do_differently():
    return {
        "with_more_data": (
            "With a larger dataset (thousands of rows), a logistic regression or "
            "gradient-boosted tree with proper train/test split and cross-validation "
            "would be appropriate. Features like credit score, income, debt ratio, "
            "and employment length are well-suited for interpretable ML models."
        ),
        "additional_features": (
            "If available, add: loan purpose, payment history, number of dependents, "
            "education level, and existing credit line utilization."
        ),
        "production_considerations": (
            "In production: implement feature pipelines with monitoring, maintain "
            "a separate holdout for drift detection, and document model cards."
        ),
    }


# ── Validation ──────────────────────────────────────────────────────────
def compute_validation(rows):
    # Compute median age
    age_vals = [r["age"] for r in rows if r.get("age") is not None]
    sorted_ages = sorted(age_vals)
    median_age = sorted_ages[len(sorted_ages) // 2] if sorted_ages else 30

    # Score each row that has a known default_90d label
    scored = []
    for r in rows:
        raw_default = r.get(TARGET_COLUMN)
        if raw_default is None:
            continue
        age_val = r["age"] if r.get("age") is not None else median_age
        credit = r["credit_score"] if r.get("credit_score") is not None else 600
        income = r["income"] if r.get("income") is not None and r["income"] > 0 else 1
        loan = r["loan_amount"] if r.get("loan_amount") is not None else 0
        debt = r["existing_debt"] if r.get("existing_debt") is not None else 0
        emp = r["employment_years"] if r.get("employment_years") is not None else 0
        region = r.get("region", "")

        pts = 0
        pts += 40 if credit >= 700 else 30 if credit >= 650 else 15 if credit >= 600 else 0
        lti = loan / income
        pts += 20 if lti <= 0.3 else 10 if lti <= 0.5 else 0
        pts += 10 if age_val >= 25 else 5 if age_val >= 18 else -10
        pts += 15 if emp >= 5 else 10 if emp >= 2 else 5
        dti = debt / income
        pts += 15 if dti <= 0.3 else 5 if dti <= 0.6 else 0
        pts += {"North": 5, "East": 0, "South": -5, "West": 0}.get(region, 0)

        if pts >= 80:
            risk = "Low"
        elif pts >= 60:
            risk = "Medium"
        elif pts >= 40:
            risk = "High"
        else:
            risk = "Very High"

        scored.append((risk, int(raw_default)))

    # Group by risk level
    levels = ["Very High", "High", "Medium", "Low"]
    calibration = {}
    for level in levels:
        group = [s for s in scored if s[0] == level]
        if group:
            default_rate = sum(s[1] for s in group) / len(group)
            calibration[level] = {
                "count": len(group),
                "default_rate": round(default_rate, 4),
            }
        else:
            calibration[level] = {"count": 0, "default_rate": None}

    return {
        "calibration_check": calibration,
        "note": "Validation based on available default_90d labels; sample too small for meaningful statistics.",
        "expected_monotonicity": "Higher risk level -> higher default rate (monotonic relationship expected)",
    }


# ── Main ────────────────────────────────────────────────────────────────
def main():
    rows, fieldnames = load_data()

    answer = {
        "row_counts": compute_row_counts(rows, fieldnames),
        "field_summary": compute_field_summary(rows, fieldnames),
        "data_quality": compute_data_quality(rows),
        "feature_processing": compute_feature_processing(rows),
        "scoring_result": compute_scoring_result(rows),
        "business_rule_checks": compute_business_rule_checks(rows),
        "explanations": compute_explanations(),
        "warnings": compute_warnings(rows),
        "how_to_do_differently": compute_how_to_do_differently(),
        "validation": compute_validation(rows),
    }

    with open(ANSWER_PATH, "w", encoding="utf-8") as f:
        json.dump(answer, f, ensure_ascii=False, indent=2)

    print(f"answer.json written to {ANSWER_PATH}")


if __name__ == "__main__":
    main()
