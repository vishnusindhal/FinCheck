import logging
import os
import threading

import joblib
import pandas as pd

from backend.app.anomaly_detection.data_handling import build_features, get_vendor_invoices, FEATURES
from backend.app.anomaly_detection.train import MODELS_DIR, model_key

logger = logging.getLogger(__name__)

_models: dict = {}
_models_lock = threading.Lock()


def load_models(models_dir: str = MODELS_DIR) -> dict:
    """Load all .pkl model files from disk into a dict keyed by model name."""
    models = {}
    if not os.path.isdir(models_dir):
        return models
    for filename in os.listdir(models_dir):
        if filename.endswith(".pkl"):
            models[filename[:-4]] = joblib.load(os.path.join(models_dir, filename))
    return models


def set_models(models: dict):
    global _models
    with _models_lock:
        _models = dict(models)


def get_models() -> dict:
    with _models_lock:
        return _models


def _feature_row(invoice: dict, user_id, history: pd.DataFrame | None) -> pd.DataFrame:
    """
    Build the feature row for the current invoice IN CONTEXT of the vendor's
    history, mirroring how training computes vendor aggregates.
    """
    current = pd.DataFrame([{
        "id": -1,
        "user_id": user_id,
        "vendor_name": (invoice.get("vendor_name") or "").strip().lower(),
        "currency": invoice.get("currency") or "USD",
        "total_amount": invoice.get("total_amount") or 0,
        "tax_amount": invoice.get("tax_amount") or 0,
        "invoice_date": invoice.get("invoice_date"),
        "line_items": invoice.get("line_items") or [],
    }])
    frame = current if history is None or history.empty else pd.concat([history, current], ignore_index=True)
    features = build_features(frame)
    return features[features["id"] == -1]


def detect_anomaly(models: dict | None, invoice: dict, user_id: int, exclude_invoice_id: int | None = None) -> dict:
    models = get_models() if models is None else models
    vendor = invoice.get("vendor_name") or ""
    currency = invoice.get("currency") or "USD"
    key = model_key(user_id, vendor, currency)
    logs = []

    if key in models:
        model, model_used = models[key], key
        logs.append(f"Vendor model found for '{vendor}' ({currency}).")
    elif "global" in models:
        model, model_used = models["global"], "global"
        logs.append(f"No vendor model for '{vendor}' — not enough historical data.")
        logs.append("Falling back to global model. Prediction may be less accurate.")
    else:
        logs.append("No models available. Anomaly detection skipped.")
        return {"is_anomaly": False, "anomaly_score": 0.0, "model_used": "none", "logs": logs}

    try:
        history = get_vendor_invoices(user_id, vendor, exclude_invoice_id)
    except Exception as exc:
        logger.warning("Could not load vendor history for anomaly features: %s", exc)
        history = None
        logs.append("Vendor history unavailable; using invoice-only features.")

    X = _feature_row(invoice, user_id, history)[FEATURES].fillna(0)
    prediction = model.predict(X)[0]
    score = model.score_samples(X)[0]
    is_anomaly = prediction == -1

    logs.append(f"Anomaly score: {score:.4f} (lower = more anomalous).")
    logs.append(f"⚠ Flagged as anomalous by {model_used} model." if is_anomaly
                else "✓ Invoice appears normal based on vendor history.")

    return {
        "is_anomaly": bool(is_anomaly),
        "anomaly_score": round(float(score), 4),
        "model_used": model_used,
        "logs": logs,
    }
