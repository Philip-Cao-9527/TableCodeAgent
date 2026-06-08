from __future__ import annotations

from datetime import date
from typing import Any, Literal, Type

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, ValidationError, field_validator


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


FinanceAgingBucketName = Literal["not_due", "0-30", "31-60", "61-90", "90+", "missing_due_date"]
FinanceRiskBand = Literal["low", "medium", "high"]
FinancePriority = Literal["low", "medium", "high"]
FinanceExceptionType = Literal[
    "duplicate_invoice",
    "duplicate_payment",
    "partial_payment",
    "overpayment",
    "approved_credit_memo",
    "pending_write_off",
    "chargeback",
    "unapplied_cash",
    "currency_mismatch",
    "negative_invoice_amount",
    "missing_due_date",
    "disputed_invoice",
    "inactive_or_on_hold_customer",
    "future_dated_payment",
    "non_posted_payment",
    "unmatched_adjustment",
    "over_credit_limit",
    "missing_po",
    "term_mismatch",
]


class FinanceSummary(FlexibleModel):
    reference_date: StrictStr
    base_currency: StrictStr
    invoice_row_count: StrictInt
    unique_invoice_count: StrictInt
    duplicate_invoice_count: StrictInt
    payment_row_count: StrictInt
    duplicate_payment_count: StrictInt
    total_invoice_amount_by_currency: dict[str, StrictFloat]
    applied_payment_amount_by_currency: dict[str, StrictFloat]
    approved_adjustment_amount_by_currency: dict[str, StrictFloat]
    open_invoice_amount_by_currency: dict[str, StrictFloat]
    unapplied_cash_amount_by_currency: dict[str, StrictFloat]
    disputed_open_amount_by_currency: dict[str, StrictFloat]
    expected_credit_loss_by_currency: dict[str, StrictFloat]


class FinanceCustomerRiskRow(FlexibleModel):
    customer_id: StrictStr
    customer_name: StrictStr
    status: StrictStr
    risk_band: FinanceRiskBand
    open_amount_by_currency: dict[str, StrictFloat]
    overdue_amount_by_currency: dict[str, StrictFloat]
    disputed_open_amount_by_currency: dict[str, StrictFloat]
    risk_amount_excluding_disputed_by_currency: dict[str, StrictFloat]
    expected_credit_loss_by_currency: dict[str, StrictFloat]
    max_days_overdue: StrictInt | None
    action_tags: list[StrictStr]
    rationale: list[StrictStr]


class FinanceInvoiceReconciliationRow(FlexibleModel):
    invoice_id: StrictStr
    customer_id: StrictStr
    currency: StrictStr
    invoice_amount: StrictFloat
    approved_adjustment_amount: StrictFloat
    adjusted_invoice_amount: StrictFloat
    applied_amount: StrictFloat
    open_amount: StrictFloat
    overpayment_amount: StrictFloat
    disputed_open_amount: StrictFloat
    expected_credit_loss: StrictFloat
    due_date: StrictStr | None
    days_overdue: StrictInt | None
    aging_bucket: FinanceAgingBucketName
    status: Literal["open", "closed", "overpaid", "excluded"]
    exception_tags: list[StrictStr]

    @field_validator("due_date")
    @classmethod
    def due_date_must_be_iso_or_null(cls, value: StrictStr | None) -> StrictStr | None:
        if value is None:
            return value
        text = value.strip()
        if not text or text.lower() in {"nan", "nat", "none", "null"}:
            raise ValueError("due_date must be null for missing dates, not an empty or NaN-like string.")
        date.fromisoformat(text)
        return text


class FinanceAgingBucketRow(FlexibleModel):
    currency: StrictStr
    bucket: FinanceAgingBucketName
    invoice_count: StrictInt
    open_amount: StrictFloat
    risk_amount_excluding_disputed: StrictFloat
    expected_credit_loss: StrictFloat


class FinanceExceptionRow(FlexibleModel):
    exception_type: FinanceExceptionType
    severity: Literal["info", "warning", "critical"]
    count: StrictInt
    amount_by_currency: dict[str, StrictFloat]
    related_ids: list[StrictStr]
    description: StrictStr


class FinanceRecommendedAction(FlexibleModel):
    customer_id: StrictStr
    priority: FinancePriority
    action_type: Literal[
        "collect_overdue",
        "resolve_dispute",
        "apply_unapplied_cash",
        "fix_data_quality",
        "review_customer_status",
        "investigate_payment",
        "review_credit_hold",
        "review_adjustment",
        "request_documentation",
        "investigate_chargeback",
    ]
    invoice_ids: list[StrictStr]
    details: StrictStr


class FinanceDataQuality(FlexibleModel):
    required_columns: dict[str, list[StrictStr]]
    missing_required_columns: dict[str, list[StrictStr]]
    duplicate_invoice_ids: list[StrictStr]
    duplicate_payment_ids: list[StrictStr]
    invalid_invoice_ids: list[StrictStr]
    unmatched_payment_ids: list[StrictStr]
    currency_mismatch_payment_ids: list[StrictStr]
    missing_due_date_invoice_ids: list[StrictStr]
    future_dated_payment_ids: list[StrictStr]
    non_posted_payment_ids: list[StrictStr]
    unmatched_adjustment_ids: list[StrictStr]
    term_mismatch_invoice_ids: list[StrictStr]
    missing_po_invoice_ids: list[StrictStr]
    over_credit_limit_customer_ids: list[StrictStr]


class FinanceAuditNote(FlexibleModel):
    step: StrictStr
    evidence: StrictStr


class FinanceOperationsAnswer(FlexibleModel):
    summary: FinanceSummary
    customer_risk: list[FinanceCustomerRiskRow]
    invoice_reconciliation: list[FinanceInvoiceReconciliationRow]
    aging_buckets: list[FinanceAgingBucketRow]
    exceptions: list[FinanceExceptionRow]
    recommended_actions: list[FinanceRecommendedAction]
    data_quality: FinanceDataQuality
    audit_notes: list[FinanceAuditNote]
    validation: dict[str, Any]


ANSWER_MODELS: dict[str, Type[BaseModel]] = {
    "credit_risk_scoring": CreditRiskScoringAnswer,
    "credit_risk_scoring_001": CreditRiskScoringAnswer,
    "finance_operations": FinanceOperationsAnswer,
    "finance_operations_001": FinanceOperationsAnswer,
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
