"""
LangGraph invoice pipeline.

Nodes return ONLY the state keys they change (deltas). Nothing heavy happens at
import time: anomaly models are loaded/trained by main.py's lifespan via
backend.app.anomaly_detection.train.retrain_from_db / predict.set_models.
"""

import logging
from typing import TypedDict, Optional, List, Dict, Annotated

from langgraph.graph import StateGraph, END, START
from langgraph.types import Send, interrupt

from backend.app import extracter
from backend.app.validator import validate_invoice
from backend.app import db
from backend.app.matching import match_invoice
from backend.app.schemas import MatchResult
from backend.app.classify import classify_invoice
from backend.app.risk_analysis import assess_risk
from backend.app.approval import route_approval
from backend.app.report import generate_report
from backend.app.helper import (
    extract_confidences, unwrap_confident_fields, normalize_invoice, normalize_goods_receipt,
)
from backend.app.anomaly_detection.predict import detect_anomaly

logger = logging.getLogger(__name__)

EXTRACTION_NODES = ["extract_Invoice", "extract_PurchaseOrder", "extract_GoodReceipt"]


def merge_optional(a, b):
    """Keep whichever value is not None (lets parallel extraction branches merge)."""
    return b if b is not None else a


class PipelineState(TypedDict, total=False):
    invoice_path: str
    po_path: Optional[str]
    gr_path: Optional[str]
    user_id: Optional[int]
    invoice: Annotated[Optional[dict], merge_optional]
    po: Annotated[Optional[dict], merge_optional]
    gr: Annotated[Optional[dict], merge_optional]
    invoice_confidences: Annotated[Optional[dict], merge_optional]
    invoice_id: Optional[int]        # invoices.id inserted by duplicate_detect
    po_db_id: Optional[int]          # purchase_orders.id inserted by THIS run (None if pre-existing/absent)
    gr_db_id: Optional[int]          # goods_receipts.id inserted by THIS run
    is_valid: Optional[bool]
    validation_errors: Optional[list]
    is_duplicate: Optional[bool]
    match_result: Optional[dict]
    classification: Optional[dict]
    anomaly_result: Optional[dict]
    risk: Optional[dict]
    approval: Optional[dict]
    report: Optional[dict]
    status: Optional[str]            # set to rejected_* to short-circuit
    warnings: List[Dict]


# ============================================================
# EXTRACTION (parallel fan-out)
# ============================================================

def extract_Invoice(state: PipelineState) -> dict:
    invoice = extracter.extract_invoice(state["invoice_path"])
    if invoice is None:
        return {"invoice": None, "invoice_confidences": {}}
    raw = invoice.model_dump()
    return {
        "invoice": normalize_invoice(unwrap_confident_fields(raw)),
        "invoice_confidences": extract_confidences(raw),
    }


def extract_PurchaseOrder(state: PipelineState) -> dict:
    if not state.get("po_path"):
        return {"po": None}
    po = extracter.extract_po(state["po_path"])
    return {"po": po.model_dump() if po else None}


def extract_GoodReceipt(state: PipelineState) -> dict:
    if not state.get("gr_path"):
        return {"gr": None}
    gr = extracter.extract_gr(state["gr_path"])
    return {"gr": normalize_goods_receipt(gr.model_dump()) if gr else None}


def dispatch_extraction(state: PipelineState) -> list:
    """Fan out to parallel extraction nodes (only for documents that were uploaded)."""
    tasks = [Send("extract_Invoice", state)]
    if state.get("po_path"):
        tasks.append(Send("extract_PurchaseOrder", state))
    if state.get("gr_path"):
        tasks.append(Send("extract_GoodReceipt", state))
    return tasks


# ============================================================
# CHECKS
# ============================================================

def validation_node(state: PipelineState) -> dict:
    is_valid, errors = validate_invoice(state.get("invoice"))
    update = {"is_valid": is_valid, "validation_errors": errors}
    if not is_valid:
        update["status"] = "rejected_invalid"
    return update


def duplicate_node(state: PipelineState) -> dict:
    user_id = state.get("user_id")
    invoice = state["invoice"]

    if db.check_duplicate(invoice, user_id):
        return {"is_duplicate": True, "status": "rejected_duplicate"}

    warnings = []
    po, gr = state.get("po"), state.get("gr")
    insert_po = insert_gr = False

    if po is not None:
        if not po.get("po_number"):
            warnings.append({"PurchaseOrderNumberMissing": "purchase order has no PO number; it was not saved"})
        elif db.check_duplicate_po(po, user_id):
            warnings.append({"DuplicatePurchaseOrder": "purchase order with same number already exists"})
        else:
            insert_po = True

    if gr is not None:
        if not gr.get("po_number"):
            warnings.append({"GoodsReceiptPONumberMissing": "goods receipt has no PO number; it was not saved"})
        elif db.check_duplicate_gr(gr, user_id):
            warnings.append({"DuplicateGoodsReceipt": "goods receipt for this PO and date already exists"})
        else:
            insert_gr = True

    try:
        ids = db.persist_documents(invoice, po, gr, user_id, insert_po, insert_gr)
    except db.DuplicateInvoiceError:
        # A concurrent request saved the same invoice first.
        return {"is_duplicate": True, "status": "rejected_duplicate"}

    return {
        "is_duplicate": False,
        "warnings": warnings,
        "invoice_id": ids["invoice_id"],
        "po_db_id": ids["po_id"],
        "gr_db_id": ids["gr_id"],
    }


def matching_node(state: PipelineState) -> dict:
    if not state.get("po") or not state.get("gr"):
        return {"match_result": {"matched": False, "issues": [
            {"field": "po/gr", "expected": "present", "actual": "missing", "severity": "warning"}
        ]}}
    return {"match_result": match_invoice(state["invoice"], state["po"], state["gr"]).model_dump()}


def classification_node(state: PipelineState) -> dict:
    return {"classification": classify_invoice(state["invoice"])}


def anomaly_node(state: PipelineState) -> dict:
    if not state.get("invoice"):
        return {"anomaly_result": None}
    try:
        result = detect_anomaly(
            models=None,  # use the shared registry
            invoice=state["invoice"],
            user_id=state.get("user_id"),
            exclude_invoice_id=state.get("invoice_id"),
        )
    except Exception as exc:  # anomaly detection is advisory; never fail the run on it
        logger.warning("Anomaly detection failed: %s", exc)
        result = {"is_anomaly": False, "anomaly_score": 0.0, "model_used": "error",
                  "logs": [f"Anomaly detection failed: {exc}"]}
    return {"anomaly_result": result}


def risk_node(state: PipelineState) -> dict:
    risk = assess_risk(
        state["invoice"],
        MatchResult(**state["match_result"]),
        state.get("invoice_confidences") or {},
        state.get("anomaly_result") or {},
        user_id=state.get("user_id"),
        invoice_id=state.get("invoice_id"),
    )
    return {"risk": risk}


def approval_node(state: PipelineState) -> dict:
    # NOTE: on resume LangGraph re-runs this node from the top, so everything
    # before interrupt() must stay side-effect-free.
    approval = route_approval(state["invoice"], state.get("risk") or {}, MatchResult(**state["match_result"]))
    approval["source"] = "automated"

    if approval["decision"] != "needs_review":
        return {"approval": approval}

    human_input = interrupt({
        "message": "Flagged by FinCheck — pending human review",
        "approval": approval,
    })
    decision = human_input.get("decision") if isinstance(human_input, dict) else human_input
    note = human_input.get("note", "") if isinstance(human_input, dict) else ""
    return {
        "approval": {
            "decision": decision,
            "approver": "human_reviewer",
            "routed_to": approval.get("approver"),
            "note": note,
            "source": "human",
        }
    }


def report_node(state: PipelineState) -> dict:
    report = generate_report(
        invoice=state["invoice"],
        validation=(state.get("is_valid"), state.get("validation_errors")),
        match_result=MatchResult(**state["match_result"]),
        classification=state.get("classification"),
        risk=state.get("risk") or {},
        approval=state.get("approval") or {},
        warnings=state.get("warnings") or [],
        anomaly=state.get("anomaly_result"),
    )
    return {"report": report, "status": state.get("status") or "processed"}


# Conditional routing: stop early if invalid or duplicate
def route_after_validation(state: PipelineState) -> str:
    return "duplicate_detect" if state.get("is_valid") else END


def route_after_duplicate(state: PipelineState) -> str:
    return END if state.get("is_duplicate") else "3_way_matching"


nodes = [
    ("extract_Invoice", extract_Invoice),
    ("extract_PurchaseOrder", extract_PurchaseOrder),
    ("extract_GoodReceipt", extract_GoodReceipt),
    ("validation", validation_node),
    ("duplicate_detect", duplicate_node),
    ("3_way_matching", matching_node),
    ("classify", classification_node),
    ("anomaly_detect", anomaly_node),
    ("risk_analysis", risk_node),
    ("approval", approval_node),
    ("report_gen", report_node),
]

paths = [
    (START, dispatch_extraction, "fan_out"),
    ("extract_Invoice", "validation"),
    ("extract_PurchaseOrder", "validation"),
    ("extract_GoodReceipt", "validation"),
    ("validation", route_after_validation, "conditional_routing"),
    ("duplicate_detect", route_after_duplicate, "conditional_routing"),
    ("3_way_matching", "classify"),
    ("classify", "anomaly_detect"),
    ("anomaly_detect", "risk_analysis"),
    ("risk_analysis", "approval"),
    ("approval", "report_gen"),
    ("report_gen", END),
]


def create_graph(nodes, paths, checkpointer=None):
    graph = StateGraph(PipelineState)
    for name, fn in nodes:
        graph.add_node(name, fn)

    for path in paths:
        if len(path) == 2:
            graph.add_edge(*path)
            continue
        strt, route_fn, label = path
        if label == "fan_out":
            graph.add_conditional_edges(strt, route_fn, EXTRACTION_NODES)
        else:
            graph.add_conditional_edges(strt, route_fn)

    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    samples = "output/pdf/fincheck-samples"
    pipeline = create_graph(nodes, paths)
    result = pipeline.invoke({
        "invoice_path": f"{samples}/01-matching-invoice.pdf",
        "po_path": f"{samples}/01-matching-purchase-order.pdf",
        "gr_path": f"{samples}/01-matching-goods-receipt.pdf",
        "user_id": None,
    })
    print(result.get("report") or f"Stopped early — status: {result.get('status')}")
