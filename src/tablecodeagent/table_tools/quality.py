from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from tablecodeagent.table_tools.core import read_table_frame


def _pd():
    try:
        import pandas as pd
        return pd
    except ImportError as error:
        raise ImportError("Quality checks require pandas.") from error


def _frame(value: Any):
    if hasattr(value, "columns") and hasattr(value, "copy"):
        return value.copy()
    frame, _ = read_table_frame(value)
    return frame


def _missing_frame(df: Any) -> Any:
    blank = df.astype("string").apply(lambda column: column.str.strip().eq(""))
    return df.isna() | blank.fillna(False)


def check_missing_values(table: Any, columns: list[str] | None = None) -> dict[str, Any]:
    df = _frame(table)
    target_columns = columns or list(df.columns)
    missing_matrix = _missing_frame(df.reindex(columns=target_columns))
    missing_counts = missing_matrix.sum().astype(int)
    missing_rates = missing_matrix.mean().fillna(0.0)
    missing_by_column = missing_counts.to_dict()
    missing_rate_by_column = missing_rates.to_dict()
    return {
        "row_count": len(df),
        "missing_by_column": missing_by_column,
        "missing_rate_by_column": missing_rate_by_column,
        "columns_with_missing": [column for column, count in missing_by_column.items() if count > 0],
        "total_missing": int(sum(missing_by_column.values())),
    }


def check_unique_key(table: Any, key_columns: list[str]) -> dict[str, Any]:
    df = _frame(table)
    missing_columns = [column for column in key_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing key columns: {missing_columns}")
    duplicated = df.duplicated(subset=key_columns, keep=False)
    duplicate_rows = df.loc[duplicated, key_columns]
    duplicate_groups = duplicate_rows.drop_duplicates()
    examples = duplicate_groups.head(20).to_dict(orient="records")
    return {
        "key_columns": key_columns,
        "row_count": len(df),
        "is_unique": not bool(duplicated.any()),
        "duplicate_key_count": int(len(duplicate_groups)),
        "duplicate_row_count": int(duplicated.sum()),
        "duplicate_examples": examples,
    }


def _cardinality(left_duplicate_groups: int, right_duplicate_groups: int) -> str:
    if left_duplicate_groups and right_duplicate_groups:
        return "many_to_many"
    if right_duplicate_groups:
        return "one_to_many"
    if left_duplicate_groups:
        return "many_to_one"
    return "one_to_one"


def check_join_cardinality(
    left_table: Any,
    right_table: Any,
    *,
    left_keys: list[str],
    right_keys: list[str] | None = None,
    how: str = "left",
) -> dict[str, Any]:
    pd = _pd()
    left = _frame(left_table)
    right = _frame(right_table)
    right_keys = right_keys or left_keys
    if len(left_keys) != len(right_keys):
        raise ValueError("left_keys and right_keys must have the same length.")

    left_dupes = check_unique_key(left, left_keys)
    right_dupes = check_unique_key(right, right_keys)
    right_for_join = right.copy()
    rename_map = {right_key: left_key for left_key, right_key in zip(left_keys, right_keys) if left_key != right_key}
    right_for_join = right_for_join.rename(columns=rename_map)
    joined = left.merge(right_for_join, on=left_keys, how=how, suffixes=("_left", "_right"))
    ratio = len(joined) / len(left) if len(left) else 0.0
    cardinality = _cardinality(left_dupes["duplicate_key_count"], right_dupes["duplicate_key_count"])
    risk = cardinality in {"one_to_many", "many_to_one", "many_to_many"} or ratio > 1.0
    return {
        "left_row_count": len(left),
        "right_row_count": len(right),
        "joined_row_count": len(joined),
        "join_type": how,
        "left_keys": left_keys,
        "right_keys": right_keys,
        "cardinality": cardinality,
        "left_duplicate_key_count": left_dupes["duplicate_key_count"],
        "right_duplicate_key_count": right_dupes["duplicate_key_count"],
        "row_expansion_ratio": ratio,
        "row_expansion_detected": ratio > 1.0,
        "join_risk": risk,
        "joined_preview": joined.head(5).to_dict(orient="records"),
    }


def check_treatment_control_distribution(
    table: Any,
    *,
    group_column: str = "treatment_group",
    treatment_value: str = "treatment",
    control_value: str = "control",
    min_group_ratio: float = 0.5,
) -> dict[str, Any]:
    df = _frame(table)
    counts = df[group_column].fillna("").astype(str).value_counts().to_dict()
    treatment_count = int(counts.get(treatment_value, 0))
    control_count = int(counts.get(control_value, 0))
    largest = max(treatment_count, control_count, 1)
    smallest = min(treatment_count, control_count)
    minority_ratio = smallest / largest
    imbalanced = minority_ratio < min_group_ratio
    return {
        "group_column": group_column,
        "counts": {key: int(value) for key, value in counts.items()},
        "treatment_count": treatment_count,
        "control_count": control_count,
        "minority_to_majority_ratio": minority_ratio,
        "imbalanced": imbalanced,
        "imbalanced_group": control_value if control_count < treatment_count else treatment_value,
        "threshold": min_group_ratio,
    }


def _is_numeric(series: Any) -> bool:
    pd = _pd()
    converted = pd.to_numeric(series, errors="coerce")
    return converted.notna().sum() >= max(1, int(series.notna().sum() * 0.8))


def _numeric_smd(treatment: Any, control: Any) -> float:
    pd = _pd()
    t = pd.to_numeric(treatment, errors="coerce").dropna()
    c = pd.to_numeric(control, errors="coerce").dropna()
    if len(t) == 0 or len(c) == 0:
        return 0.0
    var_t = float(t.var(ddof=1)) if len(t) > 1 else 0.0
    var_c = float(c.var(ddof=1)) if len(c) > 1 else 0.0
    pooled = math.sqrt((var_t + var_c) / 2)
    if pooled == 0:
        return 0.0 if float(t.mean()) == float(c.mean()) else float("inf")
    return float((t.mean() - c.mean()) / pooled)


def _categorical_balance_gap(treatment: Any, control: Any) -> float:
    t_dist = treatment.fillna("").astype(str).value_counts(normalize=True).to_dict()
    c_dist = control.fillna("").astype(str).value_counts(normalize=True).to_dict()
    categories = set(t_dist) | set(c_dist)
    if not categories:
        return 0.0
    return max(abs(float(t_dist.get(cat, 0.0)) - float(c_dist.get(cat, 0.0))) for cat in categories)


def calculate_smd(
    table: Any,
    *,
    group_column: str,
    covariates: list[str],
    treatment_value: str = "treatment",
    control_value: str = "control",
    threshold: float = 0.1,
) -> dict[str, Any]:
    df = _frame(table)
    treatment = df[df[group_column].astype(str) == treatment_value]
    control = df[df[group_column].astype(str) == control_value]
    by_column: dict[str, dict[str, Any]] = {}
    warning_columns: list[str] = []

    for column in covariates:
        if column not in df.columns:
            by_column[column] = {"missing_column": True, "smd": None, "warning": True}
            warning_columns.append(column)
            continue
        if _is_numeric(df[column]):
            score = abs(_numeric_smd(treatment[column], control[column]))
            method = "numeric_smd"
        else:
            score = _categorical_balance_gap(treatment[column], control[column])
            method = "categorical_max_proportion_gap"
        warning = bool(score > threshold or math.isinf(score))
        if warning:
            warning_columns.append(column)
        by_column[column] = {
            "method": method,
            "smd": score,
            "threshold": threshold,
            "warning": warning,
        }

    return {
        "group_column": group_column,
        "treatment_count": int(len(treatment)),
        "control_count": int(len(control)),
        "by_column": by_column,
        "warning_columns": warning_columns,
    }


def check_group_balance(
    table: Any,
    *,
    group_column: str,
    covariates: list[str],
    treatment_value: str = "treatment",
    control_value: str = "control",
    threshold: float = 0.1,
) -> dict[str, Any]:
    return calculate_smd(
        table,
        group_column=group_column,
        covariates=covariates,
        treatment_value=treatment_value,
        control_value=control_value,
        threshold=threshold,
    )


def check_subsidy_outliers(
    table: Any,
    *,
    column: str = "subsidy_amount",
    iqr_multiplier: float = 1.5,
) -> dict[str, Any]:
    pd = _pd()
    df = _frame(table)
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        return {"column": column, "outlier_count": 0, "outlier_rows": [], "lower_bound": None, "upper_bound": None}
    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - iqr_multiplier * iqr
    upper = q3 + iqr_multiplier * iqr
    numeric = pd.to_numeric(df[column], errors="coerce")
    mask = (numeric < lower) | (numeric > upper)
    return {
        "column": column,
        "method": "iqr",
        "iqr_multiplier": iqr_multiplier,
        "lower_bound": lower,
        "upper_bound": upper,
        "outlier_count": int(mask.sum()),
        "outlier_rows": df.loc[mask].head(20).to_dict(orient="records"),
    }


def check_time_window_alignment(
    orders_table: Any,
    exposure_table: Any,
    *,
    user_key: str = "user_id",
    order_time_column: str = "order_time",
    campaign_window_column: str = "campaign_window",
) -> dict[str, Any]:
    pd = _pd()
    orders = _frame(orders_table)
    exposure = _frame(exposure_table)
    windows = exposure[[user_key, campaign_window_column]].drop_duplicates(subset=[user_key])
    joined = orders.merge(windows, on=user_key, how="left")

    window_text = joined[campaign_window_column].fillna("").astype(str).str.strip()
    bounds = window_text.str.split(":", n=1, expand=True).reindex(columns=[0, 1])
    start = pd.to_datetime(bounds[0], errors="coerce")
    end = pd.to_datetime(bounds[1], errors="coerce")
    order_time = pd.to_datetime(joined[order_time_column], errors="coerce")

    missing_window = window_text.eq("") | start.isna() | end.isna()
    outside_window = (~missing_window) & (order_time.isna() | order_time.lt(start) | order_time.gt(end))
    mismatch_mask = missing_window | outside_window
    reason = pd.Series("", index=joined.index)
    reason.loc[missing_window] = "missing_campaign_window"
    reason.loc[outside_window] = "order_outside_campaign_window"
    mismatch = joined.loc[mismatch_mask].copy()
    mismatch["mismatch_reason"] = reason.loc[mismatch_mask]
    return {
        "order_count": len(orders),
        "checked_order_count": len(joined),
        "mismatch_count": int(mismatch_mask.sum()),
        "mismatch_rows": mismatch.head(20).to_dict(orient="records"),
    }


def expected_warning_coverage(warnings: list[str], expected_required_warnings: list[str]) -> dict[str, Any]:
    warning_text = "\n".join(warnings)
    covered = [warning for warning in expected_required_warnings if warning in warning_text]
    missing = [warning for warning in expected_required_warnings if warning not in warning_text]
    return {
        "covered": covered,
        "missing": missing,
        "warning_recall": len(covered) / len(expected_required_warnings) if expected_required_warnings else 1.0,
        "expected_warning_coverage": len(covered),
    }
