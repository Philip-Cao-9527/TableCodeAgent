"""
solve.py — finance_operations_001 No-Helper Workflow
Reads CSV tables, processes AR reconciliation, aging, ECL,
customer risk, exceptions, actions, and writes answer.json.
"""
import json
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

import pandas as pd

HERE = Path(__file__).resolve().parent


# ── helpers ──────────────────────────────────────────────────────────────
def r2(v: Decimal | float | str) -> float:
    """Round to 2 decimal places as a native float."""
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_date(val: str) -> date | None:
    if not val or pd.isna(val):
        return None
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def bucket_name(days_overdue: int | None) -> str:
    if days_overdue is None:
        return "missing_due_date"
    if days_overdue <= 0:
        return "not_due"
    if days_overdue <= 30:
        return "0-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def sum_cur(d: list[dict]) -> dict[str, float]:
    """Sum amount_by_currency dicts."""
    out: dict[str, float] = {}
    for item in d:
        for ccy, val in item.items():
            out[ccy] = r2(out.get(ccy, 0) + val)
    return out


BUCKET_ORDER = {"not_due": 0, "0-30": 1, "31-60": 2, "61-90": 3, "90+": 4, "missing_due_date": 5}

LOSS_RATE_KEYS = {
    "not_due": "loss_rate_not_due",
    "0-30": "loss_rate_0_30",
    "31-60": "loss_rate_31_60",
    "61-90": "loss_rate_61_90",
    "90+": "loss_rate_90_plus",
    "missing_due_date": "loss_rate_missing_due_date",
}


# ── load data ────────────────────────────────────────────────────────────
invoices_raw = pd.read_csv(HERE / "invoices.csv", dtype=str)
payments_raw = pd.read_csv(HERE / "payments.csv", dtype=str)
customers_raw = pd.read_csv(HERE / "customers.csv", dtype=str)
disputes_raw = pd.read_csv(HERE / "disputes.csv", dtype=str)
adjustments_raw = pd.read_csv(HERE / "adjustments.csv", dtype=str)
policy_row = pd.read_csv(HERE / "policy.csv", dtype=str).iloc[0]

REFERENCE_DATE = parse_date(policy_row["reference_date"])
BASE_CCY = str(policy_row["base_currency"])
LOSS_RATES = {bkt: Decimal(str(policy_row[key])) for bkt, key in LOSS_RATE_KEYS.items()}

# ── required columns check ──────────────────────────────────────────────
REQUIRED_COLS = {
    "invoices": ["invoice_id", "customer_id", "invoice_date", "due_date", "invoice_amount", "currency", "status", "po_number", "delivery_status", "billing_hold_flag"],
    "payments": ["payment_id", "customer_id", "invoice_id", "payment_date", "gl_date", "payment_amount", "currency", "status", "bank_deposit_id", "remittance_reference"],
    "customers": ["customer_id", "customer_name", "segment", "status", "credit_terms_days", "credit_limit", "default_currency", "collector_owner"],
    "disputes": ["dispute_id", "invoice_id", "customer_id", "opened_date", "dispute_amount", "currency", "reason", "status"],
    "adjustments": ["adjustment_id", "invoice_id", "customer_id", "adjustment_type", "adjustment_date", "amount", "currency", "status", "reason"],
    "policy": ["policy_id", "reference_date", "base_currency", "amount_precision", "loss_rate_not_due", "loss_rate_0_30", "loss_rate_31_60", "loss_rate_61_90", "loss_rate_90_plus", "loss_rate_missing_due_date", "write_off_approval_threshold", "dispute_risk_rule", "aging_bucket_rule"],
}
missing_req: dict[str, list[str]] = {}
for tbl, cols in REQUIRED_COLS.items():
    df_map = {
        "invoices": invoices_raw, "payments": payments_raw, "customers": customers_raw,
        "disputes": disputes_raw, "adjustments": adjustments_raw, "policy": pd.DataFrame([policy_row]),
    }
    present = set(df_map[tbl].columns)
    missing_req[tbl] = [c for c in cols if c not in present]

# ── customer index ──────────────────────────────────────────────────────
customers: dict[str, dict] = {}
for _, r in customers_raw.iterrows():
    cid = str(r["customer_id"])
    customers[cid] = {
        "customer_id": cid,
        "customer_name": str(r.get("customer_name", "")),
        "segment": str(r.get("segment", "")),
        "status": str(r.get("status", "")),
        "credit_terms_days": int(float(str(r.get("credit_terms_days", 0)))),
        "credit_limit": Decimal(str(r.get("credit_limit", "0"))),
        "default_currency": str(r.get("default_currency", BASE_CCY)),
        "collector_owner": str(r.get("collector_owner", "")),
    }

# ── invoices: dedup, negative exclusion ─────────────────────────────────
invoice_rows = invoices_raw.to_dict("records")
seen_inv: set[str] = set()
deduped_invoices: list[dict] = []
dup_inv_ids: list[str] = []
neg_inv_ids: list[str] = []

for row in invoice_rows:
    iid = str(row["invoice_id"])
    if iid in seen_inv:
        dup_inv_ids.append(iid)
        continue
    seen_inv.add(iid)
    amt = Decimal(str(row.get("invoice_amount", "0")))
    if amt < 0:
        neg_inv_ids.append(iid)
        row["_excluded"] = True
    else:
        row["_excluded"] = False
    deduped_invoices.append(row)

inv_index: dict[str, dict] = {str(r["invoice_id"]): r for r in deduped_invoices}

# ── payments: dedup, filter posted/dated, classify ─────────────────────
payment_rows = payments_raw.to_dict("records")
seen_pay: set[str] = set()
deduped_payments: list[dict] = []
dup_pay_ids: list[str] = []

for row in payment_rows:
    pid = str(row["payment_id"])
    if pid in seen_pay:
        dup_pay_ids.append(pid)
        continue
    seen_pay.add(pid)
    deduped_payments.append(row)

future_pay_ids: list[str] = []
non_posted_pay_ids: list[str] = []
currency_mismatch_pay_ids: list[str] = []
unmatched_pay_ids: list[str] = []
applied_payments: list[dict] = []   # payments that get applied to invoices
unapplied_payments: list[dict] = []  # cash that cannot be applied

for row in deduped_payments:
    pid = str(row["payment_id"])
    status = str(row.get("status", ""))
    pay_date = parse_date(str(row.get("payment_date", "")))
    gl_date = parse_date(str(row.get("gl_date", "")))
    pay_ccy = str(row.get("currency", ""))
    inv_id = str(row.get("invoice_id", "")).strip()
    pay_amt = Decimal(str(row.get("payment_amount", "0")))

    # non-posted
    if status != "posted":
        non_posted_pay_ids.append(pid)
        row["_applied"] = False
        row["_reason"] = "non_posted"
        continue

    # future-dated (payment_date or gl_date after reference)
    if (pay_date and pay_date > REFERENCE_DATE) or (gl_date and gl_date > REFERENCE_DATE):
        future_pay_ids.append(pid)
        row["_applied"] = False
        row["_reason"] = "future_dated"
        continue

    # Try to match to an invoice
    if not inv_id or inv_id not in inv_index or inv_index[inv_id].get("_excluded", False):
        unmatched_pay_ids.append(pid)
        unapplied_payments.append(row)
        row["_applied"] = False
        row["_reason"] = "no_valid_invoice"
        continue

    inv_row = inv_index[inv_id]
    inv_ccy = str(inv_row["currency"])
    if pay_ccy != inv_ccy:
        currency_mismatch_pay_ids.append(pid)
        unapplied_payments.append(row)
        row["_applied"] = False
        row["_reason"] = "currency_mismatch"
        continue

    # Valid posted, on-time, matching invoice
    row["_applied"] = True
    applied_payments.append(row)

# ── adjustments ─────────────────────────────────────────────────────────
adj_rows = adjustments_raw.to_dict("records")
approved_credit_memo_adjs: list[dict] = []
approved_chargeback_adjs: list[dict] = []
pending_writeoff_adjs: list[dict] = []
unmatched_adj_ids: list[str] = []

for row in adj_rows:
    aid = str(row["adjustment_id"])
    inv_id = str(row.get("invoice_id", "")).strip()
    adj_type = str(row.get("adjustment_type", ""))
    adj_status = str(row.get("status", ""))
    adj_amt = Decimal(str(row.get("amount", "0")))

    if inv_id not in inv_index or inv_index[inv_id].get("_excluded", False):
        unmatched_adj_ids.append(aid)
        row["_applied"] = False
        continue

    row["_applied"] = True
    if adj_status == "approved":
        if adj_type == "credit_memo":
            approved_credit_memo_adjs.append(row)
        elif adj_type == "write_off":
            # approved write_off reduces
            approved_credit_memo_adjs.append(row)  # treat same as credit_memo for balance
        elif adj_type == "chargeback":
            approved_chargeback_adjs.append(row)
        else:
            row["_applied"] = False
            unmatched_adj_ids.append(aid)
    elif adj_status == "pending" and adj_type == "write_off":
        pending_writeoff_adjs.append(row)
    else:
        unmatched_adj_ids.append(aid)
        row["_applied"] = False

# ── disputes ────────────────────────────────────────────────────────────
disputes_by_invoice: dict[str, list[dict]] = defaultdict(list)
for _, r in disputes_raw.iterrows():
    inv_id = str(r["invoice_id"])
    if str(r.get("status", "")).strip().lower() == "open":
        disputes_by_invoice[inv_id].append(r)

# ── build invoice reconciliation ────────────────────────────────────────
inv_rec: list[dict] = []
total_inv_amt: dict[str, Decimal] = defaultdict(Decimal)
total_applied: dict[str, Decimal] = defaultdict(Decimal)
total_adj_approved: dict[str, Decimal] = defaultdict(Decimal)
total_open: dict[str, Decimal] = defaultdict(Decimal)
total_disputed_open: dict[str, Decimal] = defaultdict(Decimal)
total_unapplied: dict[str, Decimal] = defaultdict(Decimal)
# add overpayment excess to unapplied
total_ecl: dict[str, Decimal] = defaultdict(Decimal)

# Track over_credit_limit
cust_open_exposure: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

for row in deduped_invoices:
    iid = str(row["invoice_id"])
    cid = str(row["customer_id"])
    ccy = str(row["currency"])
    amt = Decimal(str(row["invoice_amount"]))
    due_str = str(row.get("due_date", "")).strip()

    if row.get("_excluded", False):
        # Still report as excluded
        due_d = parse_date(due_str)
        days_over = (REFERENCE_DATE - due_d).days if due_d else None
        inv_rec.append({
            "invoice_id": iid,
            "customer_id": cid,
            "currency": ccy,
            "invoice_amount": r2(amt),
            "approved_adjustment_amount": 0.0,
            "adjusted_invoice_amount": 0.0,
            "applied_amount": 0.0,
            "open_amount": 0.0,
            "overpayment_amount": 0.0,
            "disputed_open_amount": 0.0,
            "expected_credit_loss": 0.0,
            "due_date": due_str if due_str else None,
            "days_overdue": days_over,
            "aging_bucket": bucket_name(days_over),
            "status": "excluded",
            "exception_tags": ["negative_invoice_amount"],
        })
        continue

    total_inv_amt[ccy] += amt

    # due date
    due_d = parse_date(due_str)
    if due_d:
        days_over = (REFERENCE_DATE - due_d).days
    else:
        days_over = None

    # adjustments
    adj_total = Decimal("0")
    for a in approved_credit_memo_adjs:
        if str(a["invoice_id"]) == iid:
            adj_total += Decimal(str(a["amount"]))  # credit_memo/write_off amounts are negative
    for a in approved_chargeback_adjs:
        if str(a["invoice_id"]) == iid:
            adj_total += Decimal(str(a["amount"]))  # chargeback amounts are positive

    adjusted_amt = amt + adj_total

    # payments
    pay_total = Decimal("0")
    overpayment_amt = Decimal("0")
    for p in applied_payments:
        if str(p["invoice_id"]) == iid:
            pay_total += Decimal(str(p["payment_amount"]))

    applied_amt = min(pay_total, adjusted_amt)
    overpayment_amt = max(Decimal("0"), pay_total - adjusted_amt) if pay_total > adjusted_amt else Decimal("0")
    open_amt = adjusted_amt - applied_amt

    # overpayment goes to unapplied cash
    if overpayment_amt > 0:
        total_unapplied[ccy] += overpayment_amt

    # disputes on this invoice
    open_disp = disputes_by_invoice.get(iid, [])
    total_dispute_amt = Decimal("0")
    for d in open_disp:
        total_dispute_amt += Decimal(str(d["dispute_amount"]))
    disputed_open_amt = min(total_dispute_amt, open_amt) if open_amt > 0 else Decimal("0")

    # ECL on risk amount (open - disputed)
    risk_excl_disp = open_amt - disputed_open_amt
    bkt = bucket_name(days_over)
    loss_rate = LOSS_RATES.get(bkt, Decimal("0"))
    ecl = (risk_excl_disp * loss_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # status
    if open_amt == 0 and overpayment_amt > 0:
        inv_status = "overpaid"
    elif open_amt == 0:
        inv_status = "closed"
    else:
        inv_status = "open"

    # exception tags
    exc_tags = []
    if overpayment_amt > 0:
        exc_tags.append("overpayment")
    if pay_total > 0 and open_amt > 0 and pay_total < adjusted_amt:
        exc_tags.append("partial_payment")
    if disputed_open_amt > 0:
        exc_tags.append("disputed_invoice")
    if days_over is None:
        exc_tags.append("missing_due_date")
    if not str(row.get("po_number", "")).strip():
        exc_tags.append("missing_po")
    # term mismatch
    cust = customers.get(cid)
    if cust and due_d:
        inv_date = parse_date(str(row["invoice_date"]))
        if inv_date:
            expected_due = date.fromordinal(inv_date.toordinal() + cust["credit_terms_days"])
            if due_d != expected_due:
                exc_tags.append("term_mismatch")

    inv_rec.append({
        "invoice_id": iid,
        "customer_id": cid,
        "currency": ccy,
        "invoice_amount": r2(amt),
        "approved_adjustment_amount": r2(adj_total),
        "adjusted_invoice_amount": r2(adjusted_amt),
        "applied_amount": r2(applied_amt),
        "open_amount": r2(open_amt),
        "overpayment_amount": r2(overpayment_amt),
        "disputed_open_amount": r2(disputed_open_amt),
        "expected_credit_loss": float(ecl),
        "due_date": due_str if due_str else None,
        "days_overdue": days_over,
        "aging_bucket": bkt,
        "status": inv_status,
        "exception_tags": list(dict.fromkeys(exc_tags)),
    })

    total_applied[ccy] += applied_amt
    total_adj_approved[ccy] += adj_total
    total_open[ccy] += open_amt
    total_disputed_open[ccy] += disputed_open_amt
    total_ecl[ccy] += ecl

    cust_open_exposure[cid][ccy] += open_amt

# ── unapplied cash from payments ────────────────────────────────────────
for p in unapplied_payments:
    ccy = str(p["currency"])
    amt = Decimal(str(p["payment_amount"]))
    total_unapplied[ccy] += amt

# ── customer risk (only customers that exist) ───────────────────────────
# Also include C005 (Echo Foods) with INV-1007 excluded → no open AR
cust_risk_rows: list[dict] = []

for cid_sort, cust in sorted(customers.items()):
    cid = cid_sort
    cname = cust["customer_name"]
    cstatus = cust["status"]
    climit = cust["credit_limit"]

    # Find invoices for this customer
    cust_invs = [r for r in inv_rec if r["customer_id"] == cid and r["status"] != "excluded"]
    open_by_ccy: dict[str, float] = {}
    overdue_by_ccy: dict[str, float] = {}
    disputed_by_ccy: dict[str, float] = {}
    risk_excl_disp_by_ccy: dict[str, float] = {}
    ecl_by_ccy: dict[str, float] = {}
    max_days = None
    has_90plus = False
    has_31_90 = False
    has_dispute = False
    has_missing_due = False
    has_over_credit = False
    has_unapplied = False
    has_chargeback = False

    for r in cust_invs:
        ccy = r["currency"]
        oa = r["open_amount"]
        open_by_ccy[ccy] = r2(open_by_ccy.get(ccy, 0) + oa)

        if r["days_overdue"] is not None and r["days_overdue"] > 0:
            overdue_by_ccy[ccy] = r2(overdue_by_ccy.get(ccy, 0) + oa)
            if max_days is None or r["days_overdue"] > max_days:
                max_days = r["days_overdue"]

        if r["days_overdue"] is not None and r["days_overdue"] >= 91:
            has_90plus = True
        if r["days_overdue"] is not None and 31 <= r["days_overdue"] <= 90:
            has_31_90 = True
        if r["disputed_open_amount"] > 0:
            has_dispute = True
            disputed_by_ccy[ccy] = r2(disputed_by_ccy.get(ccy, 0) + r["disputed_open_amount"])

        risk_excl = r["open_amount"] - r["disputed_open_amount"]
        risk_excl_disp_by_ccy[ccy] = r2(risk_excl_disp_by_ccy.get(ccy, 0) + risk_excl)

        ecl_by_ccy[ccy] = r2(ecl_by_ccy.get(ccy, 0) + r["expected_credit_loss"])

        if "missing_due_date" in r["exception_tags"]:
            has_missing_due = True
        if "missing_po" in r["exception_tags"]:
            pass  # handled per-invoice

    # Check chargeback adjustments for this customer
    for a in approved_chargeback_adjs:
        if str(a["customer_id"]) == cid:
            has_chargeback = True

    # Check unapplied cash
    for p in unapplied_payments:
        if str(p.get("customer_id", "")) == cid:
            has_unapplied = True

    # Over credit limit check
    for ccy, exposure in cust_open_exposure.get(cid, {}).items():
        if exposure > 0:
            # Compare exposure to credit limit (in the customer's default currency context)
            # The contract says "exceeds customer.credit_limit"
            if Decimal(str(exposure)) > climit:
                has_over_credit = True

    total_open_amt = r2(sum(open_by_ccy.values()))

    # Also check if over_credit_limit more carefully: compare total open in each currency
    # Actually the contract says open exposure in its invoice currencies exceeds credit_limit
    # The credit_limit is a single number in the customer's default currency
    # For simplicity, compare total open USD equivalent (but we don't convert currencies)
    # Since amounts are in original currency, just compare to credit limit per currency
    # The practical approach: for each currency the customer has open, if total > credit_limit
    # Actually let me check properly: cust_open_exposure stores per currency.
    # If customer's main/default currency open exceeds limit.
    default_ccy = cust["default_currency"]
    exposure_in_default = cust_open_exposure[cid].get(default_ccy, Decimal("0"))
    if exposure_in_default > climit:
        has_over_credit = True
    # Also check any currency
    for ccy_key, exp_val in cust_open_exposure[cid].items():
        if Decimal(str(exp_val)) > climit:
            has_over_credit = True

    # risk band
    if cstatus != "active" and total_open_amt > 0:
        risk_band = "high"
    elif has_90plus:
        risk_band = "high"
    elif has_over_credit:
        risk_band = "high"
    elif has_31_90:
        risk_band = "medium"
    elif has_dispute:
        risk_band = "medium"
    elif total_open_amt > 0:
        risk_band = "low"
    else:
        risk_band = "low"

    # action tags
    action_tags = []
    rationales = []
    if has_90plus:
        action_tags.append("collect_90_plus")
        rationales.append("Customer has invoices 90+ days overdue")
    if has_31_90:
        action_tags.append("collect_31_90")
        rationales.append("Customer has invoices 31-90 days overdue")
    if has_dispute:
        action_tags.append("resolve_dispute")
        rationales.append("Customer has open disputed amount")
    if has_missing_due:
        action_tags.append("fix_missing_due_date")
        rationales.append("Customer has invoices with missing due dates")
    if has_unapplied:
        action_tags.append("apply_unapplied_cash")
        rationales.append("Customer has unapplied cash")
    if cstatus != "active" and total_open_amt > 0:
        action_tags.append("review_customer_status")
        rationales.append(f"Customer status is '{cstatus}' with open receivables")
    if has_over_credit:
        action_tags.append("review_credit_hold")
        rationales.append("Customer open exposure exceeds credit limit")
    if has_chargeback:
        action_tags.append("investigate_chargeback")
        rationales.append("Customer has approved chargeback adjustments")
    # pending write-off for customer
    for a in pending_writeoff_adjs:
        if str(a["customer_id"]) == cid:
            action_tags.append("review_adjustment")
            rationales.append("Customer has pending write-off adjustments")
    # missing PO
    po_missing_invs = [r["invoice_id"] for r in cust_invs if "missing_po" in r["exception_tags"]]
    if po_missing_invs:
        action_tags.append("request_documentation")
        rationales.append("Customer invoices missing PO numbers")

    # Deduplicate action_tags preserving order
    seen_tags = set()
    deduped_tags = []
    for t in action_tags:
        if t not in seen_tags:
            seen_tags.add(t)
            deduped_tags.append(t)

    cust_risk_rows.append({
        "customer_id": cid,
        "customer_name": cname,
        "status": cstatus,
        "risk_band": risk_band,
        "open_amount_by_currency": {k: r2(v) for k, v in open_by_ccy.items()},
        "overdue_amount_by_currency": {k: r2(v) for k, v in overdue_by_ccy.items()},
        "disputed_open_amount_by_currency": {k: r2(v) for k, v in disputed_by_ccy.items()},
        "risk_amount_excluding_disputed_by_currency": {k: r2(v) for k, v in risk_excl_disp_by_ccy.items()},
        "expected_credit_loss_by_currency": {k: r2(v) for k, v in ecl_by_ccy.items()},
        "max_days_overdue": max_days,
        "action_tags": deduped_tags,
        "rationale": rationales,
    })

# ── aging buckets ───────────────────────────────────────────────────────
aging_data: dict[tuple[str, str], dict] = defaultdict(lambda: {"invoice_count": 0, "open_amount": Decimal("0"), "risk_excl_disp": Decimal("0"), "ecl": Decimal("0")})

for r in inv_rec:
    if r["status"] == "excluded":
        continue
    ccy = r["currency"]
    bkt = r["aging_bucket"]
    key = (ccy, bkt)
    aging_data[key]["invoice_count"] += 1
    aging_data[key]["open_amount"] += Decimal(str(r["open_amount"]))
    risk_excl = Decimal(str(r["open_amount"])) - Decimal(str(r["disputed_open_amount"]))
    aging_data[key]["risk_excl_disp"] += max(Decimal("0"), risk_excl)
    aging_data[key]["ecl"] += Decimal(str(r["expected_credit_loss"]))

aging_rows: list[dict] = []
for (ccy, bkt), vals in aging_data.items():
    loss_rate = LOSS_RATES.get(bkt, Decimal("0"))
    # Recompute ECL at bucket level from risk_excl_disp * loss_rate
    bucket_ecl = (vals["risk_excl_disp"] * loss_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    aging_rows.append({
        "currency": ccy,
        "bucket": bkt,
        "invoice_count": vals["invoice_count"],
        "open_amount": r2(vals["open_amount"]),
        "risk_amount_excluding_disputed": r2(vals["risk_excl_disp"]),
        "expected_credit_loss": float(bucket_ecl),
    })

# Sort aging: currency then bucket order
aging_rows.sort(key=lambda x: (x["currency"], BUCKET_ORDER.get(x["bucket"], 99)))

# ── exceptions ──────────────────────────────────────────────────────────
exceptions_list: list[dict] = []

def add_exc(etype: str, severity: str, count: int, amt_by_ccy: dict[str, float], ids: list[str], desc: str):
    exceptions_list.append({
        "exception_type": etype,
        "severity": severity,
        "count": count,
        "amount_by_currency": amt_by_ccy,
        "related_ids": ids,
        "description": desc,
    })

# duplicate_invoice
if dup_inv_ids:
    add_exc("duplicate_invoice", "warning", len(dup_inv_ids), {}, list(dict.fromkeys(dup_inv_ids)),
            f"Duplicate invoice_id rows found: {', '.join(dict.fromkeys(dup_inv_ids))}")

# duplicate_payment
if dup_pay_ids:
    add_exc("duplicate_payment", "warning", len(dup_pay_ids), {}, list(dict.fromkeys(dup_pay_ids)),
            f"Duplicate payment_id rows found: {', '.join(dict.fromkeys(dup_pay_ids))}")

# partial payments
partial_invs = [r for r in inv_rec if "partial_payment" in r["exception_tags"]]
if partial_invs:
    total_partial_amt = r2(sum(Decimal(str(r["open_amount"])) for r in partial_invs))
    by_ccy: dict[str, float] = {}
    for r in partial_invs:
        by_ccy[r["currency"]] = r2(by_ccy.get(r["currency"], 0) + r["open_amount"])
    add_exc("partial_payment", "info", len(partial_invs), by_ccy, [r["invoice_id"] for r in partial_invs],
            f"Invoices with partial payments: {len(partial_invs)}")

# overpayments
overpaid_invs = [r for r in inv_rec if r["overpayment_amount"] > 0]
if overpaid_invs:
    by_ccy_over: dict[str, float] = {}
    for r in overpaid_invs:
        by_ccy_over[r["currency"]] = r2(by_ccy_over.get(r["currency"], 0) + r["overpayment_amount"])
    add_exc("overpayment", "info", len(overpaid_invs), by_ccy_over, [r["invoice_id"] for r in overpaid_invs],
            f"Overpaid invoices: {len(overpaid_invs)}")

# approved_credit_memo
if approved_credit_memo_adjs:
    by_ccy_cm: dict[str, float] = defaultdict(float)
    cm_ids = []
    for a in approved_credit_memo_adjs:
        ccy = str(a["currency"])
        amt = abs(float(a["amount"]))
        by_ccy_cm[ccy] = r2(by_ccy_cm.get(ccy, 0) + amt)
        cm_ids.append(str(a["adjustment_id"]))
    add_exc("approved_credit_memo", "info", len(approved_credit_memo_adjs), by_ccy_cm, cm_ids,
            f"Approved credit memo / write-off adjustments applied: {len(approved_credit_memo_adjs)}")

# pending_write_off
if pending_writeoff_adjs:
    by_ccy_pw: dict[str, float] = defaultdict(float)
    pw_ids = []
    for a in pending_writeoff_adjs:
        ccy = str(a["currency"])
        by_ccy_pw[ccy] = r2(by_ccy_pw.get(ccy, 0) + abs(float(a["amount"])))
        pw_ids.append(str(a["adjustment_id"]))
    add_exc("pending_write_off", "warning", len(pending_writeoff_adjs), by_ccy_pw, pw_ids,
            f"Pending write-off adjustments (not reducing AR): {len(pending_writeoff_adjs)}")

# chargeback
if approved_chargeback_adjs:
    by_ccy_cb: dict[str, float] = defaultdict(float)
    cb_ids = []
    for a in approved_chargeback_adjs:
        ccy = str(a["currency"])
        by_ccy_cb[ccy] = r2(by_ccy_cb.get(ccy, 0) + abs(float(a["amount"])))
        cb_ids.append(str(a["adjustment_id"]))
    add_exc("chargeback", "warning", len(approved_chargeback_adjs), by_ccy_cb, cb_ids,
            f"Approved chargeback adjustments increasing AR: {len(approved_chargeback_adjs)}")

# unapplied_cash
unapplied_amt_by_ccy: dict[str, float] = {}
unapplied_ids = []
for p in unapplied_payments:
    ccy = str(p["currency"])
    unapplied_amt_by_ccy[ccy] = r2(unapplied_amt_by_ccy.get(ccy, 0) + float(p["payment_amount"]))
    unapplied_ids.append(str(p["payment_id"]))
# Add overpayment excess
for r in overpaid_invs:
    ccy = r["currency"]
    unapplied_amt_by_ccy[ccy] = r2(unapplied_amt_by_ccy.get(ccy, 0) + r["overpayment_amount"])
if unapplied_amt_by_ccy:
    add_exc("unapplied_cash", "warning", len(unapplied_payments) + len(overpaid_invs),
            unapplied_amt_by_ccy, unapplied_ids,
            f"Unapplied cash from unmatched/currency-mismatch/overpayments: {len(unapplied_payments)+len(overpaid_invs)}")

# currency_mismatch
if currency_mismatch_pay_ids:
    by_ccy_mm: dict[str, float] = defaultdict(float)
    for p in deduped_payments:
        if str(p["payment_id"]) in currency_mismatch_pay_ids:
            by_ccy_mm[str(p["currency"])] = r2(by_ccy_mm.get(str(p["currency"]), 0) + float(p["payment_amount"]))
    add_exc("currency_mismatch", "warning", len(currency_mismatch_pay_ids), by_ccy_mm,
            currency_mismatch_pay_ids,
            f"Payments with currency mismatch to invoice: {len(currency_mismatch_pay_ids)}")

# negative_invoice_amount
if neg_inv_ids:
    by_ccy_neg: dict[str, float] = {}
    for row in deduped_invoices:
        if str(row["invoice_id"]) in neg_inv_ids:
            by_ccy_neg[str(row["currency"])] = r2(by_ccy_neg.get(str(row["currency"]), 0) + abs(float(row["invoice_amount"])))
    add_exc("negative_invoice_amount", "critical", len(neg_inv_ids), by_ccy_neg, neg_inv_ids,
            f"Invoices with negative amounts excluded from AR: {len(neg_inv_ids)}")

# missing_due_date
missing_dd_invs = [r for r in inv_rec if r["days_overdue"] is None and r["status"] != "excluded"]
if missing_dd_invs:
    by_ccy_mdd: dict[str, float] = {}
    for r in missing_dd_invs:
        by_ccy_mdd[r["currency"]] = r2(by_ccy_mdd.get(r["currency"], 0) + r["open_amount"])
    add_exc("missing_due_date", "warning", len(missing_dd_invs), by_ccy_mdd,
            [r["invoice_id"] for r in missing_dd_invs],
            f"Invoices missing due dates: {len(missing_dd_invs)}")

# disputed_invoice
disputed_invs = [r for r in inv_rec if r["disputed_open_amount"] > 0]
if disputed_invs:
    by_ccy_disp: dict[str, float] = {}
    for r in disputed_invs:
        by_ccy_disp[r["currency"]] = r2(by_ccy_disp.get(r["currency"], 0) + r["disputed_open_amount"])
    add_exc("disputed_invoice", "warning", len(disputed_invs), by_ccy_disp,
            [r["invoice_id"] for r in disputed_invs],
            f"Invoices with open disputes: {len(disputed_invs)}")

# inactive_or_on_hold_customer
inactive_custs_with_ar = []
for r in cust_risk_rows:
    if r["status"] != "active" and sum(r["open_amount_by_currency"].values()) > 0:
        inactive_custs_with_ar.append(r)
if inactive_custs_with_ar:
    by_ccy_ia: dict[str, float] = {}
    for r in inactive_custs_with_ar:
        for ccy, amt in r["open_amount_by_currency"].items():
            by_ccy_ia[ccy] = r2(by_ccy_ia.get(ccy, 0) + amt)
    add_exc("inactive_or_on_hold_customer", "critical", len(inactive_custs_with_ar), by_ccy_ia,
            [r["customer_id"] for r in inactive_custs_with_ar],
            f"Customers with inactive/on-hold status carrying open AR: {len(inactive_custs_with_ar)}")

# future_dated_payment
if future_pay_ids:
    by_ccy_fd: dict[str, float] = defaultdict(float)
    for p in deduped_payments:
        if str(p["payment_id"]) in future_pay_ids:
            by_ccy_fd[str(p["currency"])] = r2(by_ccy_fd.get(str(p["currency"]), 0) + float(p["payment_amount"]))
    add_exc("future_dated_payment", "warning", len(future_pay_ids), by_ccy_fd, future_pay_ids,
            f"Future-dated payments not applied: {len(future_pay_ids)}")

# non_posted_payment
if non_posted_pay_ids:
    by_ccy_np: dict[str, float] = defaultdict(float)
    for p in deduped_payments:
        if str(p["payment_id"]) in non_posted_pay_ids:
            by_ccy_np[str(p["currency"])] = r2(by_ccy_np.get(str(p["currency"]), 0) + float(p["payment_amount"]))
    add_exc("non_posted_payment", "warning", len(non_posted_pay_ids), by_ccy_np, non_posted_pay_ids,
            f"Non-posted (voided/reversed) payments: {len(non_posted_pay_ids)}")

# unmatched_adjustment
if unmatched_adj_ids:
    by_ccy_ua: dict[str, float] = defaultdict(float)
    for a in adj_rows:
        if str(a["adjustment_id"]) in unmatched_adj_ids:
            by_ccy_ua[str(a["currency"])] = r2(by_ccy_ua.get(str(a["currency"]), 0) + abs(float(a["amount"])))
    add_exc("unmatched_adjustment", "warning", len(unmatched_adj_ids), by_ccy_ua, unmatched_adj_ids,
            f"Adjustments with no matching invoice: {len(unmatched_adj_ids)}")

# over_credit_limit
over_limit_custs = [r for r in cust_risk_rows if "review_credit_hold" in r["action_tags"]]
if over_limit_custs:
    by_ccy_ol: dict[str, float] = {}
    for r in over_limit_custs:
        for ccy, amt in r["open_amount_by_currency"].items():
            by_ccy_ol[ccy] = r2(by_ccy_ol.get(ccy, 0) + amt)
    add_exc("over_credit_limit", "critical", len(over_limit_custs), by_ccy_ol,
            [r["customer_id"] for r in over_limit_custs],
            f"Customers exceeding credit limit: {len(over_limit_custs)}")

# missing_po
po_missing_list = [r for r in inv_rec if "missing_po" in r["exception_tags"]]
if po_missing_list:
    by_ccy_po: dict[str, float] = {}
    for r in po_missing_list:
        by_ccy_po[r["currency"]] = r2(by_ccy_po.get(r["currency"], 0) + r["open_amount"])
    add_exc("missing_po", "info", len(po_missing_list), by_ccy_po,
            [r["invoice_id"] for r in po_missing_list],
            f"Invoices missing PO numbers: {len(po_missing_list)}")

# term_mismatch
term_mismatch_list = [r for r in inv_rec if "term_mismatch" in r["exception_tags"]]
if term_mismatch_list:
    by_ccy_tm: dict[str, float] = {}
    for r in term_mismatch_list:
        by_ccy_tm[r["currency"]] = r2(by_ccy_tm.get(r["currency"], 0) + r["open_amount"])
    add_exc("term_mismatch", "info", len(term_mismatch_list), by_ccy_tm,
            [r["invoice_id"] for r in term_mismatch_list],
            f"Invoices with due date not matching credit terms: {len(term_mismatch_list)}")

# ── recommended actions ─────────────────────────────────────────────────
action_rows: list[dict] = []
priority_map_high = {"collect_90_plus": "high", "review_credit_hold": "high", "investigate_chargeback": "high",
                     "review_customer_status": "high"}
priority_map_medium = {"collect_31_90": "medium", "resolve_dispute": "medium", "review_adjustment": "medium"}
priority_map_low = {"apply_unapplied_cash": "low", "fix_missing_due_date": "low", "request_documentation": "low",
                    "investigate_payment": "low"}

action_type_map = {
    "collect_90_plus": "collect_overdue",
    "collect_31_90": "collect_overdue",
    "resolve_dispute": "resolve_dispute",
    "apply_unapplied_cash": "apply_unapplied_cash",
    "fix_missing_due_date": "fix_data_quality",
    "review_customer_status": "review_customer_status",
    "review_credit_hold": "review_credit_hold",
    "review_adjustment": "review_adjustment",
    "request_documentation": "request_documentation",
    "investigate_chargeback": "investigate_chargeback",
}

for cr in cust_risk_rows:
    cid = cr["customer_id"]
    for tag in cr["action_tags"]:
        if tag not in action_type_map:
            continue
        atype = action_type_map[tag]
        priority = "low"
        if tag in priority_map_high:
            priority = "high"
        elif tag in priority_map_medium:
            priority = "medium"
        else:
            priority = "low"

        inv_ids_for_action = []
        for r in inv_rec:
            if r["customer_id"] == cid and r["status"] != "excluded":
                inv_ids_for_action.append(r["invoice_id"])

        action_rows.append({
            "customer_id": cid,
            "priority": priority,
            "action_type": atype,
            "invoice_ids": inv_ids_for_action,
            "details": f"Action: {tag} for customer {cid} ({cr['customer_name']})",
        })

# Also add apply_unapplied_cash for any customer with unapplied payments
for p in unapplied_payments:
    cid_p = str(p.get("customer_id", ""))
    if cid_p and cid_p in customers:
        # Check if already have this action for this customer
        already = any(a["customer_id"] == cid_p and a["action_type"] == "apply_unapplied_cash" for a in action_rows)
        if not already:
            cr_match = next((cr for cr in cust_risk_rows if cr["customer_id"] == cid_p), None)
            if cr_match:
                inv_list = [r["invoice_id"] for r in inv_rec if r["customer_id"] == cid_p and r["status"] != "excluded"]
                action_rows.append({
                    "customer_id": cid_p,
                    "priority": "low",
                    "action_type": "apply_unapplied_cash",
                    "invoice_ids": inv_list,
                    "details": f"Unapplied cash exists for customer {cid_p} ({customers[cid_p]['customer_name']})",
                })

# investigate_payment for future-dated / non-posted
for pid in future_pay_ids:
    p_row = next((p for p in deduped_payments if str(p["payment_id"]) == pid), None)
    if p_row:
        cid_p = str(p_row.get("customer_id", ""))
        if cid_p and cid_p in customers:
            already = any(a["customer_id"] == cid_p and a["action_type"] == "investigate_payment" for a in action_rows)
            if not already:
                inv_list = [r["invoice_id"] for r in inv_rec if r["customer_id"] == cid_p and r["status"] != "excluded"]
                action_rows.append({
                    "customer_id": cid_p,
                    "priority": "medium",
                    "action_type": "investigate_payment",
                    "invoice_ids": inv_list,
                    "details": f"Future-dated payment {pid} needs investigation for customer {cid_p}",
                })

# ── data quality ────────────────────────────────────────────────────────
term_mismatch_ids = [r["invoice_id"] for r in inv_rec if "term_mismatch" in r["exception_tags"]]
missing_po_ids = [r["invoice_id"] for r in inv_rec if "missing_po" in r["exception_tags"]]
missing_dd_ids = [r["invoice_id"] for r in inv_rec if r["days_overdue"] is None and r["status"] != "excluded"]
over_limit_ids = [r["customer_id"] for r in cust_risk_rows if "review_credit_hold" in r["action_tags"]]

data_quality = {
    "required_columns": REQUIRED_COLS,
    "missing_required_columns": missing_req,
    "duplicate_invoice_ids": list(dict.fromkeys(dup_inv_ids)),
    "duplicate_payment_ids": list(dict.fromkeys(dup_pay_ids)),
    "invalid_invoice_ids": neg_inv_ids,
    "unmatched_payment_ids": list(dict.fromkeys(unmatched_pay_ids)),
    "currency_mismatch_payment_ids": currency_mismatch_pay_ids,
    "missing_due_date_invoice_ids": missing_dd_ids,
    "future_dated_payment_ids": future_pay_ids,
    "non_posted_payment_ids": non_posted_pay_ids,
    "unmatched_adjustment_ids": unmatched_adj_ids,
    "term_mismatch_invoice_ids": term_mismatch_ids,
    "missing_po_invoice_ids": missing_po_ids,
    "over_credit_limit_customer_ids": list(dict.fromkeys(over_limit_ids)),
}

# ── sort invoice reconciliation ─────────────────────────────────────────
inv_rec.sort(key=lambda x: x["invoice_id"])

# ── sort customer risk ──────────────────────────────────────────────────
band_order = {"high": 0, "medium": 1, "low": 2}


def cust_sort_key(r):
    band = band_order.get(r["risk_band"], 99)
    total_open = sum(r["open_amount_by_currency"].values())
    return (band, -total_open, r["customer_id"])


cust_risk_rows.sort(key=cust_sort_key)

# ── summary ─────────────────────────────────────────────────────────────
def to_float_dict(d: dict[str, Decimal]) -> dict[str, float]:
    return {k: r2(v) for k, v in d.items()}


summary = {
    "reference_date": str(REFERENCE_DATE),
    "base_currency": BASE_CCY,
    "invoice_row_count": len(invoice_rows),
    "unique_invoice_count": len(deduped_invoices),
    "duplicate_invoice_count": len(dup_inv_ids),
    "payment_row_count": len(payment_rows),
    "duplicate_payment_count": len(dup_pay_ids),
    "total_invoice_amount_by_currency": to_float_dict(total_inv_amt),
    "applied_payment_amount_by_currency": to_float_dict(total_applied),
    "approved_adjustment_amount_by_currency": to_float_dict(total_adj_approved),
    "open_invoice_amount_by_currency": to_float_dict(total_open),
    "unapplied_cash_amount_by_currency": to_float_dict(total_unapplied),
    "disputed_open_amount_by_currency": to_float_dict(total_disputed_open),
    "expected_credit_loss_by_currency": to_float_dict(total_ecl),
}

# ── audit notes ─────────────────────────────────────────────────────────
audit_notes = [
    {"step": "load_policy", "evidence": f"reference_date={REFERENCE_DATE}, base_currency={BASE_CCY}"},
    {"step": "deduplicate_invoices", "evidence": f"kept {len(deduped_invoices)} unique, {len(dup_inv_ids)} duplicates"},
    {"step": "exclude_negative_invoices", "evidence": f"excluded {len(neg_inv_ids)} negative-amount invoices"},
    {"step": "deduplicate_payments", "evidence": f"kept {len(deduped_payments)} unique payments, {len(dup_pay_ids)} duplicates"},
    {"step": "filter_payments_cutoff", "evidence": f"{len(future_pay_ids)} future-dated, {len(non_posted_pay_ids)} non-posted excluded"},
    {"step": "match_payments", "evidence": f"{len(applied_payments)} payments applied, {len(unapplied_payments)} unapplied"},
    {"step": "apply_adjustments", "evidence": f"{len(approved_credit_memo_adjs)} credit_memo/write_off, {len(approved_chargeback_adjs)} chargeback, {len(pending_writeoff_adjs)} pending_write_off, {len(unmatched_adj_ids)} unmatched"},
    {"step": "process_disputes", "evidence": f"{len(disputed_invs)} invoices with open disputes"},
    {"step": "compute_aging", "evidence": f"aged {sum(1 for r in inv_rec if r['status']!='excluded')} invoices by {REFERENCE_DATE}"},
    {"step": "compute_ecl", "evidence": f"loss rates applied: {dict(LOSS_RATES)}"},
    {"step": "assess_credit_limits", "evidence": f"{len(over_limit_ids)} customers over limit"},
    {"step": "check_terms", "evidence": f"{len(term_mismatch_ids)} term mismatches, {len(missing_po_ids)} missing PO"},
]

# ── validation ──────────────────────────────────────────────────────────
# Basic balance checks
balance_check = {}
for ccy in set(list(total_inv_amt.keys()) + list(total_open.keys()) + list(total_applied.keys())):
    inv = total_inv_amt.get(ccy, Decimal("0"))
    adj = total_adj_approved.get(ccy, Decimal("0"))
    app = total_applied.get(ccy, Decimal("0"))
    opn = total_open.get(ccy, Decimal("0"))
    # inv + adj = app + open  (approximately)
    lhs = inv + adj
    rhs = app + opn
    balance_check[ccy] = {
        "total_invoice_plus_adjustments": r2(lhs),
        "total_applied_plus_open": r2(rhs),
        "difference": r2(lhs - rhs),
    }

validation = {
    "balance_check": balance_check,
    "exceptions_count": len(exceptions_list),
    "actions_count": len(action_rows),
    "customers_evaluated": len(cust_risk_rows),
}

# ── assemble answer ─────────────────────────────────────────────────────
answer = {
    "summary": summary,
    "customer_risk": cust_risk_rows,
    "invoice_reconciliation": inv_rec,
    "aging_buckets": aging_rows,
    "exceptions": exceptions_list,
    "recommended_actions": action_rows,
    "data_quality": data_quality,
    "audit_notes": audit_notes,
    "validation": validation,
}

# ── write answer.json ───────────────────────────────────────────────────
with open(HERE / "answer.json", "w", encoding="utf-8") as f:
    json.dump(answer, f, indent=2, ensure_ascii=False)

print("✅ answer.json written successfully")
print(f"   Summary: {summary['unique_invoice_count']} invoices, {summary['duplicate_invoice_count']} duplicates")
print(f"   Open AR: {summary['open_invoice_amount_by_currency']}")
print(f"   Unapplied cash: {summary['unapplied_cash_amount_by_currency']}")
print(f"   ECL: {summary['expected_credit_loss_by_currency']}")
print(f"   Customers: {len(cust_risk_rows)}, Exceptions: {len(exceptions_list)}, Actions: {len(action_rows)}")
