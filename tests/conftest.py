"""
Shared fixtures. Tests run fully offline: Gemini and PostgreSQL are replaced by
in-memory fakes, so no API key or database is needed.

Run from the project root:  python -m pytest -q
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Safe dummy config BEFORE any backend import (never real secrets).
os.environ["DB_URL"] = "postgresql://test:test@127.0.0.1:1/test_unused"
os.environ["JWT_SECRET"] = "test-secret-not-for-production"
os.environ["API_KEY"] = "test-key"
os.environ.pop("AUTO_APPROVE_LIMIT", None)
os.environ.pop("DIRECTOR_REVIEW_LIMIT", None)

from backend.app.schemas import Invoice, PurchaseOrder, GoodsReceipt  # noqa: E402


def cf(value, confidence=0.95):
    return {"value": value, "confidence": confidence}


def make_invoice(number="FC-INV-1001", vendor="Greenfield Supplies", qty=2, price=100.0, tax=20.0,
                 po_number="PO-1001", total=None, currency="USD"):
    total = qty * price + tax if total is None else total
    return Invoice(**{
        "invoice_number": cf(number),
        "vendor_name": cf(vendor),
        "invoice_date": cf("2026-11-01"),
        "po_number": cf(po_number),
        "total_amount": cf(total),
        "currency": cf(currency),
        "tax_amount": cf(tax),
        "line_items": [{"description": "Office Printer", "quantity": qty, "unit_price": price, "confidence": 0.9}],
    })


def make_po(po_number="PO-1001", qty=2, price=100.0):
    return PurchaseOrder(po_number=po_number, vendor_name="Greenfield Supplies", currency="USD",
                         line_items=[{"description": "Office Printer", "quantity": qty, "unit_price": price}])


def make_gr(po_number="PO-1001", qty=2):
    return GoodsReceipt(po_number=po_number, received_date="2026-11-02",
                        line_items=[{"description": "Office Printer", "quantity_received": qty}])


SCENARIOS = {
    # sample set 1: everything agrees
    "matching": (make_invoice(), make_po(), make_gr()),
    # sample set 2: price 120 vs 100, 4 invoiced/ordered vs 3 received
    "mismatch": (make_invoice(number="FC-INV-2001", qty=4, price=120.0, tax=48.0, po_number="PO-2001"),
                 make_po("PO-2001", qty=4, price=100.0), make_gr("PO-2001", qty=3)),
}


class FakeDB:
    """In-memory stand-in for the db / risk functions the pipeline calls."""

    def __init__(self):
        self.invoices = {}   # id -> (user_id, vendor, number)
        self.pos = {}
        self.grs = {}
        self.next_id = 1
        self.deleted = []

    def _id(self):
        self.next_id += 1
        return self.next_id - 1

    def check_duplicate(self, invoice, user_id):
        key = (user_id, invoice["vendor_name"].strip().lower(), invoice["invoice_number"].strip().lower())
        return key in self.invoices.values()

    def check_duplicate_po(self, po, user_id):
        return (user_id, po["po_number"].lower()) in self.pos.values()

    def check_duplicate_gr(self, gr, user_id):
        return (user_id, gr["po_number"].lower(), gr.get("received_date")) in self.grs.values()

    def persist_documents(self, invoice, po, gr, user_id, insert_po, insert_gr):
        inv_id = self._id()
        self.invoices[inv_id] = (user_id, invoice["vendor_name"].strip().lower(), invoice["invoice_number"].strip().lower())
        po_id = gr_id = None
        if insert_po:
            po_id = self._id()
            self.pos[po_id] = (user_id, po["po_number"].lower())
        if insert_gr:
            gr_id = self._id()
            self.grs[gr_id] = (user_id, gr["po_number"].lower(), gr.get("received_date"))
        return {"invoice_id": inv_id, "po_id": po_id, "gr_id": gr_id}

    def delete_documents(self, user_id, invoice_id=None, po_id=None, gr_id=None):
        self.deleted.append((invoice_id, po_id, gr_id))
        self.invoices.pop(invoice_id, None)
        self.pos.pop(po_id, None)
        self.grs.pop(gr_id, None)

    def vendor_history(self, vendor_name, user_id=None, exclude_invoice_id=None):
        count = sum(1 for i, (u, v, _n) in self.invoices.items()
                    if v == vendor_name.strip().lower() and u == user_id and i != exclude_invoice_id)
        return {"is_new_vendor": count == 0, "avg_invoice_amount": None, "invoice_count": count}


@pytest.fixture
def fake_db(monkeypatch):
    from backend.app import agent, db, risk_analysis, report

    fdb = FakeDB()
    for name in ("check_duplicate", "check_duplicate_po", "check_duplicate_gr", "persist_documents", "delete_documents"):
        monkeypatch.setattr(db, name, getattr(fdb, name))
    monkeypatch.setattr(risk_analysis, "get_vendor_history", fdb.vendor_history)
    monkeypatch.setattr(risk_analysis, "get_vendor_decisions", lambda vendor, reviewer_id=None: [])
    monkeypatch.setattr(report, "explanation", lambda ctx: "Test explanation.")
    from backend.app.anomaly_detection import predict
    predict.set_models({})
    return fdb


@pytest.fixture
def use_scenario(monkeypatch):
    """Make the extractors return a named scenario's documents."""
    from backend.app import extracter

    def _apply(name):
        inv, po, gr = SCENARIOS[name]
        monkeypatch.setattr(extracter, "extract_invoice", lambda path: inv)
        monkeypatch.setattr(extracter, "extract_po", lambda path: po)
        monkeypatch.setattr(extracter, "extract_gr", lambda path: gr)
    return _apply


@pytest.fixture
def graph():
    from langgraph.checkpoint.memory import MemorySaver
    from backend.app.agent import create_graph, nodes, paths
    return create_graph(nodes, paths, checkpointer=MemorySaver())
