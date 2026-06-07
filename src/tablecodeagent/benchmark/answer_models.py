from __future__ import annotations

from typing import Any, Literal, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class DuplicateKeyReport(FlexibleModel):
    key_columns: list[str]
    duplicate_key_count: int


class FieldTypeIssue(FlexibleModel):
    column: str
    invalid_count: int
    expected_type: str


class RiskScoreRow(FlexibleModel):
    application_id: str
    user_id: str
    risk_score: float
    risk_band: Literal["low", "medium", "high"]


class RiskBandCounts(FlexibleModel):
    low: int
    medium: int
    high: int


class CreditDataQuality(FlexibleModel):
    required_columns: list[str]
    missing_required_columns: list[str]
    missing_values: dict[str, Any]
    duplicate_keys: DuplicateKeyReport
    duplicate_customers: DuplicateKeyReport
    invalid_age_count: int
    leakage_columns_present: list[str]
    field_type_issues: list[FieldTypeIssue] = Field(default_factory=list)


class CreditFeatureProcessing(FlexibleModel):
    pre_loan_numeric_features: list[str]
    pre_loan_categorical_features: list[str]
    excluded_columns: list[str]
    exclusion_reasons: dict[str, str]
    feature_window: dict[str, Any]
    label_window: dict[str, Any]
    time_split_column: str


class CreditScoringResult(FlexibleModel):
    method: str
    scored_rows: list[RiskScoreRow]
    risk_band_counts: RiskBandCounts


class CreditBusinessRuleChecks(FlexibleModel):
    target_not_used_as_feature: bool
    leakage_columns_excluded: bool
    label_window_declared: bool
    feature_window_declared: bool
    duplicate_application_check_completed: bool
    customer_uniqueness_check_completed: bool
    field_type_checks_completed: bool
    requires_manual_review_for_high_risk: bool


class CreditRiskScoringAnswer(FlexibleModel):
    row_counts: dict[str, int]
    field_summary: dict[str, Any]
    data_quality: CreditDataQuality
    feature_processing: CreditFeatureProcessing
    scoring_result: CreditScoringResult
    business_rule_checks: CreditBusinessRuleChecks
    explanations: list[str]
    warnings: list[str]
    how_to_do_differently: list[str]
    validation: dict[str, Any]


class GrowthCampaignAuditAnswer(FlexibleModel):
    row_counts: dict[str, int]
    unique_keys: dict[str, DuplicateKeyReport]
    join_cardinality: dict[str, Any]
    group_distribution: dict[str, Any]
    smd_summary: dict[str, Any]
    outlier_summary: dict[str, Any]
    time_window_alignment: dict[str, Any]
    warnings: list[str]
    how_to_do_differently: list[str]


ANSWER_MODELS: dict[str, Type[BaseModel]] = {
    "credit_risk_scoring": CreditRiskScoringAnswer,
    "credit_risk_scoring_001": CreditRiskScoringAnswer,
    "growth_campaign_audit": GrowthCampaignAuditAnswer,
    "growth_campaign_audit_001": GrowthCampaignAuditAnswer,
}


def resolve_answer_model(*, task_type: str | None = None, task_id: str | None = None, answer_model: str | None = None) -> Type[BaseModel] | None:
    for key in (answer_model, task_type, task_id):
        if key and key in ANSWER_MODELS:
            return ANSWER_MODELS[key]
    return None


def answer_json_schema(*, task_type: str | None = None, task_id: str | None = None, answer_model: str | None = None) -> dict[str, Any] | None:
    model = resolve_answer_model(task_type=task_type, task_id=task_id, answer_model=answer_model)
    return model.model_json_schema() if model else None


def _format_loc(loc: tuple[Any, ...]) -> str:
    path = "$"
    for item in loc:
        if isinstance(item, int):
            path += f"[{item}]"
        else:
            path += f".{item}"
    return path


def validate_answer_json_with_model(
    answer_data: Any,
    *,
    task_type: str | None = None,
    task_id: str | None = None,
    answer_model: str | None = None,
) -> dict[str, Any]:
    model = resolve_answer_model(task_type=task_type, task_id=task_id, answer_model=answer_model)
    if model is None:
        return {"passed": None, "errors": [], "model": None}
    try:
        model.model_validate(answer_data)
    except ValidationError as error:
        return {
            "passed": False,
            "model": model.__name__,
            "errors": [
                {
                    "path": _format_loc(tuple(item.get("loc", ()))),
                    "message": item.get("msg"),
                    "type": item.get("type"),
                }
                for item in error.errors()
            ],
        }
    return {"passed": True, "model": model.__name__, "errors": []}
