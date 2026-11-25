"""Unit tests for the pure rule modules (no I/O)."""

import importlib

import numpy as np
import pandas as pd

from backend.app.validator import validate_invoice, normalize_currency
from backend.app.matching import match_invoice
from backend.app.classify import classify_invoice
from backend.app.schemas import MatchResult
from backend.app.helper import (
    unwrap_confident_fields, extract_confidences, to_number, normalize_invoice, process_context, jsonable,
)
from tests.conftest import SCENARIOS


def plain(name):
    inv, po, gr = SCENARIOS[name]
    return normalize_invoice(unwrap_confident_fields(inv.model_dump())), po.model_dump(), gr.model_dump()


# ---------- validator ----------

def test_valid_invoice_passes():
    inv, _, _ = plain("matching")
    assert validate_invoice(inv) == (True, [])


def test_none_invoice_is_invalid_not_crash():
    ok, errors = validate_invoice(None)
    assert not ok and errors


def test_missing_and_bad_fields():
    ok, errors = validate_invoice({"invoice_number": "1", "vendor_name": "", "invoice_date": "31/31/2026",
                                   "total_amount": -5, "currency": "XYZ", "tax_amount": "abc"})
    assert not ok
    text = " ".join(errors)
    for needle in ("vendor_name", "total_amount", "tax_amount", "invoice_date", "currency"):
        assert needle in text


def test_currency_symbol_normalized():
    assert normalize_currency("$") == "USD"
    assert normalize_currency(" inr ") == "INR"


# ---------- helper ----------

def test_numeric_strings_coerced_so_validation_passes():
    raw = SCENARIOS["matching"][0].model_dump()
    raw["total_amount"]["value"] = "1,220.00"
    raw["currency"]["value"] = "$"
    inv = normalize_invoice(unwrap_confident_fields(raw))
    assert inv["total_amount"] == 1220.0 and inv["currency"] == "USD"
    assert validate_invoice(inv)[0]


def test_goods_receipt_date_normalized_for_db():
    from backend.app.helper import normalize_goods_receipt
    gr = normalize_goods_receipt({"po_number": "P", "received_date": "Nov 2, 2026",
                                  "line_items": [{"description": "x", "quantity_received": "3"}]})
    assert gr["received_date"] == "2026-11-02" and gr["line_items"][0]["quantity_received"] == 3.0
    assert normalize_goods_receipt({"received_date": "sometime"})["received_date"] is None


def test_to_number():
    assert to_number("$220") == 220.0
    assert to_number("abc") == "abc"
    assert to_number(None) is None


def test_confidences_skip_missing_values():
    raw = SCENARIOS["matching"][0].model_dump()
    raw["po_number"] = {"value": None, "confidence": 0.0}
    conf = extract_confidences(raw)
    assert "po_number" not in conf and conf["invoice_number"] == 0.95


def test_process_context_describes_real_issue_fields():
    inv, po, gr = plain("mismatch")
    result = match_invoice(inv, po, gr)
    report = {"stages": {"matching": {"issues": [i.model_dump() for i in result.issues]}, "risk": {"tier": "high"}}}
    signals = " ".join(process_context(report)["signals"])
    assert "Unit price differs" in signals and "exceeds received quantity" in signals
    assert "mismatch detected with" not in signals  # every field format recognised


def test_explanation_context_carries_decision():
    ctx = process_context({"stages": {"approval": {"decision": "auto_approved"}, "risk": {"tier": "low"}}})
    assert ctx["decision"] == "auto_approved"


def test_jsonable_handles_numpy_and_decimal():
    from decimal import Decimal
    out = jsonable({"a": np.int64(3), "b": [np.float64(1.5)], "c": Decimal("2.5"), "d": np.bool_(True)})
    assert out == {"a": 3, "b": [1.5], "c": 2.5, "d": True}


# ---------- matching ----------

def test_matching_set_reconciles():
    inv, po, gr = plain("matching")
    result = match_invoice(inv, po, gr)
    assert result.matched and result.issues == []


def test_mismatch_set_flags_price_qty_total():
    inv, po, gr = plain("mismatch")
    fields = {i.field for i in match_invoice(inv, po, gr).issues}
    assert {"GR:qty:office printer", "Invoice:price:office printer",
            "Invoice:qty:office printer", "total_amount"} <= fields


def test_underbilling_is_warning_not_critical():
    inv, po, gr = plain("matching")
    inv["line_items"][0]["unit_price"] = 80.0
    inv["total_amount"] = 2 * 80 + 20
    result = match_invoice(inv, po, gr)
    low = [i for i in result.issues if i.field.startswith("Invoice:price_low:")]
    assert low and low[0].severity == "warning"


def test_missing_po_number_is_warning():
    inv, po, gr = plain("matching")
    po["po_number"] = None
    result = match_invoice(inv, po, gr)
    assert not result.matched and result.issues[0].field == "po_number"


# ---------- classify / approval ----------

def test_classification():
    assert classify_invoice({"line_items": [{"description": "Office Printer"}]})["primary_category"] == "Office Supplies"
    assert classify_invoice({"line_items": []})["primary_category"] == "Uncategorized"


def test_approval_limits_from_env_are_numeric(monkeypatch):
    monkeypatch.setenv("AUTO_APPROVE_LIMIT", "1000")
    monkeypatch.setenv("DIRECTOR_REVIEW_LIMIT", "3000")
    from backend.app import approval
    approval = importlib.reload(approval)
    try:
        matched = MatchResult(matched=True)
        assert approval.route_approval({"total_amount": 500.0}, {"tier": "low"}, matched)["decision"] == "auto_approved"
        assert approval.route_approval({"total_amount": 1500.0}, {"tier": "low"}, matched)["approver"] == "AP Team"
        assert approval.route_approval({"total_amount": 5000.0}, {"tier": "medium"}, matched)["approver"] == "Finance Director"
        assert approval.route_approval({"total_amount": 10.0}, {"tier": "high"}, matched)["approver"] == "AP Manager"
    finally:
        monkeypatch.delenv("AUTO_APPROVE_LIMIT")
        monkeypatch.delenv("DIRECTOR_REVIEW_LIMIT")
        importlib.reload(approval)


# ---------- anomaly features ----------

def test_inference_features_use_vendor_history():
    from backend.app.anomaly_detection.predict import _feature_row
    history = pd.DataFrame([
        {"id": i, "user_id": 1, "vendor_name": "acme", "currency": "USD", "total_amount": 100.0,
         "tax_amount": 0.0, "invoice_date": f"2026-0{i}-01", "line_items": [{"unit_price": 100.0}]}
        for i in range(1, 6)
    ])
    row = _feature_row({"vendor_name": "Acme", "currency": "USD", "total_amount": 1000.0, "tax_amount": 0,
                        "invoice_date": "2026-07-01", "line_items": [{"unit_price": 1000.0}]}, 1, history).iloc[0]
    assert row["vendor_invoice_frequency"] == 6
    assert row["invoice_total_ratio"] > 3   # clearly above the vendor norm (was always 1.0 before)
    assert row["days_since_last_vendor_invoice"] == 61  # 2026-05-01 → 2026-07-01
