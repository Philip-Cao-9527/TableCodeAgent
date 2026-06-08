"""solve.py — finance_operations_001: no-helper B2B AR reconciliation & risk workflow."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
TASK = json.loads((HERE / "task.json").read_text("utf-8"))
CFG = TASK["finance_config"]

def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(HERE / CFG["tables"][name], dtype_backend="numpy_nullable",
                       keep_default_na=True)

invoices_raw: pd.DataFrame = _load("invoices")
payments_raw: pd.DataFrame = _load("payments")
customers_raw: pd.DataFrame = _load("customers")
disputes_raw: pd.DataFrame = _load("disputes")
adjustments_raw: pd.DataFrame = _load("adjustments")
policy_raw: pd.DataFrame = _load("policy")

# ── policy constants ───────────────────────────────────────────────────────
POL = policy_raw.iloc[0]
REF_DATE = pd.Timestamp(POL["reference_date"])
BASE_CCY = str(POL["base_currency"])
LOSS_RATES: dict[str, Decimal] = {
    "not_due":          Decimal(str(POL["loss_rate_not_due"])),
    "0-30":             Decimal(str(POL["loss_rate_0_30"])),
    "31-60":            Decimal(str(POL["loss_rate_31_60"])),
    "61-90":            Decimal(str(POL["loss_rate_61_90"])),
    "90+":              Decimal(str(POL["loss_rate_90_plus"])),
    "missing_due_date": Decimal(str(POL["loss_rate_missing_due_date"])),
}

# ── helpers ────────────────────────────────────────────────────────────────
def _is_missing(val: object) -> bool:
    """True for blank, whitespace, NaN, NaT, 'nan', 'NaN', 'NaT', 'None', 'null'."""
    if val is None:
        return True
    if isinstance(val, float) and np.isnan(val):
        return True
    if hasattr(pd, "isna") and pd.isna(val):
        return True
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in ("nan", "nat", "none", "null"):
            return True
        return False
    return False

def _parse_ts(val: object) -> pd.Timestamp | None:
    if _is_missing(val):
        return None
    try:
        return pd.Timestamp(val)
    except Exception:
        return None

def _d2(val: Decimal | float | str) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _safe_float(val: object) -> float:
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return 0.0

# ── 1. Normalise invoices ─────────────────────────────────────────────────
inv = invoices_raw.copy()
inv["invoice_amount"] = inv["invoice_amount"].astype(float)

# detect duplicate invoice_id — keep first
dup_inv_mask = inv["invoice_id"].duplicated(keep="first")
dup_inv_ids = sorted(inv.loc[dup_inv_mask, "invoice_id"].unique().tolist())
inv = inv[~dup_inv_mask].copy()

# negative invoice_amount rows → excluded from AR
neg_mask = inv["invoice_amount"] < 0
neg_inv_ids = sorted(inv.loc[neg_mask, "invoice_id"].tolist())
inv_valid = inv[~neg_mask].copy()          # used for reconciliation
inv_excluded = inv[neg_mask].copy()        # keep for output

# parse dates
inv_valid["invoice_date_ts"] = inv_valid["invoice_date"].apply(_parse_ts)
inv_valid["due_date_ts"] = inv_valid["due_date"].apply(_parse_ts)
inv_valid["due_date_str"] = inv_valid["due_date_ts"].apply(
    lambda x: x.strftime("%Y-%m-%d") if x is not None else None
)
inv_valid["due_date_missing"] = inv_valid["due_date_ts"].isna()

# missing PO
inv_valid["po_missing"] = inv_valid["po_number"].apply(_is_missing)
missing_po_ids = sorted(inv_valid.loc[inv_valid["po_missing"], "invoice_id"].tolist())

# ── 2. Normalise payments ──────────────────────────────────────────────────
pmt = payments_raw.copy()
pmt["payment_amount"] = pmt["payment_amount"].astype(float)

dup_pmt_mask = pmt["payment_id"].duplicated(keep="first")
dup_pmt_ids = sorted(pmt.loc[dup_pmt_mask, "payment_id"].unique().tolist())
pmt = pmt[~dup_pmt_mask].copy()

pmt["payment_date_ts"] = pmt["payment_date"].apply(_parse_ts)
pmt["gl_date_ts"] = pmt["gl_date"].apply(_parse_ts)

# classify
pmt["is_posted"] = pmt["status"].str.strip().str.lower() == "posted"
pmt["is_future"] = pmt["payment_date_ts"].apply(
    lambda x: x is not None and x.date() > REF_DATE.date()
) | pmt["gl_date_ts"].apply(
    lambda x: x is not None and x.date() > REF_DATE.date()
)
pmt["is_applicable"] = pmt["is_posted"] & ~pmt["is_future"]

# non-posted and future-dated payment IDs for DQ
non_posted_ids = sorted(pmt.loc[~pmt["is_posted"], "payment_id"].tolist())
future_ids = sorted(pmt.loc[pmt["is_future"], "payment_id"].tolist())

# ── 3. Adjustments (approved only affect balance) ─────────────────────────
adj = adjustments_raw.copy()
adj["amount"] = adj["amount"].astype(float)
adj["is_approved"] = adj["status"].str.strip().str.lower() == "approved"
adj["adj_type"] = adj["adjustment_type"].str.strip().str.lower()

# approved credit_memo / write_off reduce balance; chargeback increases
def adj_net_effect(row: pd.Series) -> float:
    t = row["adj_type"]
    if t in ("credit_memo", "write_off"):
        return row["amount"]  # already negative, keeps being negative (reduces)
    elif t == "chargeback":
        return row["amount"]   # positive → increases balance
    return 0.0

adj["net_effect"] = adj.apply(adj_net_effect, axis=1)

# pending write-off adjustments
pending_wo = adj[(adj["adj_type"] == "write_off") & (~adj["is_approved"])].copy()

# unmatched adjustments (invoice not in valid invoices)
valid_inv_ids = set(inv_valid["invoice_id"].tolist())
adj["inv_exists"] = adj["invoice_id"].apply(
    lambda x: not _is_missing(x) and str(x).strip() in valid_inv_ids
)
unmatched_adj = adj[~adj["inv_exists"]].copy()
unmatched_adj_ids = sorted(unmatched_adj["adjustment_id"].tolist())

# ── 4. Disputes (open) ────────────────────────────────────────────────────
disp = disputes_raw.copy()
disp["dispute_amount"] = disp["dispute_amount"].astype(float)
disp_open = disp[disp["status"].str.strip().str.lower() == "open"].copy()

# aggregate dispute amounts by invoice (open disputes only)
disp_by_inv = disp_open.groupby("invoice_id", as_index=False).agg(
    disputed_amount=("dispute_amount", "sum")
)

# ── 5. Build invoice-level reconciliation ──────────────────────────────────
rows: list[dict[str, Any]] = []

# lookup maps
cust_map = customers_raw.set_index("customer_id").to_dict(orient="index")
adj_by_inv = adj[adj["is_approved"] & adj["inv_exists"]].groupby("invoice_id")["net_effect"].sum()
pmt_applicable = pmt[pmt["is_applicable"]].copy()

for _, inv_row in inv_valid.iterrows():
    iid = inv_row["invoice_id"]
    cid = inv_row["customer_id"]
    inv_amt = _safe_float(inv_row["invoice_amount"])
    ccy = str(inv_row["currency"]).strip()
    due_ts = inv_row["due_date_ts"]
    due_missing = inv_row["due_date_missing"]
    due_str = inv_row["due_date_str"]

    # ---- approved adjustment ----
    approved_adj = float(adj_by_inv.get(iid, 0.0))
    adjusted_amt = inv_amt + approved_adj

    # ---- applicable payments for this invoice ----
    inv_pmts = pmt_applicable[pmt_applicable["invoice_id"] == iid].copy()
    if not inv_pmts.empty:
        # check currency match for each payment
        pmt_amt_total = Decimal("0")
        overpayment_excess = Decimal("0")
        for _, pmt_row in inv_pmts.iterrows():
            pmt_ccy = str(pmt_row["currency"]).strip()
            if pmt_ccy != ccy:
                # currency mismatch → this payment is unapplied cash
                continue
            pmt_amt_total += Decimal(str(pmt_row["payment_amount"]))

        applied_dec = min(pmt_amt_total, Decimal(str(adjusted_amt)))
        overpayment_dec = max(pmt_amt_total - Decimal(str(adjusted_amt)), Decimal("0"))
        open_dec = Decimal(str(adjusted_amt)) - applied_dec
        if open_dec < 0:
            open_dec = Decimal("0")
    else:
        applied_dec = Decimal("0")
        overpayment_dec = Decimal("0")
        open_dec = Decimal(str(adjusted_amt))

    applied = float(applied_dec)
    overpayment = float(overpayment_dec)
    open_amt = float(open_dec)

    # ---- dispute amount ----
    disp_info = disp_by_inv[disp_by_inv["invoice_id"] == iid]
    disputed = float(disp_info["disputed_amount"].sum()) if not disp_info.empty else 0.0
    disputed = min(disputed, open_amt)  # cap at open amount

    # ---- aging ----
    if due_missing or due_ts is None:
        bucket = "missing_due_date"
        days_overdue = None
        due_out = None
    else:
        due_out = due_str
        delta = (REF_DATE.date() - due_ts.date()).days
        if delta <= 0:
            bucket = "not_due"
            days_overdue = None
        elif delta <= 30:
            bucket = "0-30"
            days_overdue = delta
        elif delta <= 60:
            bucket = "31-60"
            days_overdue = delta
        elif delta <= 90:
            bucket = "61-90"
            days_overdue = delta
        else:
            bucket = "90+"
            days_overdue = delta

    # ---- exception tags ----
    exc_tags: list[str] = []
    if overpayment > 0:
        exc_tags.append("overpayment")
    if open_amt > 0 and applied > 0 and overpayment == 0:
        exc_tags.append("partial_payment")
    if disputed > 0:
        exc_tags.append("disputed_invoice")
    if due_missing:
        exc_tags.append("missing_due_date")
    if inv_row["po_missing"]:
        exc_tags.append("missing_po")
    # term mismatch
    cid_info = cust_map.get(cid)
    if cid_info is not None and not due_missing and due_ts is not None:
        inv_date = inv_row["invoice_date_ts"]
        if inv_date is not None:
            terms = int(cid_info["credit_terms_days"])
            expected_due = inv_date + pd.DateOffset(days=terms)
            if due_ts.date() != expected_due.date():
                exc_tags.append("term_mismatch")
    # chargeback
    inv_chargebacks = adj[(adj["invoice_id"] == iid) & (adj["adj_type"] == "chargeback") & (adj["is_approved"])]
    if not inv_chargebacks.empty:
        exc_tags.append("chargeback")

    # ---- status ----
    if open_amt == 0 and overpayment > 0:
        inv_status = "overpaid"
    elif open_amt == 0:
        inv_status = "closed"
    elif iid in neg_inv_ids:
        inv_status = "excluded"
    else:
        inv_status = "open"

    # ---- expected credit loss ----
    risk_amt = max(0.0, open_amt - disputed)
    ecl = float(Decimal(str(risk_amt)) * LOSS_RATES[bucket])

    rows.append({
        "invoice_id": iid,
        "customer_id": cid,
        "currency": ccy,
        "invoice_amount": _d2(inv_amt),
        "approved_adjustment_amount": _d2(approved_adj),
        "adjusted_invoice_amount": _d2(adjusted_amt),
        "applied_amount": _d2(applied),
        "open_amount": _d2(open_amt),
        "overpayment_amount": _d2(overpayment),
        "disputed_open_amount": _d2(disputed),
        "expected_credit_loss": _d2(ecl),
        "due_date": due_out,
        "days_overdue": days_overdue,
        "aging_bucket": bucket,
        "status": inv_status,
        "exception_tags": sorted(exc_tags),
    })

invoice_reconciliation = sorted(rows, key=lambda r: r["invoice_id"])

# ── 6. Unapplied cash ─────────────────────────────────────────────────────
# includes: payments with blank/invalid invoice_id, currency-mismatch payments,
#           and overpayment excess from invoices
unapplied_items: list[dict] = []

# 6a. payments with no invoice_id or invalid invoice_id
for _, pmt_row in pmt_applicable.iterrows():
    pid = pmt_row["payment_id"]
    inv_ref = str(pmt_row["invoice_id"]).strip() if not _is_missing(pmt_row["invoice_id"]) else ""
    if not inv_ref or inv_ref not in valid_inv_ids:
        unapplied_items.append({
            "payment_id": pid,
            "amount": float(pmt_row["payment_amount"]),
            "currency": str(pmt_row["currency"]).strip(),
            "reason": "unknown_invoice" if inv_ref else "blank_invoice",
        })
        continue

# 6b. currency-mismatch payments (already filtered out in reconciliation)
for _, pmt_row in pmt_applicable.iterrows():
    pid = pmt_row["payment_id"]
    inv_ref = str(pmt_row["invoice_id"]).strip() if not _is_missing(pmt_row["invoice_id"]) else ""
    if inv_ref and inv_ref in valid_inv_ids:
        inv_ccy = inv_valid.loc[inv_valid["invoice_id"] == inv_ref, "currency"].iloc[0]
        pmt_ccy = str(pmt_row["currency"]).strip()
        if pmt_ccy != inv_ccy:
            unapplied_items.append({
                "payment_id": pid,
                "amount": float(pmt_row["payment_amount"]),
                "currency": pmt_ccy,
                "reason": "currency_mismatch",
            })

# deduplicate unapplied items by payment_id
seen_pids = set()
deduped_unapplied: list[dict] = []
for item in unapplied_items:
    if item["payment_id"] not in seen_pids:
        seen_pids.add(item["payment_id"])
        deduped_unapplied.append(item)
unapplied_items = deduped_unapplied

# 6c. overpayment excess from invoices
overpayment_total_by_ccy: dict[str, Decimal] = {}
for r in invoice_reconciliation:
    if r["overpayment_amount"] > 0:
        ccy = r["currency"]
        overpayment_total_by_ccy[ccy] = overpayment_total_by_ccy.get(ccy, Decimal("0")) + Decimal(str(r["overpayment_amount"]))

# ── 7. Summary ─────────────────────────────────────────────────────────────
summary_inv_total_by_ccy: dict[str, float] = {}
summary_applied_by_ccy: dict[str, float] = {}
summary_adj_by_ccy: dict[str, float] = {}
summary_open_by_ccy: dict[str, float] = {}
summary_disputed_by_ccy: dict[str, float] = {}
summary_ecl_by_ccy: dict[str, float] = {}
summary_unapplied_cash_by_ccy: dict[str, float] = {}

for r in invoice_reconciliation:
    c = r["currency"]
    summary_inv_total_by_ccy[c] = _d2(summary_inv_total_by_ccy.get(c, 0) + r["invoice_amount"])
    summary_applied_by_ccy[c] = _d2(summary_applied_by_ccy.get(c, 0) + r["applied_amount"])
    summary_adj_by_ccy[c] = _d2(summary_adj_by_ccy.get(c, 0) + r["approved_adjustment_amount"])
    summary_open_by_ccy[c] = _d2(summary_open_by_ccy.get(c, 0) + r["open_amount"])
    summary_disputed_by_ccy[c] = _d2(summary_disputed_by_ccy.get(c, 0) + r["disputed_open_amount"])
    summary_ecl_by_ccy[c] = _d2(summary_ecl_by_ccy.get(c, 0) + r["expected_credit_loss"])

# unapplied cash from payments
for item in unapplied_items:
    c = item["currency"]
    summary_unapplied_cash_by_ccy[c] = _d2(summary_unapplied_cash_by_ccy.get(c, 0) + item["amount"])
# add overpayment excess
for ccy, amt in overpayment_total_by_ccy.items():
    summary_unapplied_cash_by_ccy[ccy] = _d2(summary_unapplied_cash_by_ccy.get(ccy, 0) + float(amt))

summary = {
    "reference_date": str(REF_DATE.date()),
    "base_currency": BASE_CCY,
    "invoice_row_count": len(invoices_raw),
    "unique_invoice_count": len(inv),
    "duplicate_invoice_count": len(dup_inv_ids),
    "payment_row_count": len(payments_raw),
    "duplicate_payment_count": len(dup_pmt_ids),
    "total_invoice_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_inv_total_by_ccy.items())},
    "applied_payment_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_applied_by_ccy.items())},
    "approved_adjustment_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_adj_by_ccy.items())},
    "open_invoice_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_open_by_ccy.items())},
    "unapplied_cash_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_unapplied_cash_by_ccy.items())},
    "disputed_open_amount_by_currency": {k: _d2(v) for k, v in sorted(summary_disputed_by_ccy.items())},
    "expected_credit_loss_by_currency": {k: _d2(v) for k, v in sorted(summary_ecl_by_ccy.items())},
}

# ── 8. Aging buckets ──────────────────────────────────────────────────────
bucket_order = ["not_due", "0-30", "31-60", "61-90", "90+", "missing_due_date"]
aging_map: dict[tuple[str, str], dict] = {}

for r in invoice_reconciliation:
    key = (r["currency"], r["aging_bucket"])
    if key not in aging_map:
        aging_map[key] = {
            "currency": r["currency"],
            "bucket": r["aging_bucket"],
            "invoice_count": 0,
            "open_amount": 0.0,
            "risk_amount_excluding_disputed": 0.0,
            "expected_credit_loss": 0.0,
        }
    aging_map[key]["invoice_count"] += 1
    aging_map[key]["open_amount"] = _d2(aging_map[key]["open_amount"] + r["open_amount"])
    risk = max(0.0, r["open_amount"] - r["disputed_open_amount"])
    aging_map[key]["risk_amount_excluding_disputed"] = _d2(aging_map[key]["risk_amount_excluding_disputed"] + risk)
    aging_map[key]["expected_credit_loss"] = _d2(aging_map[key]["expected_credit_loss"] + r["expected_credit_loss"])

aging_buckets = sorted(aging_map.values(), key=lambda x: (x["currency"], bucket_order.index(x["bucket"])))

# ── 9. Customer risk ──────────────────────────────────────────────────────
customer_risk_rows: list[dict] = []

for cid, cinfo in customers_raw.iterrows():
    cid_str = cinfo["customer_id"]
    invs_for_cust = [r for r in invoice_reconciliation if r["customer_id"] == cid_str]

    open_by_ccy: dict[str, float] = {}
    overdue_by_ccy: dict[str, float] = {}
    disputed_ccy: dict[str, float] = {}
    risk_ccy: dict[str, float] = {}
    ecl_ccy: dict[str, float] = {}
    max_days = None

    for r in invs_for_cust:
        c = r["currency"]
        open_by_ccy[c] = _d2(open_by_ccy.get(c, 0) + r["open_amount"])
        if r["days_overdue"] is not None and r["days_overdue"] > 0:
            overdue_by_ccy[c] = _d2(overdue_by_ccy.get(c, 0) + r["open_amount"])
        disputed_ccy[c] = _d2(disputed_ccy.get(c, 0) + r["disputed_open_amount"])
        risk = max(0.0, r["open_amount"] - r["disputed_open_amount"])
        risk_ccy[c] = _d2(risk_ccy.get(c, 0) + risk)
        ecl_ccy[c] = _d2(ecl_ccy.get(c, 0) + r["expected_credit_loss"])
        if r["days_overdue"] is not None:
            if max_days is None or r["days_overdue"] > max_days:
                max_days = r["days_overdue"]

    total_open = sum(open_by_ccy.values())
    cust_status = str(cinfo["status"]).strip().lower()

    # Determine risk band
    has_90_plus = any(r["aging_bucket"] == "90+" for r in invs_for_cust)
    has_over_limit = False
    if total_open > 0:
        limit = float(cinfo["credit_limit"])
        if total_open > limit:
            has_over_limit = True

    if cust_status != "active" and total_open > 0:
        risk_band = "high"
    elif has_90_plus:
        risk_band = "high"
    elif has_over_limit:
        risk_band = "medium"
    elif total_open > 0:
        risk_band = "medium"
    else:
        risk_band = "low"

    # Action tags
    action_tags: list[str] = []
    rationale: list[str] = []

    for r in invs_for_cust:
        if r["aging_bucket"] == "90+" and r["open_amount"] > 0:
            if "collect_90_plus" not in action_tags:
                action_tags.append("collect_90_plus")
                rationale.append(f"Invoice {r['invoice_id']} is 90+ days overdue ({r['days_overdue']}d)")
        if r["aging_bucket"] in ("31-60", "61-90") and r["open_amount"] > 0:
            if "collect_31_90" not in action_tags:
                action_tags.append("collect_31_90")
                rationale.append(f"Invoice {r['invoice_id']} is {r['aging_bucket']} days overdue")
        if r["disputed_open_amount"] > 0:
            if "resolve_dispute" not in action_tags:
                action_tags.append("resolve_dispute")
                rationale.append(f"Invoice {r['invoice_id']} has open dispute ${r['disputed_open_amount']:.2f}")
        if "missing_due_date" in r["exception_tags"]:
            if "fix_missing_due_date" not in action_tags:
                action_tags.append("fix_missing_due_date")
                rationale.append(f"Invoice {r['invoice_id']} has no due date")
        if "missing_po" in r["exception_tags"]:
            if "request_documentation" not in action_tags:
                action_tags.append("request_documentation")
                rationale.append(f"Invoice {r['invoice_id']} is missing PO number")
        if "chargeback" in r["exception_tags"]:
            if "investigate_chargeback" not in action_tags:
                action_tags.append("investigate_chargeback")
                rationale.append(f"Invoice {r['invoice_id']} has an approved chargeback")

    if cust_status != "active" and total_open > 0:
        action_tags.append("review_customer_status")
        rationale.append(f"Customer status is '{cust_status}' with open receivables")

    if has_over_limit:
        action_tags.append("review_credit_hold")
        limit = float(cinfo["credit_limit"])
        rationale.append(f"Open exposure ${total_open:.2f} exceeds credit limit ${limit:.2f}")

    # unapplied cash check for this customer
    cust_unapplied = [item for item in unapplied_items
                      if pmt.loc[pmt["payment_id"] == item["payment_id"], "customer_id"].iloc[0] == cid_str] if any(
        pmt["payment_id"].isin([i["payment_id"] for i in unapplied_items if "payment_id" in i])
    ) else []
    # simpler: check if any unapplied items belong to this customer
    has_unapplied = False
    for item in unapplied_items:
        pid = item.get("payment_id", "")
        if pid:
            pmt_row = pmt[pmt["payment_id"] == pid]
            if not pmt_row.empty and pmt_row.iloc[0]["customer_id"] == cid_str:
                has_unapplied = True
                break
    if has_unapplied or (cid_str in [r["customer_id"] for r in invoice_reconciliation if r["overpayment_amount"] > 0]):
        # check if this customer has either unapplied payments or overpayment
        cust_overpmt = sum(Decimal(str(r["overpayment_amount"])) for r in invoice_reconciliation
                           if r["customer_id"] == cid_str)
        if float(cust_overpmt) > 0:
            if "apply_unapplied_cash" not in action_tags:
                action_tags.append("apply_unapplied_cash")
                rationale.append(f"Customer has ${float(cust_overpmt):.2f} overpayment/unapplied cash")
        elif has_unapplied:
            if "apply_unapplied_cash" not in action_tags:
                action_tags.append("apply_unapplied_cash")
                rationale.append("Customer has unapplied cash payments")

    # remove duplicates
    action_tags = list(dict.fromkeys(action_tags))

    customer_risk_rows.append({
        "customer_id": cid_str,
        "customer_name": str(cinfo["customer_name"]),
        "status": cust_status,
        "risk_band": risk_band,
        "open_amount_by_currency": {k: _d2(v) for k, v in sorted(open_by_ccy.items())},
        "overdue_amount_by_currency": {k: _d2(v) for k, v in sorted(overdue_by_ccy.items())},
        "disputed_open_amount_by_currency": {k: _d2(v) for k, v in sorted(disputed_ccy.items())},
        "risk_amount_excluding_disputed_by_currency": {k: _d2(v) for k, v in sorted(risk_ccy.items())},
        "expected_credit_loss_by_currency": {k: _d2(v) for k, v in sorted(ecl_ccy.items())},
        "max_days_overdue": max_days,
        "action_tags": action_tags,
        "rationale": rationale,
    })

# sort: risk_band high->medium->low, then desc total open, then customer_id
band_rank = {"high": 0, "medium": 1, "low": 2}
customer_risk = sorted(customer_risk_rows, key=lambda r: (
    band_rank.get(r["risk_band"], 9),
    -sum(r["open_amount_by_currency"].values()),
    r["customer_id"],
))

# ── 10. Exceptions ─────────────────────────────────────────────────────────
exceptions_list: list[dict] = []

# helper to build exception rows
def exc_row(etype: str, severity: str, count: int, amount_by_ccy: dict[str, float],
            related_ids: list[str], description: str) -> dict:
    return {
        "exception_type": etype,
        "severity": severity,
        "count": count,
        "amount_by_currency": {k: _d2(v) for k, v in sorted(amount_by_ccy.items())},
        "related_ids": sorted(related_ids),
        "description": description,
    }

# duplicate_invoice
if dup_inv_ids:
    exceptions_list.append(exc_row("duplicate_invoice", "warning", len(dup_inv_ids), {},
                                    dup_inv_ids, f"Duplicate invoice_ids found: {', '.join(dup_inv_ids)}"))

# duplicate_payment
if dup_pmt_ids:
    exceptions_list.append(exc_row("duplicate_payment", "warning", len(dup_pmt_ids), {},
                                    dup_pmt_ids, f"Duplicate payment_ids found: {', '.join(dup_pmt_ids)}"))

# partial_payment
partial_rows = [r for r in invoice_reconciliation if "partial_payment" in r["exception_tags"]]
if partial_rows:
    amt_ccy: dict[str, float] = {}
    ids: list[str] = []
    for r in partial_rows:
        amt_ccy[r["currency"]] = amt_ccy.get(r["currency"], 0) + r["open_amount"]
        ids.append(r["invoice_id"])
    exceptions_list.append(exc_row("partial_payment", "warning", len(partial_rows), amt_ccy,
                                    ids, "Invoices with partial payment applied"))

# overpayment
over_rows = [r for r in invoice_reconciliation if r["overpayment_amount"] > 0]
if over_rows:
    amt_ccy = {}
    ids = []
    for r in over_rows:
        amt_ccy[r["currency"]] = amt_ccy.get(r["currency"], 0) + r["overpayment_amount"]
        ids.append(r["invoice_id"])
    exceptions_list.append(exc_row("overpayment", "warning", len(over_rows), amt_ccy,
                                    ids, "Invoices where payments exceeded invoice amount"))

# approved_credit_memo
cm_adj = adj[(adj["adj_type"] == "credit_memo") & (adj["is_approved"])]
if not cm_adj.empty:
    amt_ccy = {}
    ids = []
    for _, a in cm_adj.iterrows():
        c = str(a["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + abs(float(a["amount"]))
        ids.append(str(a["adjustment_id"]))
    exceptions_list.append(exc_row("approved_credit_memo", "info", len(cm_adj), amt_ccy,
                                    ids, "Approved credit memo adjustments applied"))

# pending_write_off
if not pending_wo.empty:
    amt_ccy = {}
    ids = []
    for _, a in pending_wo.iterrows():
        c = str(a["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + abs(float(a["amount"]))
        ids.append(str(a["adjustment_id"]))
    exceptions_list.append(exc_row("pending_write_off", "warning", len(pending_wo), amt_ccy,
                                    ids, "Pending write-off adjustments do not reduce open AR"))

# chargeback
cb_adj = adj[(adj["adj_type"] == "chargeback") & (adj["is_approved"])]
if not cb_adj.empty:
    amt_ccy = {}
    ids = []
    for _, a in cb_adj.iterrows():
        c = str(a["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + float(a["amount"])
        ids.append(str(a["adjustment_id"]))
    exceptions_list.append(exc_row("chargeback", "critical", len(cb_adj), amt_ccy,
                                    ids, "Approved chargeback adjustments increasing invoice balance"))

# unapplied_cash
if unapplied_items or any(float(v) > 0 for v in overpayment_total_by_ccy.values()):
    amt_ccy = {}
    ids = []
    for item in unapplied_items:
        c = item["currency"]
        amt_ccy[c] = amt_ccy.get(c, 0) + item["amount"]
        ids.append(item["payment_id"])
    # add overpayment excess amounts
    for ccy, amt in overpayment_total_by_ccy.items():
        amt_ccy[ccy] = amt_ccy.get(ccy, 0) + float(amt)
    exceptions_list.append(exc_row("unapplied_cash", "warning", len(unapplied_items) + (1 if overpayment_total_by_ccy else 0),
                                    amt_ccy, ids, "Unapplied cash including unknown invoice, currency mismatch, and overpayment excess"))

# currency_mismatch
ccy_mismatch_pmts = [item for item in unapplied_items if item.get("reason") == "currency_mismatch"]
cm_ids = [item["payment_id"] for item in ccy_mismatch_pmts]
if cm_ids:
    amt_ccy = {}
    for item in ccy_mismatch_pmts:
        c = item["currency"]
        amt_ccy[c] = amt_ccy.get(c, 0) + item["amount"]
    exceptions_list.append(exc_row("currency_mismatch", "warning", len(cm_ids), amt_ccy,
                                    cm_ids, "Payments with currency mismatch to the matched invoice"))

# negative_invoice_amount
if neg_inv_ids:
    amt_ccy = {}
    for _, r in inv_excluded.iterrows():
        c = str(r["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + abs(float(r["invoice_amount"]))
    exceptions_list.append(exc_row("negative_invoice_amount", "critical", len(neg_inv_ids), amt_ccy,
                                    neg_inv_ids, "Invoices with negative amount excluded from AR"))

# missing_due_date
missing_due_ids = sorted(inv_valid.loc[inv_valid["due_date_missing"], "invoice_id"].tolist())
if missing_due_ids:
    amt_ccy = {}
    for _, r in inv_valid[inv_valid["due_date_missing"]].iterrows():
        c = str(r["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + float(r["invoice_amount"])
    exceptions_list.append(exc_row("missing_due_date", "warning", len(missing_due_ids), amt_ccy,
                                    missing_due_ids, "Invoices with missing due date"))

# disputed_invoice
disputed_inv_ids = list(disp_by_inv["invoice_id"])
if disputed_inv_ids:
    amt_ccy = {}
    for _, d in disp_by_inv.iterrows():
        inv_row_match = disp[disp["invoice_id"] == d["invoice_id"]]
        if not inv_row_match.empty:
            c = str(inv_row_match.iloc[0]["currency"]).strip()
            amt_ccy[c] = amt_ccy.get(c, 0) + float(d["disputed_amount"])
    exceptions_list.append(exc_row("disputed_invoice", "warning", len(disp_by_inv), amt_ccy,
                                    sorted(disputed_inv_ids), "Invoices with open disputes"))

# inactive_or_on_hold_customer
for cr in customer_risk_rows:
    if cr["status"] != "active" and sum(cr["open_amount_by_currency"].values()) > 0:
        exceptions_list.append(exc_row("inactive_or_on_hold_customer", "critical", 1, cr["open_amount_by_currency"],
                                        [cr["customer_id"]], f"Customer {cr['customer_id']} has status '{cr['status']}' with open receivables"))

# future_dated_payment
if future_ids:
    amt_ccy = {}
    for pid in future_ids:
        pr = pmt[pmt["payment_id"] == pid].iloc[0]
        c = str(pr["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + float(pr["payment_amount"])
    exceptions_list.append(exc_row("future_dated_payment", "warning", len(future_ids), amt_ccy,
                                    future_ids, "Future-dated payments not applied to AR"))

# non_posted_payment
if non_posted_ids:
    amt_ccy = {}
    for pid in non_posted_ids:
        pr = pmt[pmt["payment_id"] == pid].iloc[0]
        c = str(pr["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + float(pr["payment_amount"])
    exceptions_list.append(exc_row("non_posted_payment", "warning", len(non_posted_ids), amt_ccy,
                                    non_posted_ids, "Non-posted payments not applied to AR"))

# unmatched_adjustment
if unmatched_adj_ids:
    amt_ccy = {}
    for _, a in unmatched_adj.iterrows():
        c = str(a["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + abs(float(a["amount"]))
    exceptions_list.append(exc_row("unmatched_adjustment", "warning", len(unmatched_adj), amt_ccy,
                                    unmatched_adj_ids, "Adjustments referencing non-existent invoices"))

# over_credit_limit
over_limit_custs = []
for cr in customer_risk_rows:
    total_open = sum(cr["open_amount_by_currency"].values())
    cust_info = cust_map.get(cr["customer_id"])
    if cust_info and total_open > 0:
        limit = float(cust_info["credit_limit"])
        if total_open > limit:
            over_limit_custs.append(cr["customer_id"])
if over_limit_custs:
    exceptions_list.append(exc_row("over_credit_limit", "critical", len(over_limit_custs), {},
                                    over_limit_custs, "Customers exceeding credit limit"))

# missing_po
if missing_po_ids:
    amt_ccy = {}
    for iid in missing_po_ids:
        r = inv_valid[inv_valid["invoice_id"] == iid].iloc[0]
        c = str(r["currency"]).strip()
        amt_ccy[c] = amt_ccy.get(c, 0) + float(r["invoice_amount"])
    exceptions_list.append(exc_row("missing_po", "warning", len(missing_po_ids), amt_ccy,
                                    missing_po_ids, "Invoices missing PO number"))

# term_mismatch
term_mismatch_ids = []
for r in invoice_reconciliation:
    if "term_mismatch" in r["exception_tags"]:
        term_mismatch_ids.append(r["invoice_id"])
if term_mismatch_ids:
    exceptions_list.append(exc_row("term_mismatch", "warning", len(term_mismatch_ids), {},
                                    term_mismatch_ids, "Invoices with due date not matching credit terms"))

# ── 11. Data quality ──────────────────────────────────────────────────────
# currency_mismatch_payment_ids
ccy_mismatch_pmt_ids = [item["payment_id"] for item in unapplied_items if item.get("reason") == "currency_mismatch"]

# unmatched_payment_ids (blank invoice or invalid invoice)
unmatched_pmt_ids = [item["payment_id"] for item in unapplied_items if item.get("reason") in ("blank_invoice", "unknown_invoice")]

data_quality = {
    "required_columns": CFG["required_columns"],
    "missing_required_columns": {},
    "duplicate_invoice_ids": dup_inv_ids,
    "duplicate_payment_ids": dup_pmt_ids,
    "invalid_invoice_ids": neg_inv_ids,
    "unmatched_payment_ids": sorted(unmatched_pmt_ids),
    "currency_mismatch_payment_ids": sorted(ccy_mismatch_pmt_ids),
    "missing_due_date_invoice_ids": missing_due_ids,
    "future_dated_payment_ids": future_ids,
    "non_posted_payment_ids": non_posted_ids,
    "unmatched_adjustment_ids": unmatched_adj_ids,
    "term_mismatch_invoice_ids": sorted(term_mismatch_ids),
    "missing_po_invoice_ids": missing_po_ids,
    "over_credit_limit_customer_ids": sorted(over_limit_custs),
}

# ── 12. Recommended actions ────────────────────────────────────────────────
actions_list: list[dict] = []

def add_action(cid: str, priority: str, action_type: str, invoice_ids: list[str], details: str):
    actions_list.append({
        "customer_id": cid,
        "priority": priority,
        "action_type": action_type,
        "invoice_ids": sorted(invoice_ids),
        "details": details,
    })

for cr in customer_risk_rows:
    cid = cr["customer_id"]
    invs_for_cust = [r for r in invoice_reconciliation if r["customer_id"] == cid]

    # collect_90_plus
    invs_90 = [r for r in invs_for_cust if r["aging_bucket"] == "90+" and r["open_amount"] > 0]
    if invs_90:
        total = sum(r["open_amount"] for r in invs_90)
        add_action(cid, "high", "collect_overdue", [r["invoice_id"] for r in invs_90],
                    f"Collect ${total:.2f} from {len(invs_90)} invoice(s) overdue 90+ days")

    # collect_31_90
    invs_31_90 = [r for r in invs_for_cust if r["aging_bucket"] in ("31-60", "61-90") and r["open_amount"] > 0]
    if invs_31_90:
        total = sum(r["open_amount"] for r in invs_31_90)
        add_action(cid, "medium", "collect_overdue", [r["invoice_id"] for r in invs_31_90],
                    f"Collect ${total:.2f} from {len(invs_31_90)} invoice(s) overdue 31-90 days")

    # resolve_dispute
    invs_disp = [r for r in invs_for_cust if r["disputed_open_amount"] > 0]
    if invs_disp:
        total = sum(r["disputed_open_amount"] for r in invs_disp)
        add_action(cid, "high", "resolve_dispute", [r["invoice_id"] for r in invs_disp],
                    f"Resolve ${total:.2f} in open disputes across {len(invs_disp)} invoice(s)")

    # fix_missing_due_date
    invs_missing_dd = [r for r in invs_for_cust if "missing_due_date" in r["exception_tags"]]
    if invs_missing_dd:
        add_action(cid, "medium", "fix_data_quality", [r["invoice_id"] for r in invs_missing_dd],
                    "Fix missing due date on invoice(s)")

    # apply_unapplied_cash (check if this customer has unapplied payments)
    cust_unapplied_pmts = []
    for item in unapplied_items:
        pid = item.get("payment_id", "")
        if pid:
            pmt_row = pmt[pmt["payment_id"] == pid]
            if not pmt_row.empty and pmt_row.iloc[0]["customer_id"] == cid:
                cust_unapplied_pmts.append(item)
    if cust_unapplied_pmts:
        total_ua = sum(item["amount"] for item in cust_unapplied_pmts)
        add_action(cid, "medium", "apply_unapplied_cash", [],
                    f"Apply ${total_ua:.2f} in unapplied cash ({len(cust_unapplied_pmts)} payment(s))")

    # review_customer_status
    if cr["status"] != "active" and sum(cr["open_amount_by_currency"].values()) > 0:
        add_action(cid, "high", "review_customer_status", [],
                    f"Customer status is '{cr['status']}' with open receivables — review and update")

    # review_credit_hold
    cust_info = cust_map.get(cid)
    if cust_info:
        total_open = sum(cr["open_amount_by_currency"].values())
        limit = float(cust_info["credit_limit"])
        if total_open > limit:
            add_action(cid, "high", "review_credit_hold", [],
                        f"Open exposure ${total_open:.2f} exceeds credit limit ${limit:.2f}")

    # investigate_chargeback
    invs_cb = [r for r in invs_for_cust if "chargeback" in r["exception_tags"]]
    if invs_cb:
        cb_amts = []
        for r in invs_cb:
            cb_match = adj[(adj["invoice_id"] == r["invoice_id"]) & (adj["adj_type"] == "chargeback") & (adj["is_approved"])]
            cb_amts.extend(cb_match["amount"].tolist())
        total_cb = sum(cb_amts)
        add_action(cid, "high", "investigate_chargeback", [r["invoice_id"] for r in invs_cb],
                    f"Investigate ${total_cb:.2f} in chargeback(s) on invoice(s)")

    # request_documentation (missing PO)
    invs_missing_po = [r for r in invs_for_cust if "missing_po" in r["exception_tags"]]
    if invs_missing_po:
        add_action(cid, "low", "request_documentation", [r["invoice_id"] for r in invs_missing_po],
                    "Request PO documentation for invoice(s) with missing PO number")

    # review_adjustment
    cust_adjs = adj[adj["customer_id"] == cid]
    pending_cust_adjs = cust_adjs[cust_adjs["status"].str.strip().str.lower() == "pending"]
    if not pending_cust_adjs.empty:
        add_action(cid, "medium", "review_adjustment", [],
                    f"{len(pending_cust_adjs)} pending adjustment(s) requiring review")

# ── 13. Audit notes ────────────────────────────────────────────────────────
audit_notes = [
    {"step": "load_policy", "evidence": f"Reference date {REF_DATE.date()}, base currency {BASE_CCY}"},
    {"step": "deduplicate_invoices", "evidence": f"Found {len(dup_inv_ids)} duplicate invoice(s): {', '.join(dup_inv_ids) if dup_inv_ids else 'none'}"},
    {"step": "deduplicate_payments", "evidence": f"Found {len(dup_pmt_ids)} duplicate payment(s): {', '.join(dup_pmt_ids) if dup_pmt_ids else 'none'}"},
    {"step": "exclude_negative_invoices", "evidence": f"Excluded {len(neg_inv_ids)} negative-amount invoice(s): {', '.join(neg_inv_ids) if neg_inv_ids else 'none'}"},
    {"step": "match_payments", "evidence": f"Applied {len(pmt_applicable)} payment(s); {len(unapplied_items)} unapplied item(s); {len(future_ids)} future-dated; {len(non_posted_ids)} non-posted"},
    {"step": "apply_adjustments", "evidence": f"Approved adjustments net {_d2(sum(summary_adj_by_ccy.values()))} total; {len(unmatched_adj_ids)} unmatched"},
    {"step": "compute_aging", "evidence": f"Aged {len(invoice_reconciliation)} invoices across {len(aging_buckets)} bucket-currency groups"},
    {"step": "compute_expected_credit_loss", "evidence": f"Total ECL {_d2(sum(summary_ecl_by_ccy.values()))}"},
    {"step": "identify_exceptions", "evidence": f"Generated {len(exceptions_list)} exception rows"},
    {"step": "generate_actions", "evidence": f"Generated {len(actions_list)} recommended actions across {len(customer_risk)} customers"},
]

# ── 14. Validation ─────────────────────────────────────────────────────────
validation = {
    "reference_date_used": str(REF_DATE.date()),
    "total_invoice_valid": len(inv_valid),
    "total_invoice_excluded": len(inv_excluded),
    "total_payments_valid": len(pmt),
    "total_applied_payments": int(pmt_applicable["payment_amount"].sum()) if not pmt_applicable.empty else 0,
    "total_unapplied_cash": _d2(sum(summary_unapplied_cash_by_ccy.values())),
    "net_ar_outstanding": _d2(sum(summary_open_by_ccy.values())),
}

# ── 15. Build answer ───────────────────────────────────────────────────────
answer = {
    "summary": summary,
    "customer_risk": customer_risk,
    "invoice_reconciliation": invoice_reconciliation,
    "aging_buckets": aging_buckets,
    "exceptions": exceptions_list,
    "recommended_actions": actions_list,
    "data_quality": data_quality,
    "audit_notes": audit_notes,
    "validation": validation,
}

(HERE / "answer.json").write_text(
    json.dumps(answer, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
)
print("solve.py completed — answer.json written.")
