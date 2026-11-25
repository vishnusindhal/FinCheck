from datetime import datetime

from backend.app.helper import process_context
from backend.app.schemas import MatchResult
from backend.app.anomaly_exp import explanation

STOP_REASONS = {
    "rejected_invalid": "The invoice failed validation, so processing stopped.",
    "rejected_duplicate": "This invoice was already processed (same vendor and invoice number), so processing stopped.",
}


def generate_report(invoice: dict, validation: tuple, match_result: MatchResult, classification: dict,
                    risk: dict, approval: dict, warnings, anomaly: dict | None = None,
                    include_explanation: bool = True) -> dict:
    is_valid, validation_errors = validation
    report = {
        "invoice_number": invoice.get("invoice_number"),
        "vendor_name": invoice.get("vendor_name"),
        "total_amount": invoice.get("total_amount"),
        "currency": invoice.get("currency"),
        "outcome": "completed",
        "stages": {
            "validation": {"passed": is_valid, "errors": validation_errors or []},
            "matching": {"matched": match_result.matched, "issues": [i.model_dump() for i in match_result.issues]},
            "classification": classification,
            "anomaly": anomaly,
            "risk": risk,
            "approval": approval,
            "warnings": warnings or [],
        },
        "generated_at": datetime.now().isoformat(),
        "explanation": None,
    }

    if include_explanation and (risk or {}).get("score", 0) > 0:
        report["explanation"] = explanation(process_context(report))

    return report


def generate_stopped_report(invoice: dict | None, status: str, validation_errors: list | None) -> dict:
    """Report for runs that ended early (invalid / duplicate) so the UI and history can show why."""
    invoice = invoice or {}
    return {
        "invoice_number": invoice.get("invoice_number"),
        "vendor_name": invoice.get("vendor_name"),
        "total_amount": invoice.get("total_amount"),
        "currency": invoice.get("currency"),
        "outcome": status,
        "stages": {
            "validation": {"passed": status != "rejected_invalid", "errors": validation_errors or []},
        },
        "generated_at": datetime.now().isoformat(),
        "explanation": STOP_REASONS.get(status),
    }
