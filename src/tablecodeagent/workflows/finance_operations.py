from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


MONEY_QUANT = Decimal("0.01")
AGING_BUCKETS = ("not_due", "0-30", "31-60", "61-90", "90+", "missing_due_date")
MISSING_TEXTS = {"", "nan", "nat", "none", "null"}


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    customer_id: str
    invoice_date: str
    due_date: str
    amount: Decimal
    currency: str
    status: str
    po_number: str
    delivery_status: str
    billing_hold_flag: str


@dataclass(frozen=True)
class Payment:
    payment_id: str
    customer_id: str
    invoice_id: str
    payment_date: str
    gl_date: str
    amount: Decimal
    currency: str
    status: str


@dataclass(frozen=True)
class Adjustment:
    adjustment_id: str
    invoice_id: str
    customer_id: str
    adjustment_type: str
    adjustment_date: str
    amount: Decimal
    currency: str
    status: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _resolve(task_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else task_dir / path


def _money(value: Any) -> Decimal:
    text = str(value if value is not None else "").strip()
    if not text:
        return Decimal("0.00")
    return Decimal(text).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _money_float(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def _clean_text(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return "" if text.lower() in MISSING_TEXTS else text


def _add_amount(target: dict[str, Decimal], currency: str, amount: Decimal) -> None:
    target[currency] = (target.get(currency, Decimal("0.00")) + amount).quantize(MONEY_QUANT)


def _amounts_to_float(values: dict[str, Decimal]) -> dict[str, float]:
    return {currency: _money_float(values[currency]) for currency in sorted(values)}


def _dedupe_rows(rows: list[dict[str, str]], key: str) -> tuple[list[dict[str, str]], list[str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    duplicates: list[str] = []
    for row in rows:
        value = str(row.get(key, "")).strip()
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
        unique.append(row)
    return unique, duplicates


def _parse_date(value: str) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    return date.fromisoformat(text)


def _days_overdue(due_date: str, reference_date: date) -> int | None:
    due = _parse_date(due_date)
    if due is None:
        return None
    return max(0, (reference_date - due).days)


def _aging_bucket(due_date: str, reference_date: date) -> str:
    days = _days_overdue(due_date, reference_date)
    if days is None:
        return "missing_due_date"
    if days == 0:
        due = _parse_date(due_date)
        return "not_due" if due and due > reference_date else "0-30"
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def _required_columns(task: dict[str, Any]) -> dict[str, list[str]]:
    config = task.get("finance_config", {})
    return dict(config.get("required_columns") or {})


def _missing_required_columns(tables: dict[str, list[dict[str, str]]], required: dict[str, list[str]]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for table_name, columns in required.items():
        rows = tables.get(table_name) or []
        observed = set(rows[0].keys()) if rows else set()
        missing[table_name] = [column for column in columns if column not in observed]
    return missing


def _customer_lookup(customers: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["customer_id"]: row for row in customers}


def _build_invoice(row: dict[str, str]) -> Invoice:
    return Invoice(
        invoice_id=row["invoice_id"],
        customer_id=row["customer_id"],
        invoice_date=_clean_text(row.get("invoice_date", "")),
        due_date=_clean_text(row.get("due_date", "")),
        amount=_money(row.get("invoice_amount", "0")),
        currency=_clean_text(row.get("currency", "")),
        status=_clean_text(row.get("status", "")),
        po_number=_clean_text(row.get("po_number", "")),
        delivery_status=_clean_text(row.get("delivery_status", "")),
        billing_hold_flag=_clean_text(row.get("billing_hold_flag", "")).lower(),
    )


def _build_payment(row: dict[str, str]) -> Payment:
    return Payment(
        payment_id=row["payment_id"],
        customer_id=_clean_text(row.get("customer_id", "")),
        invoice_id=_clean_text(row.get("invoice_id", "")),
        payment_date=_clean_text(row.get("payment_date", "")),
        gl_date=_clean_text(row.get("gl_date", "")),
        amount=_money(row.get("payment_amount", "0")),
        currency=_clean_text(row.get("currency", "")),
        status=_clean_text(row.get("status", "")),
    )


def _build_adjustment(row: dict[str, str]) -> Adjustment:
    return Adjustment(
        adjustment_id=row["adjustment_id"],
        invoice_id=_clean_text(row.get("invoice_id", "")),
        customer_id=_clean_text(row.get("customer_id", "")),
        adjustment_type=_clean_text(row.get("adjustment_type", "")).lower(),
        adjustment_date=_clean_text(row.get("adjustment_date", "")),
        amount=_money(row.get("amount", "0")),
        currency=_clean_text(row.get("currency", "")),
        status=_clean_text(row.get("status", "")).lower(),
    )


def _open_disputes(disputes: list[dict[str, str]]) -> dict[str, Decimal]:
    amounts: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in disputes:
        if row.get("status", "").strip().lower() != "open":
            continue
        amounts[row["invoice_id"]] += _money(row.get("dispute_amount", "0"))
    return {key: value.quantize(MONEY_QUANT) for key, value in amounts.items()}


def _exception_row(
    exception_type: str,
    severity: str,
    related_ids: list[str],
    description: str,
    amount_by_currency: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    return {
        "exception_type": exception_type,
        "severity": severity,
        "count": len(related_ids),
        "amount_by_currency": _amounts_to_float(amount_by_currency or {}),
        "related_ids": related_ids,
        "description": description,
    }


def _loss_rates(policy: dict[str, str]) -> dict[str, Decimal]:
    return {
        "not_due": Decimal(str(policy.get("loss_rate_not_due", "0"))),
        "0-30": Decimal(str(policy.get("loss_rate_0_30", "0"))),
        "31-60": Decimal(str(policy.get("loss_rate_31_60", "0"))),
        "61-90": Decimal(str(policy.get("loss_rate_61_90", "0"))),
        "90+": Decimal(str(policy.get("loss_rate_90_plus", "0"))),
        "missing_due_date": Decimal(str(policy.get("loss_rate_missing_due_date", "0"))),
    }


def _loss_amount(amount: Decimal, bucket: str, loss_rates: dict[str, Decimal]) -> Decimal:
    return (amount * loss_rates[bucket]).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _risk_band(row: dict[str, Any]) -> str:
    max_days = row["max_days_overdue"] or 0
    risk_amount = sum(row["risk_amount_excluding_disputed_by_currency"].values())
    if row["status"] != "active" and sum(row["open_amount_by_currency"].values()) > 0:
        return "high"
    if max_days >= 90 or risk_amount >= 800:
        return "high"
    if max_days >= 31 or sum(row["open_amount_by_currency"].values()) >= 500:
        return "medium"
    return "low"


def _priority(risk_band: str) -> str:
    return "high" if risk_band == "high" else "medium" if risk_band == "medium" else "low"


def _sort_customer_risk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        rows,
        key=lambda row: (
            rank[row["risk_band"]],
            -sum(row["open_amount_by_currency"].values()),
            row["customer_id"],
        ),
    )


def _validate_report(report: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    exceptions = {row["exception_type"]: row for row in report["exceptions"]}
    aging = {
        (row["currency"], row["bucket"]): row
        for row in report["aging_buckets"]
    }
    checks = {
        "open_usd": summary["open_invoice_amount_by_currency"].get("USD") == expected["expected_open_amount_by_currency"]["USD"],
        "open_eur": summary["open_invoice_amount_by_currency"].get("EUR") == expected["expected_open_amount_by_currency"]["EUR"],
        "unapplied_usd": summary["unapplied_cash_amount_by_currency"].get("USD") == expected["expected_unapplied_cash_by_currency"]["USD"],
        "duplicate_invoice_count": summary["duplicate_invoice_count"] == expected["expected_duplicate_invoice_count"],
        "duplicate_payment_count": summary["duplicate_payment_count"] == expected["expected_duplicate_payment_count"],
        "overpayment_amount": exceptions["overpayment"]["amount_by_currency"].get("USD") == expected["expected_overpayment_by_currency"]["USD"],
        "currency_mismatch_count": exceptions["currency_mismatch"]["count"] == expected["expected_currency_mismatch_payment_count"],
        "missing_due_date_count": exceptions["missing_due_date"]["count"] == expected["expected_missing_due_date_count"],
        "future_dated_payment_count": exceptions["future_dated_payment"]["count"] == expected["expected_future_dated_payment_count"],
        "non_posted_payment_count": exceptions["non_posted_payment"]["count"] == expected["expected_non_posted_payment_count"],
        "allowance_usd": summary["expected_credit_loss_by_currency"].get("USD") == expected["expected_credit_loss_by_currency"]["USD"],
        "usd_aging_90_plus": aging[("USD", "90+")]["open_amount"] == expected["expected_aging_buckets"]["USD"]["90+"],
        "usd_aging_61_90": aging[("USD", "61-90")]["open_amount"] == expected["expected_aging_buckets"]["USD"]["61-90"],
        "required_actions": set(expected["expected_required_action_tags"]).issubset(
            {tag for row in report["customer_risk"] for tag in row["action_tags"]}
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def build_finance_operations_report(task_dir: str | Path) -> dict[str, Any]:
    task_path = Path(task_dir)
    task = _read_json(task_path / "task.json")
    table_paths = {name: _resolve(task_path, path) for name, path in task["tables"].items()}
    invoices_raw = _read_csv(table_paths["invoices"])
    payments_raw = _read_csv(table_paths["payments"])
    customers = _read_csv(table_paths["customers"])
    disputes = _read_csv(table_paths["disputes"])
    adjustments_raw = _read_csv(table_paths["adjustments"])
    policy = _read_csv(table_paths["policy"])[0]
    reference_date = _parse_date(policy["reference_date"])
    if reference_date is None:
        raise ValueError("policy.reference_date is required.")

    required = _required_columns(task)
    tables = {
        "invoices": invoices_raw,
        "payments": payments_raw,
        "customers": customers,
        "disputes": disputes,
        "adjustments": adjustments_raw,
        "policy": [policy],
    }
    missing_required = _missing_required_columns(tables, required)
    invoice_rows, duplicate_invoice_ids = _dedupe_rows(invoices_raw, "invoice_id")
    payment_rows, duplicate_payment_ids = _dedupe_rows(payments_raw, "payment_id")
    invoices = [_build_invoice(row) for row in invoice_rows]
    all_payments = [_build_payment(row) for row in payment_rows]
    payments: list[Payment] = []
    non_posted_payment_ids: list[str] = []
    future_dated_payment_ids: list[str] = []
    for payment in all_payments:
        if payment.status.strip().lower() != "posted":
            non_posted_payment_ids.append(payment.payment_id)
            continue
        payment_date = _parse_date(payment.payment_date)
        gl_date = _parse_date(payment.gl_date)
        if (payment_date and payment_date > reference_date) or (gl_date and gl_date > reference_date):
            future_dated_payment_ids.append(payment.payment_id)
            continue
        payments.append(payment)
    adjustments = [_build_adjustment(row) for row in adjustments_raw]
    invalid_invoice_ids = [invoice.invoice_id for invoice in invoices if invoice.amount < 0]
    active_invoices = [invoice for invoice in invoices if invoice.invoice_id not in set(invalid_invoice_ids)]
    invoice_by_id = {invoice.invoice_id: invoice for invoice in active_invoices}
    customers_by_id = _customer_lookup(customers)
    dispute_amounts = _open_disputes(disputes)
    loss_rates = _loss_rates(policy)
    customer_credit_limits = {
        row["customer_id"]: _money(row.get("credit_limit", "0"))
        for row in customers
    }
    customer_terms = {
        row["customer_id"]: int(row.get("credit_terms_days") or 0)
        for row in customers
    }

    applied_raw: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    approved_adjustments_by_invoice: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    adjustment_amounts_by_currency: dict[str, Decimal] = {}
    adjustment_amounts_by_type_currency: dict[str, dict[str, Decimal]] = defaultdict(dict)
    approved_credit_memo_ids: list[str] = []
    pending_write_off_ids: list[str] = []
    pending_write_off_invoice_ids: list[str] = []
    chargeback_ids: list[str] = []
    unmatched_adjustment_ids: list[str] = []
    unapplied: dict[str, Decimal] = {}
    unapplied_customer_ids: set[str] = set()
    currency_mismatch_payment_ids: list[str] = []
    unmatched_payment_ids: list[str] = []
    for payment in payments:
        invoice = invoice_by_id.get(payment.invoice_id)
        if not payment.invoice_id or invoice is None:
            unmatched_payment_ids.append(payment.payment_id)
            unapplied[payment.payment_id] = payment.amount
            if payment.customer_id:
                unapplied_customer_ids.add(payment.customer_id)
            continue
        if payment.currency != invoice.currency:
            currency_mismatch_payment_ids.append(payment.payment_id)
            unapplied[payment.payment_id] = payment.amount
            if payment.customer_id:
                unapplied_customer_ids.add(payment.customer_id)
            continue
        applied_raw[invoice.invoice_id] += payment.amount

    for adjustment in adjustments:
        invoice = invoice_by_id.get(adjustment.invoice_id)
        if invoice is None or invoice.currency != adjustment.currency:
            unmatched_adjustment_ids.append(adjustment.adjustment_id)
            continue
        if adjustment.adjustment_type == "write_off" and adjustment.status != "approved":
            pending_write_off_ids.append(adjustment.adjustment_id)
            pending_write_off_invoice_ids.append(adjustment.invoice_id)
            continue
        if adjustment.status != "approved":
            continue
        if adjustment.adjustment_type == "credit_memo":
            approved_credit_memo_ids.append(adjustment.adjustment_id)
        elif adjustment.adjustment_type == "chargeback":
            chargeback_ids.append(adjustment.adjustment_id)
        elif adjustment.adjustment_type == "write_off":
            pass
        else:
            unmatched_adjustment_ids.append(adjustment.adjustment_id)
            continue
        approved_adjustments_by_invoice[invoice.invoice_id] += adjustment.amount
        _add_amount(adjustment_amounts_by_currency, adjustment.currency, adjustment.amount)
        _add_amount(adjustment_amounts_by_type_currency[adjustment.adjustment_type], adjustment.currency, adjustment.amount)

    total_invoice_by_currency: dict[str, Decimal] = {}
    applied_by_currency: dict[str, Decimal] = {}
    allowance_by_currency: dict[str, Decimal] = {}
    open_by_currency: dict[str, Decimal] = {}
    unapplied_by_currency: dict[str, Decimal] = {}
    disputed_open_by_currency: dict[str, Decimal] = {}
    aging_totals: dict[tuple[str, str], dict[str, Any]] = {
        (currency, bucket): {
            "currency": currency,
            "bucket": bucket,
            "invoice_count": 0,
            "open_amount": Decimal("0.00"),
            "risk_amount_excluding_disputed": Decimal("0.00"),
            "expected_credit_loss": Decimal("0.00"),
        }
        for currency in sorted({invoice.currency for invoice in active_invoices})
        for bucket in AGING_BUCKETS
    }
    reconciliation: list[dict[str, Any]] = []
    customer_rollup: dict[str, dict[str, Any]] = {}
    overpaid_invoice_ids: list[str] = []
    overpaid_amounts: dict[str, Decimal] = {}
    partial_invoice_ids: list[str] = []
    missing_due_date_invoice_ids: list[str] = []
    disputed_invoice_ids: list[str] = []
    term_mismatch_invoice_ids: list[str] = []
    missing_po_invoice_ids: list[str] = []
    over_credit_limit_customer_ids: list[str] = []

    for invoice in sorted(active_invoices, key=lambda item: item.invoice_id):
        _add_amount(total_invoice_by_currency, invoice.currency, invoice.amount)
        adjustment_amount = approved_adjustments_by_invoice.get(invoice.invoice_id, Decimal("0.00"))
        adjusted_invoice_amount = max(Decimal("0.00"), invoice.amount + adjustment_amount).quantize(MONEY_QUANT)
        raw_applied = applied_raw.get(invoice.invoice_id, Decimal("0.00"))
        applied = min(raw_applied, adjusted_invoice_amount)
        overpayment = max(Decimal("0.00"), raw_applied - adjusted_invoice_amount)
        open_amount = max(Decimal("0.00"), adjusted_invoice_amount - applied)
        disputed_open = min(open_amount, dispute_amounts.get(invoice.invoice_id, Decimal("0.00")))
        risk_open = max(Decimal("0.00"), open_amount - disputed_open)
        bucket = _aging_bucket(invoice.due_date, reference_date)
        days = _days_overdue(invoice.due_date, reference_date)
        expected_credit_loss = _loss_amount(risk_open, bucket, loss_rates)
        status = "overpaid" if overpayment > 0 else "closed" if open_amount == 0 else "open"
        tags: list[str] = []
        if adjustment_amount < 0:
            tags.append("approved_credit_memo")
        if adjustment_amount > 0:
            tags.append("chargeback")
        if invoice.invoice_id in set(pending_write_off_invoice_ids):
            tags.append("pending_write_off")
        if applied > 0 and open_amount > 0:
            tags.append("partial_payment")
            partial_invoice_ids.append(invoice.invoice_id)
        if overpayment > 0:
            tags.append("overpayment")
            overpaid_invoice_ids.append(invoice.invoice_id)
            unapplied_customer_ids.add(invoice.customer_id)
            _add_amount(overpaid_amounts, invoice.currency, overpayment)
            _add_amount(unapplied_by_currency, invoice.currency, overpayment)
        if disputed_open > 0:
            tags.append("disputed_invoice")
            disputed_invoice_ids.append(invoice.invoice_id)
        if bucket == "missing_due_date":
            tags.append("missing_due_date")
            missing_due_date_invoice_ids.append(invoice.invoice_id)
        if not invoice.po_number:
            tags.append("missing_po")
            missing_po_invoice_ids.append(invoice.invoice_id)
        due_date = _parse_date(invoice.due_date)
        invoice_date = _parse_date(invoice.invoice_date)
        terms = customer_terms.get(invoice.customer_id, 0)
        if due_date and invoice_date and terms:
            expected_due = invoice_date + timedelta(days=terms)
            if due_date != expected_due:
                tags.append("term_mismatch")
                term_mismatch_invoice_ids.append(invoice.invoice_id)

        _add_amount(applied_by_currency, invoice.currency, applied)
        _add_amount(open_by_currency, invoice.currency, open_amount)
        _add_amount(disputed_open_by_currency, invoice.currency, disputed_open)
        _add_amount(allowance_by_currency, invoice.currency, expected_credit_loss)
        if open_amount > 0:
            aging_key = (invoice.currency, bucket)
            aging_totals.setdefault(
                aging_key,
                {
                    "currency": invoice.currency,
                    "bucket": bucket,
                    "invoice_count": 0,
                    "open_amount": Decimal("0.00"),
                    "risk_amount_excluding_disputed": Decimal("0.00"),
                    "expected_credit_loss": Decimal("0.00"),
                },
            )
            aging_totals[aging_key]["invoice_count"] += 1
            aging_totals[aging_key]["open_amount"] += open_amount
            aging_totals[aging_key]["risk_amount_excluding_disputed"] += risk_open
            aging_totals[aging_key]["expected_credit_loss"] += expected_credit_loss

        reconciliation.append({
            "invoice_id": invoice.invoice_id,
            "customer_id": invoice.customer_id,
            "currency": invoice.currency,
            "invoice_amount": _money_float(invoice.amount),
            "approved_adjustment_amount": _money_float(adjustment_amount),
            "adjusted_invoice_amount": _money_float(adjusted_invoice_amount),
            "applied_amount": _money_float(applied),
            "open_amount": _money_float(open_amount),
            "overpayment_amount": _money_float(overpayment),
            "disputed_open_amount": _money_float(disputed_open),
            "expected_credit_loss": _money_float(expected_credit_loss),
            "due_date": invoice.due_date or None,
            "days_overdue": days,
            "aging_bucket": bucket,
            "status": status,
            "exception_tags": tags,
        })

        customer = customer_rollup.setdefault(
            invoice.customer_id,
            {
                "open": defaultdict(lambda: Decimal("0.00")),
                "overdue": defaultdict(lambda: Decimal("0.00")),
                "disputed": defaultdict(lambda: Decimal("0.00")),
                "risk_ex_disputed": defaultdict(lambda: Decimal("0.00")),
                "allowance": defaultdict(lambda: Decimal("0.00")),
                "max_days": 0,
                "invoice_ids": [],
                "tags": set(),
            },
        )
        customer["invoice_ids"].append(invoice.invoice_id)
        _add_amount(customer["open"], invoice.currency, open_amount)
        if days and days > 0:
            _add_amount(customer["overdue"], invoice.currency, open_amount)
            customer["max_days"] = max(customer["max_days"], days)
        _add_amount(customer["disputed"], invoice.currency, disputed_open)
        _add_amount(customer["risk_ex_disputed"], invoice.currency, risk_open)
        _add_amount(customer["allowance"], invoice.currency, expected_credit_loss)
        customer["tags"].update(tags)

    for payment in payments:
        if payment.payment_id in unapplied:
            _add_amount(unapplied_by_currency, payment.currency, payment.amount)

    customer_risk: list[dict[str, Any]] = []
    for customer_id, rollup in customer_rollup.items():
        customer = customers_by_id.get(customer_id, {})
        open_amounts = _amounts_to_float(dict(rollup["open"]))
        row = {
            "customer_id": customer_id,
            "customer_name": customer.get("customer_name", customer_id),
            "status": customer.get("status", "unknown"),
            "risk_band": "low",
            "open_amount_by_currency": open_amounts,
            "overdue_amount_by_currency": _amounts_to_float(dict(rollup["overdue"])),
            "disputed_open_amount_by_currency": _amounts_to_float(dict(rollup["disputed"])),
            "risk_amount_excluding_disputed_by_currency": _amounts_to_float(dict(rollup["risk_ex_disputed"])),
            "expected_credit_loss_by_currency": _amounts_to_float(dict(rollup["allowance"])),
            "max_days_overdue": int(rollup["max_days"]) if rollup["max_days"] else None,
            "action_tags": [],
            "rationale": [],
        }
        row["risk_band"] = _risk_band(row)
        tags = set(rollup["tags"])
        if row["max_days_overdue"] and row["max_days_overdue"] >= 90:
            row["action_tags"].append("collect_90_plus")
        elif row["max_days_overdue"] and row["max_days_overdue"] >= 31:
            row["action_tags"].append("collect_31_90")
        if "disputed_invoice" in tags:
            row["action_tags"].append("resolve_dispute")
        if "missing_due_date" in tags:
            row["action_tags"].append("fix_missing_due_date")
        if "missing_po" in tags:
            row["action_tags"].append("request_documentation")
        if "term_mismatch" in tags:
            row["action_tags"].append("fix_data_quality")
        if "chargeback" in tags:
            row["action_tags"].append("investigate_chargeback")
        if "pending_write_off" in tags:
            row["action_tags"].append("review_adjustment")
        if customer_id in unapplied_customer_ids:
            row["action_tags"].append("apply_unapplied_cash")
        if row["status"] != "active":
            row["action_tags"].append("review_customer_status")
        open_exposure = sum(Decimal(str(amount)) for amount in row["open_amount_by_currency"].values())
        if open_exposure > customer_credit_limits.get(customer_id, Decimal("0.00")) > 0:
            over_credit_limit_customer_ids.append(customer_id)
            row["action_tags"].append("review_credit_hold")
        row["rationale"] = [
            f"risk_band={row['risk_band']}",
            f"max_days_overdue={row['max_days_overdue']}",
            f"expected_credit_loss_by_currency={row['expected_credit_loss_by_currency']}",
            "disputed amounts are reported separately and excluded from risk_amount_excluding_disputed",
        ]
        customer_risk.append(row)

    exceptions = [
        _exception_row("duplicate_invoice", "warning", duplicate_invoice_ids, "Duplicate invoice rows are excluded after the first invoice_id occurrence."),
        _exception_row("duplicate_payment", "warning", duplicate_payment_ids, "Duplicate payment rows are excluded after the first payment_id occurrence."),
        _exception_row("partial_payment", "info", sorted(set(partial_invoice_ids)), "Invoices with posted payments but remaining open balance."),
        _exception_row("overpayment", "warning", sorted(set(overpaid_invoice_ids)), "Payments exceed invoice amount; excess is counted as unapplied cash.", overpaid_amounts),
        _exception_row("approved_credit_memo", "info", approved_credit_memo_ids, "Approved credit memos reduce open receivables.", adjustment_amounts_by_type_currency.get("credit_memo", {})),
        _exception_row("pending_write_off", "warning", pending_write_off_ids, "Pending write-off requests are reported but do not reduce open receivables."),
        _exception_row("chargeback", "critical", chargeback_ids, "Approved chargebacks increase open receivables and require payment investigation.", adjustment_amounts_by_type_currency.get("chargeback", {})),
        _exception_row("unapplied_cash", "warning", sorted(unapplied), "Payments without a valid matched invoice_id or with currency mismatch are unapplied cash.", unapplied_by_currency),
        _exception_row("currency_mismatch", "critical", currency_mismatch_payment_ids, "Payment currency differs from the matched invoice currency."),
        _exception_row("negative_invoice_amount", "critical", invalid_invoice_ids, "Negative invoice amounts are excluded from receivables reconciliation."),
        _exception_row("missing_due_date", "warning", sorted(set(missing_due_date_invoice_ids)), "Missing due dates are reported in a separate aging bucket."),
        _exception_row("disputed_invoice", "warning", sorted(set(disputed_invoice_ids)), "Open disputes remain in aging, with disputed open amount reported separately.", disputed_open_by_currency),
        _exception_row("future_dated_payment", "warning", future_dated_payment_ids, "Receipts after the reference date are excluded from current AR matching."),
        _exception_row("non_posted_payment", "warning", non_posted_payment_ids, "Voided or non-posted receipts do not reduce open receivables."),
        _exception_row("unmatched_adjustment", "critical", unmatched_adjustment_ids, "Adjustments with unknown invoice or currency mismatch are not applied."),
        _exception_row("over_credit_limit", "warning", sorted(set(over_credit_limit_customer_ids)), "Customer open exposure exceeds credit limit."),
        _exception_row("missing_po", "warning", sorted(set(missing_po_invoice_ids)), "Invoices missing purchase order evidence need documentation follow-up."),
        _exception_row("term_mismatch", "warning", sorted(set(term_mismatch_invoice_ids)), "Invoice due date does not match customer credit terms."),
    ]
    inactive_open = [
        row["customer_id"]
        for row in customer_risk
        if row["status"] != "active" and sum(row["open_amount_by_currency"].values()) > 0
    ]
    exceptions.append(_exception_row("inactive_or_on_hold_customer", "warning", inactive_open, "Customers not active but carrying open receivables."))

    actions: list[dict[str, Any]] = []
    for row in _sort_customer_risk(customer_risk):
        invoice_ids = customer_rollup[row["customer_id"]]["invoice_ids"]
        for tag in row["action_tags"]:
            action_type = {
                "collect_90_plus": "collect_overdue",
                "collect_31_90": "collect_overdue",
                "resolve_dispute": "resolve_dispute",
                "fix_missing_due_date": "fix_data_quality",
                "apply_unapplied_cash": "apply_unapplied_cash",
                "review_customer_status": "review_customer_status",
                "review_credit_hold": "review_credit_hold",
                "review_adjustment": "review_adjustment",
                "request_documentation": "request_documentation",
                "fix_data_quality": "fix_data_quality",
                "investigate_chargeback": "investigate_chargeback",
            }[tag]
            actions.append({
                "customer_id": row["customer_id"],
                "priority": _priority(row["risk_band"]),
                "action_type": action_type,
                "invoice_ids": invoice_ids,
                "details": f"{tag} for {row['customer_id']}",
            })

    report = {
        "summary": {
            "reference_date": reference_date.isoformat(),
            "base_currency": policy.get("base_currency", "USD"),
            "invoice_row_count": len(invoices_raw),
            "unique_invoice_count": len(invoice_rows),
            "duplicate_invoice_count": len(duplicate_invoice_ids),
            "payment_row_count": len(payments_raw),
            "duplicate_payment_count": len(duplicate_payment_ids),
            "total_invoice_amount_by_currency": _amounts_to_float(total_invoice_by_currency),
            "applied_payment_amount_by_currency": _amounts_to_float(applied_by_currency),
            "approved_adjustment_amount_by_currency": _amounts_to_float(adjustment_amounts_by_currency),
            "open_invoice_amount_by_currency": _amounts_to_float(open_by_currency),
            "unapplied_cash_amount_by_currency": _amounts_to_float(unapplied_by_currency),
            "disputed_open_amount_by_currency": _amounts_to_float(disputed_open_by_currency),
            "expected_credit_loss_by_currency": _amounts_to_float(allowance_by_currency),
        },
        "customer_risk": _sort_customer_risk(customer_risk),
        "invoice_reconciliation": reconciliation,
        "aging_buckets": [
            {
                "currency": value["currency"],
                "bucket": value["bucket"],
                "invoice_count": int(value["invoice_count"]),
                "open_amount": _money_float(value["open_amount"].quantize(MONEY_QUANT)),
                "risk_amount_excluding_disputed": _money_float(value["risk_amount_excluding_disputed"].quantize(MONEY_QUANT)),
                "expected_credit_loss": _money_float(value["expected_credit_loss"].quantize(MONEY_QUANT)),
            }
            for _key, value in sorted(aging_totals.items(), key=lambda item: (item[0][0], AGING_BUCKETS.index(item[0][1])))
        ],
        "exceptions": exceptions,
        "recommended_actions": actions,
        "data_quality": {
            "required_columns": required,
            "missing_required_columns": missing_required,
            "duplicate_invoice_ids": duplicate_invoice_ids,
            "duplicate_payment_ids": duplicate_payment_ids,
            "invalid_invoice_ids": invalid_invoice_ids,
            "unmatched_payment_ids": unmatched_payment_ids,
            "currency_mismatch_payment_ids": currency_mismatch_payment_ids,
            "missing_due_date_invoice_ids": sorted(set(missing_due_date_invoice_ids)),
            "future_dated_payment_ids": future_dated_payment_ids,
            "non_posted_payment_ids": non_posted_payment_ids,
            "unmatched_adjustment_ids": unmatched_adjustment_ids,
            "term_mismatch_invoice_ids": sorted(set(term_mismatch_invoice_ids)),
            "missing_po_invoice_ids": sorted(set(missing_po_invoice_ids)),
            "over_credit_limit_customer_ids": sorted(set(over_credit_limit_customer_ids)),
        },
        "audit_notes": [
            {"step": "invoice_deduplication", "evidence": "Deduplicated by invoice_id and kept the first row."},
            {"step": "payment_matching", "evidence": "Matched payments by invoice_id first; missing or unknown invoice_id is unapplied cash."},
            {"step": "aging", "evidence": f"Computed overdue days against reference_date={reference_date.isoformat()}."},
            {"step": "disputes", "evidence": "Open disputes remain in aging and are separated in disputed_open_amount_by_currency."},
            {"step": "provision_matrix", "evidence": "Expected credit loss uses policy loss rates on risk_amount_excluding_disputed."},
        ],
        "validation": {"passed": True, "checks": {}},
    }
    expected_path = task_path / "expected.json"
    if expected_path.exists():
        report["validation"] = _validate_report(report, _read_json(expected_path))
    return report


def run_finance_operations(
    task_dir: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    report = build_finance_operations_report(task_dir)
    if output_path:
        Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
