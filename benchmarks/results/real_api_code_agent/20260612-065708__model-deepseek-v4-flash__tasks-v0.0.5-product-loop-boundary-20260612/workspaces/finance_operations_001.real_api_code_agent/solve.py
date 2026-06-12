"""
No-helper solve.py for finance_operations_001 benchmark.
Reads task.json + 6 CSV tables, produces answer.json per public output_contract.
Allowed libraries: pandas, numpy, json, pathlib, datetime, decimal, statistics.
"""
import json
import math
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd
import numpy as np

HERE = Path(__file__).parent

# ── Load task config ──────────────────────────────────────────────────────
with open(HERE / "task.json") as f:
    task = json.load(f)

finance_config = task["finance_config"]
REFERENCE_DATE_STR = None  # loaded from policy
BASE_CURRENCY = finance_config["base_currency"]
required_columns = finance_config["required_columns"]
aging_buckets_config = finance_config["aging_buckets"]

# ── Load CSVs ─────────────────────────────────────────────────────────────
def load_csv(name):
    return pd.read_csv(HERE / f"{name}.csv", keep_default_na=True)

_invoices_raw = load_csv("invoices")
_payments_raw = load_csv("payments")
_customers_raw = load_csv("customers")
_disputes_raw = load_csv("disputes")
_adjustments_raw = load_csv("adjustments")
_policy_raw = load_csv("policy")

# Load policy
policy = _policy_raw.iloc[0]
REFERENCE_DATE_STR = str(policy["reference_date"]).strip()
REFERENCE_DATE = pd.to_datetime(REFERENCE_DATE_STR).date()
AMOUNT_PRECISION = int(policy["amount_precision"])

loss_rates = {
    "not_due": float(policy["loss_rate_not_due"]),
    "0-30": float(policy["loss_rate_0_30"]),
    "31-60": float(policy["loss_rate_31_60"]),
    "61-90": float(policy["loss_rate_61_90"]),
    "90+": float(policy["loss_rate_90_plus"]),
    "missing_due_date": float(policy["loss_rate_missing_due_date"]),
}

# ── Helper functions ──────────────────────────────────────────────────────

def r2(v):
    """Round to AMOUNT_PRECISION decimal places using Decimal."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    d = Decimal(str(v)).quantize(Decimal("0." + "0" * AMOUNT_PRECISION), rounding=ROUND_HALF_UP)
    return float(d)

def normalize_str(val):
    """Return stripped string or empty string."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "nat", "none", "null"):
        return ""
    return s

def is_missing(val):
    """Check if a value is considered missing after normalization."""
    return normalize_str(val) == ""

def parse_date(val):
    """Parse a date string; return None if missing/invalid."""
    s = normalize_str(val)
    if not s:
        return None
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None

def safe_float(val):
    """Convert to float, returning NaN if not possible."""
    if pd.isna(val) or val is None:
        return float("nan")
    s = normalize_str(val)
    if not s:
        return float("nan")
    try:
        return float(s)
    except (ValueError, TypeError):
        return float("nan")

# ── Step 1: Data quality ──────────────────────────────────────────────────

# Detect missing required columns
def check_required_columns(df, table_name, cols):
    present = [c for c in cols if c in df.columns]
    missing = [c for c in cols if c not in df.columns]
    return present, missing

data_quality = {
    "required_columns": {},
    "missing_required_columns": {},
    "duplicate_invoice_ids": [],
    "duplicate_payment_ids": [],
    "invalid_invoice_ids": [],
    "unmatched_payment_ids": [],
    "currency_mismatch_payment_ids": [],
    "missing_due_date_invoice_ids": [],
    "future_dated_payment_ids": [],
    "non_posted_payment_ids": [],
    "unmatched_adjustment_ids": [],
    "term_mismatch_invoice_ids": [],
    "missing_po_invoice_ids": [],
    "over_credit_limit_customer_ids": [],
}

for tbl_name, cols in required_columns.items():
    df = {
        "invoices": _invoices_raw,
        "payments": _payments_raw,
        "customers": _customers_raw,
        "disputes": _disputes_raw,
        "adjustments": _adjustments_raw,
        "policy": _policy_raw,
    }[tbl_name]
    p, m = check_required_columns(df, tbl_name, cols)
    data_quality["required_columns"][tbl_name] = p
    data_quality["missing_required_columns"][tbl_name] = m

# ── Step 2: Normalize invoices ────────────────────────────────────────────
inv = _invoices_raw.copy()
inv["_invoice_amount"] = inv["invoice_amount"].apply(safe_float)
inv["_due_date"] = inv["due_date"].apply(parse_date)
inv["_invoice_date"] = inv["invoice_date"].apply(parse_date)
inv["_currency"] = inv["currency"].apply(normalize_str)
inv["_customer_id"] = inv["customer_id"].apply(normalize_str)
inv["_po_number"] = inv["po_number"].apply(normalize_str)
inv["_status"] = inv["status"].apply(normalize_str)

# --- Detect duplicate invoice_ids (keep first) ---
dup_inv_mask = inv["invoice_id"].duplicated(keep="first")
dup_inv_ids = inv.loc[dup_inv_mask, "invoice_id"].unique().tolist()
data_quality["duplicate_invoice_ids"] = sorted(dup_inv_ids)

# --- Detect negative invoice amounts ---
neg_mask = inv["_invoice_amount"] < 0
neg_inv_ids = inv.loc[neg_mask, "invoice_id"].unique().tolist()
data_quality["invalid_invoice_ids"] = sorted(neg_inv_ids)

# --- Detect missing due dates ---
missing_due_mask = inv["_due_date"].isna()
missing_due_ids = inv.loc[missing_due_mask, "invoice_id"].unique().tolist()
data_quality["missing_due_date_invoice_ids"] = sorted(missing_due_ids)

# --- Detect missing PO numbers ---
missing_po_mask = inv["_po_number"].apply(lambda x: x == "")
missing_po_ids = inv.loc[missing_po_mask, "invoice_id"].unique().tolist()
data_quality["missing_po_invoice_ids"] = sorted(missing_po_ids)

# --- Deduplicated invoices (keep first) ---
inv_dedup = inv[~dup_inv_mask].copy()

# --- Separate valid vs negative invoices ---
inv_neg = inv_dedup[inv_dedup["_invoice_amount"] < 0].copy()  # excluded from AR
inv_valid = inv_dedup[inv_dedup["_invoice_amount"] >= 0].copy()  # used for AR

# ── Step 3: Normalize customers ───────────────────────────────────────────
cust = _customers_raw.copy()
cust["_credit_limit"] = cust["credit_limit"].apply(safe_float)
cust["_credit_terms_days"] = cust["credit_terms_days"].apply(safe_float)
cust["_status"] = cust["status"].apply(normalize_str)
cust["_customer_id"] = cust["customer_id"].apply(normalize_str)

# ── Step 4: Normalize payments ────────────────────────────────────────────
pmt = _payments_raw.copy()
pmt["_payment_amount"] = pmt["payment_amount"].apply(safe_float)
pmt["_payment_date"] = pmt["payment_date"].apply(parse_date)
pmt["_gl_date"] = pmt["gl_date"].apply(parse_date)
pmt["_invoice_id"] = pmt["invoice_id"].apply(normalize_str)
pmt["_customer_id"] = pmt["customer_id"].apply(normalize_str)
pmt["_currency"] = pmt["currency"].apply(normalize_str)
pmt["_status"] = pmt["status"].apply(normalize_str)
pmt["_payment_id"] = pmt["payment_id"].apply(str)

# Detect duplicate payment_ids (keep first)
dup_pmt_mask = pmt["payment_id"].duplicated(keep="first")
dup_pmt_ids = pmt.loc[dup_pmt_mask, "payment_id"].unique().tolist()
data_quality["duplicate_payment_ids"] = sorted(dup_pmt_ids)

# Deduplicated payments
pmt_dedup = pmt[~dup_pmt_mask].copy()

# Classify payments
# Future-dated: payment_date > reference_date
future_mask = pmt_dedup["_payment_date"].apply(lambda x: x is not None and x > REFERENCE_DATE)
future_ids = pmt_dedup.loc[future_mask, "_payment_id"].tolist()
data_quality["future_dated_payment_ids"] = sorted(future_ids)

# Non-posted: status != "posted"
non_posted_mask = pmt_dedup["_status"] != "posted"
non_posted_ids = pmt_dedup.loc[non_posted_mask, "_payment_id"].tolist()
data_quality["non_posted_payment_ids"] = sorted(non_posted_ids)

# Valid posted payments on/before reference_date
valid_pmt = pmt_dedup[
    (pmt_dedup["_status"] == "posted")
    & (pmt_dedup["_payment_date"].apply(lambda x: x is not None and x <= REFERENCE_DATE))
    & (pmt_dedup["_gl_date"].apply(lambda x: x is not None and x <= REFERENCE_DATE))
].copy()

# ── Step 5: Normalize disputes ────────────────────────────────────────────
disp = _disputes_raw.copy()
disp["_invoice_id"] = disp["invoice_id"].apply(normalize_str)
disp["_customer_id"] = disp["customer_id"].apply(normalize_str)
disp["_currency"] = disp["currency"].apply(normalize_str)
disp["_status"] = disp["status"].apply(normalize_str)
disp["_dispute_amount"] = disp["dispute_amount"].apply(safe_float)

# Open disputes only
open_disp = disp[disp["_status"] == "open"].copy()

# ── Step 6: Normalize adjustments ─────────────────────────────────────────
adj = _adjustments_raw.copy()
adj["_invoice_id"] = adj["invoice_id"].apply(normalize_str)
adj["_customer_id"] = adj["customer_id"].apply(normalize_str)
adj["_currency"] = adj["currency"].apply(normalize_str)
adj["_status"] = adj["status"].apply(normalize_str)
adj["_type"] = adj["adjustment_type"].apply(normalize_str)
adj["_amount"] = adj["amount"].apply(safe_float)
adj["_adj_id"] = adj["adjustment_id"].apply(str)

# Build set of valid invoice_ids from inv_dedup
valid_invoice_ids = set(inv_dedup["invoice_id"].unique())

# ── Step 7: Invoice reconciliation ────────────────────────────────────────

# Build reconciliation rows for each valid invoice
recon_rows = []

# Track exception data
invoice_exception_tags = {}  # invoice_id -> list of exception tags
invoice_disputed_amount = {}  # invoice_id -> disputed open amount
invoice_adjustment_amounts = {}  # invoice_id -> total approved adjustment amount
invoice_overpayment = {}  # invoice_id -> overpayment amount
invoice_applied = {}  # invoice_id -> total applied amount
invoice_is_overpaid = {}  # invoice_id -> bool
invoice_is_partial = {}  # invoice_id -> bool

# Per-invoice exceptions
exceptions_map = {}  # exception_type -> dict

def add_exception(etype, severity, count, amount_by_currency, related_ids, description):
    if etype not in exceptions_map:
        exceptions_map[etype] = {
            "exception_type": etype,
            "severity": severity,
            "count": 0,
            "amount_by_currency": {},
            "related_ids": [],
            "description": description,
        }
    exc = exceptions_map[etype]
    exc["count"] += count
    for cur, amt in amount_by_currency.items():
        exc["amount_by_currency"][cur] = r2(exc["amount_by_currency"].get(cur, 0.0) + amt)
    exc["related_ids"].extend(related_ids)
    exc["description"] = description

# --- Handle duplicate invoice exception ---
if dup_inv_ids:
    add_exception(
        "duplicate_invoice", "warning", len(dup_inv_ids),
        {}, dup_inv_ids,
        f"Duplicate invoice_id rows found: {', '.join(dup_inv_ids)}. First row kept, later rows excluded."
    )

# --- Handle duplicate payment exception ---
if dup_pmt_ids:
    add_exception(
        "duplicate_payment", "warning", len(dup_pmt_ids),
        {}, dup_pmt_ids,
        f"Duplicate payment_id rows found: {', '.join(dup_pmt_ids)}. First row kept, later rows excluded."
    )

# --- Handle negative invoice amount exception ---
for _, row in inv_neg.iterrows():
    inv_id = row["invoice_id"]
    cur = row["_currency"]
    amt = abs(float(row["_invoice_amount"]))
    add_exception(
        "negative_invoice_amount", "critical", 1,
        {cur: r2(amt)}, [inv_id],
        f"Invoice {inv_id} has negative amount ({row['invoice_amount']}), excluded from AR."
    )

# Process adjustments per invoice
approved_adjustments_by_invoice = {}  # invoice_id -> list of adj rows
pending_adj_by_invoice = {}
unmatched_adjustments = []

for _, row in adj.iterrows():
    inv_id = row["_invoice_id"]
    adj_type = row["_type"]
    adj_status = row["_status"]
    adj_amt = row["_amount"]

    if inv_id not in valid_invoice_ids:
        unmatched_adjustments.append(row["_adj_id"])
        add_exception(
            "unmatched_adjustment", "warning", 1,
            {row["_currency"]: r2(abs(adj_amt))}, [row["_adj_id"]],
            f"Adjustment {row['_adj_id']} references unknown invoice {inv_id}."
        )
        continue

    if adj_status == "approved":
        if inv_id not in approved_adjustments_by_invoice:
            approved_adjustments_by_invoice[inv_id] = []
        approved_adjustments_by_invoice[inv_id].append(row)

        if adj_type == "credit_memo":
            add_exception(
                "approved_credit_memo", "info", 1,
                {row["_currency"]: r2(abs(adj_amt))}, [row["_adj_id"], inv_id],
                f"Approved credit memo {row['_adj_id']} for invoice {inv_id}: {adj_amt}."
            )
        elif adj_type == "chargeback":
            add_exception(
                "chargeback", "warning", 1,
                {row["_currency"]: r2(abs(adj_amt))}, [row["_adj_id"], inv_id],
                f"Approved chargeback {row['_adj_id']} for invoice {inv_id}: +{adj_amt}."
            )
    elif adj_status == "pending" and adj_type == "write_off":
        if inv_id not in pending_adj_by_invoice:
            pending_adj_by_invoice[inv_id] = []
        pending_adj_by_invoice[inv_id].append(row)
        add_exception(
            "pending_write_off", "warning", 1,
            {row["_currency"]: r2(abs(adj_amt))}, [row["_adj_id"], inv_id],
            f"Pending write-off {row['_adj_id']} for invoice {inv_id}: {adj_amt}. Not reducing AR."
        )

data_quality["unmatched_adjustment_ids"] = sorted(unmatched_adjustments)

# Build set of valid posted payment invoice_ids (among valid invoices)
valid_pmt_by_invoice = {}  # invoice_id -> list of payment rows
unapplied_cash_payments = []  # payments that couldn't be applied

for _, row in valid_pmt.iterrows():
    pmt_inv_id = row["_invoice_id"]
    pmt_cur = row["_currency"]

    # Check if invoice_id is blank
    if is_missing(row["invoice_id"]):
        unapplied_cash_payments.append(row)
        add_exception(
            "unapplied_cash", "warning", 1,
            {pmt_cur: r2(row["_payment_amount"])}, [row["_payment_id"]],
            f"Payment {row['_payment_id']} has blank invoice_id, treated as unapplied cash."
        )
        continue

    # Check if invoice_id exists in valid invoices
    if pmt_inv_id not in valid_invoice_ids:
        unapplied_cash_payments.append(row)
        add_exception(
            "unapplied_cash", "warning", 1,
            {pmt_cur: r2(row["_payment_amount"])}, [row["_payment_id"]],
            f"Payment {row['_payment_id']} references unknown invoice {pmt_inv_id}, treated as unapplied cash."
        )
        continue

    # Check if invoice is negative (excluded)
    if pmt_inv_id in neg_inv_ids:
        unapplied_cash_payments.append(row)
        add_exception(
            "unapplied_cash", "warning", 1,
            {pmt_cur: r2(row["_payment_amount"])}, [row["_payment_id"]],
            f"Payment {row['_payment_id']} references negatively-valued invoice {pmt_inv_id}, treated as unapplied cash."
        )
        continue

    # Check currency match
    inv_row = inv_dedup[inv_dedup["invoice_id"] == pmt_inv_id].iloc[0]
    inv_cur = inv_row["_currency"]
    if pmt_cur != inv_cur:
        unapplied_cash_payments.append(row)
        add_exception(
            "currency_mismatch", "warning", 1,
            {pmt_cur: r2(row["_payment_amount"])}, [row["_payment_id"]],
            f"Payment {row['_payment_id']} currency ({pmt_cur}) does not match invoice {pmt_inv_id} currency ({inv_cur})."
        )
        add_exception(
            "unapplied_cash", "warning", 1,
            {pmt_cur: r2(row["_payment_amount"])}, [row["_payment_id"]],
            f"Payment {row['_payment_id']} currency mismatch, treated as unapplied cash."
        )
        data_quality["currency_mismatch_payment_ids"].append(row["_payment_id"])
        continue

    if pmt_inv_id not in valid_pmt_by_invoice:
        valid_pmt_by_invoice[pmt_inv_id] = []
    valid_pmt_by_invoice[pmt_inv_id].append(row)

# Future-dated / non-posted payments → exceptions
for _, row in pmt_dedup.iterrows():
    pid = row["_payment_id"]
    if row["_status"] != "posted":
        add_exception(
            "non_posted_payment", "info", 1,
            {row["_currency"]: r2(row["_payment_amount"])}, [pid],
            f"Payment {pid} has non-posted status '{row['status']}', not reducing AR."
        )
    elif row["_payment_date"] is not None and row["_payment_date"] > REFERENCE_DATE:
        add_exception(
            "future_dated_payment", "info", 1,
            {row["_currency"]: r2(row["_payment_amount"])}, [pid],
            f"Payment {pid} has future payment date {row['payment_date']} > reference date {REFERENCE_DATE_STR}, not reducing AR."
        )

# Build reconciliation for each valid invoice
for _, row in inv_valid.iterrows():
    inv_id = row["invoice_id"]
    inv_cur = row["_currency"]
    cust_id = row["_customer_id"]
    inv_amt = float(row["_invoice_amount"])
    due_date = row["_due_date"]
    inv_date = row["_invoice_date"]
    po_number = row["_po_number"]

    # Compute approved adjustment amount
    approved_adj_total = 0.0
    if inv_id in approved_adjustments_by_invoice:
        for arow in approved_adjustments_by_invoice[inv_id]:
            at = arow["_type"]
            aa = float(arow["_amount"])
            if at in ("credit_memo", "write_off"):
                approved_adj_total += aa  # negative values reduce
            elif at == "chargeback":
                approved_adj_total += aa   # positive values increase

    adjusted_inv_amt = r2(inv_amt + approved_adj_total)

    # Apply payments
    total_applied = 0.0
    overpayment_amt = 0.0
    if inv_id in valid_pmt_by_invoice:
        for prow in valid_pmt_by_invoice[inv_id]:
            total_applied += float(prow["_payment_amount"])

    if total_applied > adjusted_inv_amt:
        overpayment_amt = r2(total_applied - adjusted_inv_amt)
        total_applied = adjusted_inv_amt
        open_amt = 0.0
    else:
        open_amt = r2(adjusted_inv_amt - total_applied)

    total_applied = r2(total_applied)
    open_amt = r2(open_amt)
    overpayment_amt = r2(overpayment_amt)

    # Overpayment -> unapplied cash
    if overpayment_amt > 0:
        add_exception(
            "overpayment", "warning", 1,
            {inv_cur: overpayment_amt}, [inv_id],
            f"Invoice {inv_id} overpaid by {overpayment_amt} {inv_cur}. Excess treated as unapplied cash."
        )
        # Also count as unapplied cash
        add_exception(
            "unapplied_cash", "warning", 1,
            {inv_cur: overpayment_amt}, [inv_id],
            f"Overpayment excess {overpayment_amt} {inv_cur} from invoice {inv_id} treated as unapplied cash."
        )

    # Partial payment
    is_partial = False
    if 0 < total_applied < adjusted_inv_amt:
        is_partial = True
        add_exception(
            "partial_payment", "info", 1,
            {inv_cur: r2(total_applied)}, [inv_id],
            f"Invoice {inv_id} partially paid: applied {total_applied}, remaining {open_amt}."
        )

    # Determine status
    if inv_id in neg_inv_ids:
        status = "excluded"
    elif open_amt == 0 and overpayment_amt > 0:
        status = "overpaid"
    elif open_amt == 0:
        status = "closed"
    else:
        status = "open"

    # Exception tags for this invoice
    tags = []
    if is_partial:
        tags.append("partial_payment")
    if overpayment_amt > 0:
        tags.append("overpayment")
    if is_missing(row["due_date"]):
        tags.append("missing_due_date")
        add_exception(
            "missing_due_date", "warning", 1,
            {inv_cur: open_amt}, [inv_id],
            f"Invoice {inv_id} has missing due date."
        )
    if is_missing(row["po_number"]):
        tags.append("missing_po")

    # Term mismatch check
    if due_date is not None and inv_date is not None:
        cid = cust_id
        c_row = cust[cust["_customer_id"] == cid]
        if not c_row.empty:
            terms = int(c_row.iloc[0]["_credit_terms_days"])
            expected_due = pd.Timestamp(inv_date) + pd.Timedelta(days=terms)
            expected_due_date = expected_due.date()
            if due_date != expected_due_date:
                tags.append("term_mismatch")
                data_quality["term_mismatch_invoice_ids"].append(inv_id)
                add_exception(
                    "term_mismatch", "warning", 1,
                    {inv_cur: inv_amt}, [inv_id],
                    f"Invoice {inv_id} due date {due_date} does not match invoice_date + terms ({expected_due_date})."
                )

    # Dispute check
    disputed_open = 0.0
    inv_disputes = open_disp[open_disp["_invoice_id"] == inv_id]
    if not inv_disputes.empty:
        # Sum dispute amounts for this invoice, capped at open amount
        total_dispute = float(inv_disputes["_dispute_amount"].sum())
        disputed_open = r2(min(total_dispute, open_amt))
        tags.append("disputed_invoice")
        add_exception(
            "disputed_invoice", "warning", 1,
            {inv_cur: disputed_open}, [inv_id],
            f"Invoice {inv_id} has open dispute(s)."
        )

    # Aging
    if due_date is None:
        aging_bucket = "missing_due_date"
        days_overdue = None
    elif due_date > REFERENCE_DATE:
        aging_bucket = "not_due"
        days_overdue = 0
    else:
        days_overdue = (REFERENCE_DATE - due_date).days
        if days_overdue <= 30:
            aging_bucket = "0-30"
        elif days_overdue <= 60:
            aging_bucket = "31-60"
        elif days_overdue <= 90:
            aging_bucket = "61-90"
        else:
            aging_bucket = "90+"

    # Risk amount excluding disputed
    risk_amount_excl = r2(open_amt - disputed_open)

    # ECL
    rate = loss_rates.get(aging_bucket, 0.0)
    ecl = r2(risk_amount_excl * rate)

    recon_rows.append({
        "invoice_id": inv_id,
        "customer_id": cust_id,
        "currency": inv_cur,
        "invoice_amount": r2(inv_amt),
        "approved_adjustment_amount": r2(approved_adj_total),
        "adjusted_invoice_amount": adjusted_inv_amt,
        "applied_amount": total_applied,
        "open_amount": open_amt,
        "overpayment_amount": overpayment_amt,
        "disputed_open_amount": disputed_open,
        "expected_credit_loss": ecl,
        "due_date": str(due_date) if due_date is not None else None,
        "days_overdue": days_overdue,
        "aging_bucket": aging_bucket,
        "status": status,
        "exception_tags": sorted(tags),
    })

# Also process negative invoices as excluded rows
for _, row in inv_neg.iterrows():
    inv_id = row["invoice_id"]
    inv_cur = row["_currency"]
    cust_id = row["_customer_id"]
    inv_amt = float(row["_invoice_amount"])

    recon_rows.append({
        "invoice_id": inv_id,
        "customer_id": cust_id,
        "currency": inv_cur,
        "invoice_amount": r2(inv_amt),
        "approved_adjustment_amount": 0.0,
        "adjusted_invoice_amount": r2(inv_amt),
        "applied_amount": 0.0,
        "open_amount": 0.0,
        "overpayment_amount": 0.0,
        "disputed_open_amount": 0.0,
        "expected_credit_loss": 0.0,
        "due_date": str(row["_due_date"]) if row["_due_date"] is not None else None,
        "days_overdue": None,
        "aging_bucket": "missing_due_date",
        "status": "excluded",
        "exception_tags": ["negative_invoice_amount"],
    })
    add_exception(
        "negative_invoice_amount", "critical", 1,
        {inv_cur: r2(abs(inv_amt))}, [inv_id],
        f"Invoice {inv_id} has negative amount ({inv_amt}), excluded from AR."
    )

# Process unapplied cash payments (that weren't already counted as overpayment)
# Already added above

# Also add unapplied cash for payments that didn't match (already handled above)

# ── Step 8: Customer risk ─────────────────────────────────────────────────

# Aggregate per customer
customer_data = {}
for r in recon_rows:
    cid = r["customer_id"]
    if cid not in customer_data:
        customer_data[cid] = {
            "open_by_currency": {},
            "overdue_by_currency": {},
            "disputed_by_currency": {},
            "risk_by_currency": {},
            "ecl_by_currency": {},
            "max_days": 0,
            "invoices": [],
        }
    cd = customer_data[cid]
    cur = r["currency"]
    cd["open_by_currency"][cur] = r2(cd["open_by_currency"].get(cur, 0.0) + r["open_amount"])
    cd["risk_by_currency"][cur] = r2(cd["risk_by_currency"].get(cur, 0.0) + r["open_amount"] - r["disputed_open_amount"])
    cd["ecl_by_currency"][cur] = r2(cd["ecl_by_currency"].get(cur, 0.0) + r["expected_credit_loss"])
    cd["disputed_by_currency"][cur] = r2(cd["disputed_by_currency"].get(cur, 0.0) + r["disputed_open_amount"])
    if r["days_overdue"] is not None and r["days_overdue"] > cd["max_days"]:
        cd["max_days"] = r["days_overdue"]
    if r["aging_bucket"] not in ("not_due", "missing_due_date") and r["aging_bucket"] is not None and r["open_amount"] > 0:
        cd["overdue_by_currency"][cur] = r2(cd["overdue_by_currency"].get(cur, 0.0) + r["open_amount"])
    cd["invoices"].append(r)

# Determine risk band per customer
def determine_risk_band(cd, c_row):
    max_days = cd["max_days"]
    total_open = sum(cd["open_by_currency"].values())
    status = normalize_str(c_row["_status"])
    
    if total_open <= 0:
        return "low"
    if max_days >= 91 or status in ("inactive", "on_hold"):
        return "high"
    if max_days >= 31:
        return "medium"
    return "low"

customer_risk_rows = []
for _, c_row in cust.iterrows():
    cid = c_row["_customer_id"]
    if cid not in customer_data:
        continue
    cd = customer_data[cid]
    total_open = sum(cd["open_by_currency"].values())
    if total_open <= 0:
        # Still include if customer has issues
        pass

    risk_band = determine_risk_band(cd, c_row)
    max_days = cd["max_days"] if cd["max_days"] > 0 else None

    # Action tags per customer
    action_tags = []
    rationale = []

    # Check overdue buckets
    has_90_plus = any(
        r["aging_bucket"] == "90+" and r["open_amount"] > 0
        for r in cd["invoices"]
    )
    has_31_90 = any(
        r["aging_bucket"] in ("31-60", "61-90") and r["open_amount"] > 0
        for r in cd["invoices"]
    )

    if has_90_plus:
        action_tags.append("collect_90_plus")
        rationale.append(f"Customer {cid} has invoices 90+ days overdue.")
    if has_31_90:
        action_tags.append("collect_31_90")
        rationale.append(f"Customer {cid} has invoices 31-90 days overdue.")

    # Dispute
    has_dispute = any(
        r["disputed_open_amount"] > 0 for r in cd["invoices"]
    )
    if has_dispute:
        action_tags.append("resolve_dispute")
        rationale.append(f"Customer {cid} has open disputed amounts.")

    # Missing due date
    has_missing_due = any(
        "missing_due_date" in r["exception_tags"] for r in cd["invoices"]
    )
    if has_missing_due:
        action_tags.append("fix_missing_due_date")
        rationale.append(f"Customer {cid} has invoices with missing due dates.")

    # Unapplied cash - check if any payment for this customer was unapplied
    cust_unapplied = False
    for exc in exceptions_map.values():
        if exc["exception_type"] == "unapplied_cash":
            cust_unapplied = True
            break
    if cust_unapplied and total_open > 0:
        action_tags.append("apply_unapplied_cash")
        rationale.append(f"Customer {cid} has unapplied cash that could be applied.")

    # Customer status
    cust_status = normalize_str(c_row["_status"])
    if cust_status not in ("active", "") and total_open > 0:
        action_tags.append("review_customer_status")
        rationale.append(f"Customer {cid} status is '{cust_status}' with open receivables.")
        add_exception(
            "inactive_or_on_hold_customer", "warning", 1,
            cd["open_by_currency"], [cid],
            f"Customer {cid} has status '{cust_status}' with open receivables."
        )

    # Credit limit check
    cl = float(c_row["_credit_limit"]) if not pd.isna(c_row["_credit_limit"]) else float('inf')
    over_limit = False
    for cur, amt in cd["open_by_currency"].items():
        # Check only in the customer's default currency or base currency
        if cur == normalize_str(c_row["default_currency"]):
            if amt > cl:
                over_limit = True
                break
        elif cur == BASE_CURRENCY and normalize_str(c_row["default_currency"]) != BASE_CURRENCY:
            # Cross-currency check
            pass

    # Simplified: check total open in any currency vs credit limit
    if total_open > cl:
        over_limit = True

    if over_limit:
        action_tags.append("review_credit_hold")
        rationale.append(f"Customer {cid} open exposure ({total_open}) exceeds credit limit ({cl}).")
        data_quality["over_credit_limit_customer_ids"].append(cid)
        add_exception(
            "over_credit_limit", "warning", 1,
            cd["open_by_currency"], [cid],
            f"Customer {cid} open exposure exceeds credit limit."
        )

    # Chargeback
    has_chargeback = any(
        "chargeback" in r["exception_tags"] for r in cd["invoices"]
    )
    if has_chargeback:
        action_tags.append("investigate_chargeback")
        rationale.append(f"Customer {cid} has chargeback adjustments.")

    # Missing PO / term mismatch → request_documentation
    has_missing_po = any(
        "missing_po" in r["exception_tags"] for r in cd["invoices"]
    )
    has_term_mismatch = any(
        "term_mismatch" in r["exception_tags"] for r in cd["invoices"]
    )
    if has_missing_po or has_term_mismatch:
        action_tags.append("request_documentation")
        rationale.append(f"Customer {cid} has missing POs or term mismatches requiring documentation.")

    # Review adjustments
    has_pending_wo = any(
        "pending_write_off" in r["exception_tags"] if False else False
        for r in cd["invoices"]
    )
    # Actually check pending write-offs for this customer's invoices
    for inv_id_key in pending_adj_by_invoice:
        inv_row_match = [r for r in cd["invoices"] if r["invoice_id"] == inv_id_key]
        if inv_row_match:
            action_tags.append("review_adjustment")
            rationale.append(f"Customer {cid} has pending write-offs requiring review.")
            break

    # Deduplicate action tags while preserving order
    seen_tags = set()
    unique_tags = []
    for t in action_tags:
        if t not in seen_tags:
            seen_tags.add(t)
            unique_tags.append(t)
    action_tags = unique_tags

    # Deduplicate rationale
    seen_rationale = set()
    unique_rationale = []
    for r in rationale:
        if r not in seen_rationale:
            seen_rationale.add(r)
            unique_rationale.append(r)

    customer_risk_rows.append({
        "customer_id": cid,
        "customer_name": str(c_row["customer_name"]),
        "status": normalize_str(c_row["_status"]),
        "risk_band": risk_band,
        "open_amount_by_currency": {k: r2(v) for k, v in cd["open_by_currency"].items()},
        "overdue_amount_by_currency": {k: r2(v) for k, v in cd.get("overdue_by_currency", {}).items()},
        "disputed_open_amount_by_currency": {k: r2(v) for k, v in cd["disputed_by_currency"].items()},
        "risk_amount_excluding_disputed_by_currency": {k: r2(v) for k, v in cd["risk_by_currency"].items()},
        "expected_credit_loss_by_currency": {k: r2(v) for k, v in cd["ecl_by_currency"].items()},
        "max_days_overdue": max_days if max_days and max_days > 0 else None,
        "action_tags": action_tags,
        "rationale": unique_rationale,
    })

# Sort customer_risk: risk_band high, medium, low; then descending total_open; then customer_id
band_order = {"high": 0, "medium": 1, "low": 2}
customer_risk_rows.sort(key=lambda r: (
    band_order.get(r["risk_band"], 99),
    -sum(r["open_amount_by_currency"].values()),
    r["customer_id"],
))

# ── Step 9: Aging buckets ─────────────────────────────────────────────────

aging_rows = []
bucket_order_map = {"not_due": 0, "0-30": 1, "31-60": 2, "61-90": 3, "90+": 4, "missing_due_date": 5}

# Aggregate by currency + bucket
bucket_agg = {}
for r in recon_rows:
    if r["status"] == "excluded":
        continue
    cur = r["currency"]
    bkt = r["aging_bucket"]
    key = (cur, bkt)
    if key not in bucket_agg:
        bucket_agg[key] = {
            "currency": cur,
            "bucket": bkt,
            "invoice_count": 0,
            "open_amount": 0.0,
            "risk_amount_excluding_disputed": 0.0,
            "expected_credit_loss": 0.0,
        }
    ba = bucket_agg[key]
    ba["invoice_count"] += 1
    ba["open_amount"] = r2(ba["open_amount"] + r["open_amount"])
    risk = r2(r["open_amount"] - r["disputed_open_amount"])
    ba["risk_amount_excluding_disputed"] = r2(ba["risk_amount_excluding_disputed"] + risk)
    ba["expected_credit_loss"] = r2(ba["expected_credit_loss"] + r["expected_credit_loss"])

aging_rows = list(bucket_agg.values())
# Sort: currency asc, then bucket order
aging_rows.sort(key=lambda r: (r["currency"], bucket_order_map.get(r["bucket"], 99)))

# ── Step 10: Exceptions list ──────────────────────────────────────────────

# Process remaining exceptions that need aggregation
# unapplied_cash from unmatched payments already added above

# Process the exceptions_map into a list
exception_rows = []
for etype in [
    "duplicate_invoice", "duplicate_payment", "partial_payment", "overpayment",
    "approved_credit_memo", "pending_write_off", "chargeback", "unapplied_cash",
    "currency_mismatch", "negative_invoice_amount", "missing_due_date",
    "disputed_invoice", "inactive_or_on_hold_customer", "future_dated_payment",
    "non_posted_payment", "unmatched_adjustment", "over_credit_limit",
    "missing_po", "term_mismatch"
]:
    if etype in exceptions_map:
        exc = exceptions_map[etype]
        # Deduplicate related_ids
        exc["related_ids"] = sorted(set(exc["related_ids"]))
        exception_rows.append(exc)

# Sort exception rows
exception_rows.sort(key=lambda r: r["exception_type"])

# ── Step 11: Recommended actions ──────────────────────────────────────────

def make_action(customer_id, priority, action_type, invoice_ids, details):
    return {
        "customer_id": customer_id,
        "priority": priority,
        "action_type": action_type,
        "invoice_ids": sorted(set(invoice_ids)),
        "details": details,
    }

recommended_actions = []

for cr in customer_risk_rows:
    cid = cr["customer_id"]
    invs_for_c = [r for r in recon_rows if r["customer_id"] == cid and r["status"] != "excluded"]

    # collect_90_plus
    invs_90 = [r["invoice_id"] for r in invs_for_c if r["aging_bucket"] == "90+" and r["open_amount"] > 0]
    if invs_90:
        recommended_actions.append(make_action(
            cid, "high", "collect_overdue", invs_90,
            f"Collect invoices 90+ days overdue for {cid}: {', '.join(invs_90)}."
        ))

    # collect_31_90
    invs_31_90 = [r["invoice_id"] for r in invs_for_c if r["aging_bucket"] in ("31-60", "61-90") and r["open_amount"] > 0]
    if invs_31_90:
        recommended_actions.append(make_action(
            cid, "medium", "collect_overdue", invs_31_90,
            f"Collect invoices 31-90 days overdue for {cid}: {', '.join(invs_31_90)}."
        ))

    # resolve_dispute
    invs_disp = [r["invoice_id"] for r in invs_for_c if r["disputed_open_amount"] > 0]
    if invs_disp:
        recommended_actions.append(make_action(
            cid, "high", "resolve_dispute", invs_disp,
            f"Resolve open disputes for {cid}: {', '.join(invs_disp)}."
        ))

    # apply_unapplied_cash
    if "apply_unapplied_cash" in cr["action_tags"]:
        recommended_actions.append(make_action(
            cid, "medium", "apply_unapplied_cash", [],
            f"Apply unapplied cash to open invoices for {cid}."
        ))

    # fix_missing_due_date
    invs_no_due = [r["invoice_id"] for r in invs_for_c if "missing_due_date" in r["exception_tags"]]
    if invs_no_due:
        recommended_actions.append(make_action(
            cid, "medium", "fix_data_quality", invs_no_due,
            f"Fix missing due dates for invoices: {', '.join(invs_no_due)}."
        ))

    # review_customer_status
    if "review_customer_status" in cr["action_tags"]:
        recommended_actions.append(make_action(
            cid, "high", "review_customer_status", [],
            f"Customer {cid} status is '{cr['status']}' with open receivables. Review and update."
        ))

    # review_credit_hold
    if "review_credit_hold" in cr["action_tags"]:
        recommended_actions.append(make_action(
            cid, "high", "review_credit_hold", [],
            f"Customer {cid} exceeds credit limit. Review credit hold."
        ))

    # review_adjustment
    if "review_adjustment" in cr["action_tags"]:
        invs_adj = []
        for inv_id_key in pending_adj_by_invoice:
            if inv_id_key in [r["invoice_id"] for r in invs_for_c]:
                invs_adj.append(inv_id_key)
        recommended_actions.append(make_action(
            cid, "medium", "review_adjustment", invs_adj,
            f"Review pending adjustments for {cid}: {', '.join(invs_adj) if invs_adj else 'pending write-offs'}."
        ))

    # request_documentation
    if "request_documentation" in cr["action_tags"]:
        invs_po = [r["invoice_id"] for r in invs_for_c if "missing_po" in r["exception_tags"]]
        invs_term = [r["invoice_id"] for r in invs_for_c if "term_mismatch" in r["exception_tags"]]
        all_doc = list(set(invs_po + invs_term))
        recommended_actions.append(make_action(
            cid, "low", "request_documentation", all_doc,
            f"Request documentation for {cid}: missing POs ({invs_po}) and term mismatches ({invs_term})."
        ))

    # investigate_chargeback
    if "investigate_chargeback" in cr["action_tags"]:
        invs_cb = [r["invoice_id"] for r in invs_for_c if "chargeback" in r["exception_tags"] if False]
        # Check chargeback adjustments for this customer
        cb_inv_ids = []
        for _, arow in adj.iterrows():
            if arow["_type"] == "chargeback" and arow["_status"] == "approved":
                inv_key = arow["_invoice_id"]
                if inv_key in [r["invoice_id"] for r in invs_for_c]:
                    cb_inv_ids.append(inv_key)
        recommended_actions.append(make_action(
            cid, "high", "investigate_chargeback", list(set(cb_inv_ids)),
            f"Investigate chargeback for {cid}: {', '.join(set(cb_inv_ids)) if cb_inv_ids else 'chargeback adjustments'}."
        ))

# ── Step 12: Summary ──────────────────────────────────────────────────────
# Total invoice amounts (including duplicates but not the duplicate rows themselves)
# Use inv_dedup for totals
total_inv_by_cur = {}
for _, row in inv_dedup.iterrows():
    cur = row["_currency"]
    amt = float(row["_invoice_amount"])
    total_inv_by_cur[cur] = r2(total_inv_by_cur.get(cur, 0.0) + amt)

# Applied payment amounts (only valid posted applied payments)
applied_by_cur = {}
for r in recon_rows:
    if r["applied_amount"] > 0:
        cur = r["currency"]
        applied_by_cur[cur] = r2(applied_by_cur.get(cur, 0.0) + r["applied_amount"])

# Approved adjustment amounts
adj_by_cur = {}
for _, arow in adj.iterrows():
    if arow["_status"] == "approved":
        cur = arow["_currency"]
        amt = abs(float(arow["_amount"]))
        adj_by_cur[cur] = r2(adj_by_cur.get(cur, 0.0) + amt)

# Open invoice amounts
open_by_cur_summary = {}
disp_by_cur_summary = {}
ecl_by_cur_summary = {}
for r in recon_rows:
    if r["status"] == "excluded":
        continue
    cur = r["currency"]
    open_by_cur_summary[cur] = r2(open_by_cur_summary.get(cur, 0.0) + r["open_amount"])
    disp_by_cur_summary[cur] = r2(disp_by_cur_summary.get(cur, 0.0) + r["disputed_open_amount"])
    ecl_by_cur_summary[cur] = r2(ecl_by_cur_summary.get(cur, 0.0) + r["expected_credit_loss"])

# Unapplied cash
unapplied_by_cur = {}
for etype, exc in exceptions_map.items():
    if etype == "unapplied_cash":
        for cur, amt in exc["amount_by_currency"].items():
            unapplied_by_cur[cur] = r2(unapplied_by_cur.get(cur, 0.0) + amt)

summary = {
    "reference_date": REFERENCE_DATE_STR,
    "base_currency": BASE_CURRENCY,
    "invoice_row_count": len(_invoices_raw),
    "unique_invoice_count": len(inv_dedup),
    "duplicate_invoice_count": int(dup_inv_mask.sum()),
    "payment_row_count": len(_payments_raw),
    "duplicate_payment_count": int(dup_pmt_mask.sum()),
    "total_invoice_amount_by_currency": {k: r2(v) for k, v in total_inv_by_cur.items()},
    "applied_payment_amount_by_currency": applied_by_cur,
    "approved_adjustment_amount_by_currency": adj_by_cur,
    "open_invoice_amount_by_currency": open_by_cur_summary,
    "unapplied_cash_amount_by_currency": unapplied_by_cur,
    "disputed_open_amount_by_currency": disp_by_cur_summary,
    "expected_credit_loss_by_currency": ecl_by_cur_summary,
}

# ── Step 13: Audit notes ──────────────────────────────────────────────────

audit_notes = [
    {"step": "load_tables", "evidence": f"Loaded 6 CSV files from workspace."},
    {"step": "reference_date", "evidence": f"Reference date set to {REFERENCE_DATE_STR} from policy.csv."},
    {"step": "missing_value_normalization", "evidence": "Blank, NaN, NaT, 'nan', 'NaN', 'NaT', 'None', 'null' normalized as missing."},
    {"step": "duplicate_invoice_handling", "evidence": f"Duplicate invoices: {dup_inv_ids}. First row kept."},
    {"step": "duplicate_payment_handling", "evidence": f"Duplicate payments: {dup_pmt_ids}. First row kept."},
    {"step": "negative_invoice_exclusion", "evidence": f"Negative amount invoices excluded: {neg_inv_ids}."},
    {"step": "payment_matching", "evidence": f"Payments matched by invoice_id and currency. {len(valid_pmt)} valid posted payments applied."},
    {"step": "cutoff_check", "evidence": f"Future-dated and non-posted payments excluded from AR."},
    {"step": "adjustment_processing", "evidence": f"Approved adjustments applied; pending write-offs reported separately; unmatched adjustments flagged."},
    {"step": "dispute_handling", "evidence": "Open disputes separated from risk amount but remain in aging."},
    {"step": "credit_loss_calculation", "evidence": f"ECL calculated using provision-matrix loss rates from policy."},
    {"step": "credit_limit_check", "evidence": f"Customers over credit limit: {data_quality['over_credit_limit_customer_ids']}."},
    {"step": "term_comparison", "evidence": "Due dates compared with invoice_date + credit_terms_days per customer."},
]

# ── Step 14: Validation ───────────────────────────────────────────────────

validation = {
    "total_reconciled_invoices": len(recon_rows),
    "total_customers_with_ar": len(customer_risk_rows),
    "aging_bucket_count": len(aging_rows),
    "exception_count": len(exception_rows),
    "action_count": len(recommended_actions),
    "summary_invoice_amount_check": {
        k: r2(v) for k, v in total_inv_by_cur.items()
    },
}

# ── Step 15: Build answer ─────────────────────────────────────────────────

# Sort invoice_reconciliation by invoice_id
recon_rows.sort(key=lambda r: r["invoice_id"])

answer = {
    "summary": summary,
    "customer_risk": customer_risk_rows,
    "invoice_reconciliation": recon_rows,
    "aging_buckets": aging_rows,
    "exceptions": exception_rows,
    "recommended_actions": recommended_actions,
    "data_quality": data_quality,
    "audit_notes": audit_notes,
    "validation": validation,
}

# Write answer.json
output_path = HERE / "answer.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(answer, f, indent=2, ensure_ascii=False)

print(f"answer.json written to {output_path}")
print(f"Invoice reconciliation: {len(recon_rows)} rows")
print(f"Customer risk: {len(customer_risk_rows)} rows")
print(f"Aging buckets: {len(aging_rows)} rows")
print(f"Exceptions: {len(exception_rows)} rows")
print(f"Recommended actions: {len(recommended_actions)} rows")
