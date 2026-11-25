"""Gemini-based structured extraction for invoices, purchase orders and goods receipts."""

import base64
import logging
import os
import time
from functools import lru_cache

from dotenv import load_dotenv

from backend.app.schemas import Invoice, PurchaseOrder, GoodsReceipt
from backend.app.system_prompt import INVOICE_EXTRACTION_PROMPT, PO_EXTRACTION_PROMPT, GR_EXTRACTION_PROMPT

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


@lru_cache(maxsize=1)
def get_llm():
    """Create the Gemini chat client lazily (no network/config work at import time)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_NAME", DEFAULT_MODEL),
        api_key=os.getenv("API_KEY", ""),
    )


@lru_cache(maxsize=None)
def _structured(schema):
    return get_llm().with_structured_output(schema=schema)


def _is_transient(exc: Exception) -> bool:
    """Overload / rate-limit / unavailable errors are worth retrying; auth or bad-model errors are not."""
    try:
        from google.genai.errors import ServerError
        if isinstance(exc, ServerError):
            return True
    except ImportError:  # pragma: no cover
        pass
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(s in text for s in ("resourceexhausted", "resource_exhausted", "unavailable", "overloaded", "429", "503"))


def extract_document(file_path: str, prompt: str, schema, max_retries: int = 3):
    """Generic extractor — works for Invoice, PurchaseOrder, or GoodsReceipt."""
    with open(file_path, "rb") as f:
        pdf_data = base64.b64encode(f.read()).decode()

    message = [
        {
            "role": "user",
            "content": [
                {"type": "media", "data": pdf_data, "mime_type": "application/pdf"},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    for attempt in range(1, max_retries + 1):
        try:
            return _structured(schema).invoke(message)
        except Exception as exc:
            if attempt == max_retries or not _is_transient(exc):
                raise
            wait = 2 ** attempt  # 2s, 4s
            logger.warning("Gemini transient error (attempt %d/%d): %s. Retrying in %ds", attempt, max_retries, exc, wait)
            time.sleep(wait)


def extract_invoice(file_path: str) -> Invoice:
    return extract_document(file_path, INVOICE_EXTRACTION_PROMPT, Invoice)


def extract_po(file_path: str) -> PurchaseOrder:
    return extract_document(file_path, PO_EXTRACTION_PROMPT, PurchaseOrder)


def extract_gr(file_path: str) -> GoodsReceipt:
    return extract_document(file_path, GR_EXTRACTION_PROMPT, GoodsReceipt)


def extract(invoice_=None, po_=None, gr_=None):
    """Convenience: extract whichever documents are given (None for missing ones)."""
    invoice = extract_invoice(invoice_) if invoice_ else None
    po = extract_po(po_) if po_ else None
    gr = extract_gr(gr_) if gr_ else None
    return invoice, po, gr


if __name__ == "__main__":
    from backend.app.helper import unwrap_confident_fields, normalize_invoice
    from backend.app.matching import match_invoice

    samples = "output/pdf/fincheck-samples"
    inv, po, gr = extract(
        invoice_=f"{samples}/02-mismatch-invoice.pdf",
        po_=f"{samples}/02-mismatch-purchase-order.pdf",
        gr_=f"{samples}/02-mismatch-goods-receipt.pdf",
    )
    print(match_invoice(normalize_invoice(unwrap_confident_fields(inv.model_dump())), po.model_dump(), gr.model_dump()))
