"""Shared helpers: confidence handling, value coercion, vendor history, LLM context, JSON safety."""

import re

import numpy as np

from backend.app.db import get_connection


def unwrap_confident_fields(data: dict) -> dict:
    """Strips ConfidentField wrappers back to plain values, recursively.
    Call this once right after extraction — downstream code works on plain values."""
    result = {}
    for key, val in data.items():
        if isinstance(val, dict) and "value" in val and "confidence" in val:
            result[key] = val["value"]
        elif isinstance(val, list):
            result[key] = [unwrap_confident_fields(item) if isinstance(item, dict) else item for item in val]
        elif isinstance(val, dict):
            result[key] = unwrap_confident_fields(val)
        else:
            result[key] = val
    return result


def extract_confidences(data: dict) -> dict:
    """Header-level confidence scores, pulled out before unwrapping.
    Fields whose value is missing are skipped: a null field has nothing to be
    (un)confident about, and validation already reports missing fields."""
    return {
        key: val["confidence"]
        for key, val in data.items()
        if isinstance(val, dict) and "confidence" in val and val.get("value") not in (None, "")
    }


_NUMERIC_CLEAN = re.compile(r"[^0-9.\-]")


def to_number(value):
    """Coerce '1,234.50', '$220', ' 48 ' etc. to float. Returns the input unchanged if not parseable."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = _NUMERIC_CLEAN.sub("", value.replace(",", ""))
        if cleaned in ("", "-", ".", "-."):
            return value
        try:
            return float(cleaned)
        except ValueError:
            return value
    return value


def normalize_date(value):
    """Return an ISO 'YYYY-MM-DD' string for any supported format, or None if unparseable
    (so it is safe to store in a DATE column)."""
    from datetime import datetime
    from backend.app.validator import DATE_FORMATS

    if not value:
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def normalize_goods_receipt(gr: dict) -> dict:
    gr = dict(gr)
    gr["received_date"] = normalize_date(gr.get("received_date"))
    gr["line_items"] = [
        {**item, "quantity_received": to_number(item.get("quantity_received"))}
        for item in (gr.get("line_items") or [])
    ]
    return gr


def normalize_invoice(invoice: dict) -> dict:
    """Coerce numeric fields to floats and currency symbols to ISO codes after extraction."""
    from backend.app.validator import normalize_currency

    invoice = dict(invoice)
    for key in ("total_amount", "tax_amount"):
        invoice[key] = to_number(invoice.get(key))
    if isinstance(invoice.get("currency"), str):
        invoice["currency"] = normalize_currency(invoice["currency"])
    for key in ("invoice_number", "vendor_name", "po_number"):
        if invoice.get(key) is not None and not isinstance(invoice[key], str):
            invoice[key] = str(invoice[key])
    invoice["line_items"] = [
        {**item, "quantity": to_number(item.get("quantity")), "unit_price": to_number(item.get("unit_price"))}
        for item in (invoice.get("line_items") or [])
    ]
    return invoice


def get_vendor_history(vendor_name: str, user_id: int | None = None,
                       exclude_invoice_id: int | None = None) -> dict:
    """
    Historical stats for this vendor, scoped to the user and EXCLUDING the
    invoice currently being processed (it is inserted before risk analysis runs).
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT AVG(total_amount), COUNT(*) FROM invoices WHERE vendor_name = %s"
    params = [(vendor_name or "").strip().lower()]
    if user_id is not None:
        sql += " AND user_id = %s"
        params.append(user_id)
    if exclude_invoice_id is not None:
        sql += " AND id <> %s"
        params.append(exclude_invoice_id)
    cur.execute(sql, params)
    avg_amount, count = cur.fetchone()
    cur.close()
    conn.close()
    return {
        "is_new_vendor": count == 0,
        "avg_invoice_amount": float(avg_amount) if avg_amount is not None else None,
        "invoice_count": count,
    }


def _describe_issue(issue: dict) -> str:
    """Turn a matching issue (field formats from matching.py) into readable text."""
    field = issue.get("field", "") or ""
    expected, actual = issue.get("expected"), issue.get("actual")
    severity = issue.get("severity", "warning")
    lower = field.lower()

    if lower == "po/gr":
        return "Purchase order and/or goods receipt not provided, so 3-way matching could not run"
    if lower == "po_number":
        return "Purchase order number missing, so 3-way matching could not run"
    if lower == "total_amount":
        return f"Invoice subtotal differs from the expected value (expected {expected}, found {actual})"
    if lower.startswith("gr:qty:"):
        return f"Received quantity differs from ordered quantity for '{field[7:][:80]}' (ordered {expected}, received {actual})"
    if lower.startswith("gr:"):
        return f"Ordered item missing from goods receipt: '{field[3:][:80]}'"
    if lower.startswith("invoice:price:"):
        return f"Unit price differs from PO for '{field[14:][:80]}' (PO {expected}, invoiced {actual})"
    if lower.startswith("invoice:qty:"):
        return f"Invoiced quantity exceeds received quantity for '{field[12:][:80]}' (received {expected}, invoiced {actual})"
    if lower.startswith("invoice:"):
        return f"Invoiced item not on purchase order: '{field[8:][:80]}'"
    return f"{field} mismatch detected with {severity} severity"


def process_context(report: dict) -> dict:
    """Convert a full pipeline report into a compact, LLM-friendly explanation context."""
    stages = report.get("stages", {}) or {}
    validation = stages.get("validation") or {}
    matching = stages.get("matching") or {}
    risk = stages.get("risk") or {}
    warnings = stages.get("warnings") or []

    signals = [f"Validation error: {err}" for err in validation.get("errors") or []]
    signals += [_describe_issue(issue) for issue in matching.get("issues") or []]
    signals += list(risk.get("reasons") or [])

    for warning in warnings:
        if isinstance(warning, dict):
            for key, value in warning.items():
                signals.append(f"{key.replace('_', ' ').replace('-', ' ')}: {value}")
        else:
            signals.append(str(warning))

    return {
        "invoice_number": report.get("invoice_number"),
        "vendor_name": report.get("vendor_name"),
        "risk_level": risk.get("tier"),
        "risk_score": risk.get("score"),
        "signals": signals,
    }


def jsonable(value):
    """Recursively convert pipeline values (Pydantic, numpy, Decimal, dates) into JSON-safe primitives."""
    from datetime import date, datetime
    from decimal import Decimal

    if value is None:
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(i) for i in value]
    return value
