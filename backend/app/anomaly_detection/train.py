"""Train per-vendor + global IsolationForest models and save them under MODELS_DIR."""

import logging
import os
import threading
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.anomaly_detection.data_handling import build_features, FEATURES

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = os.getenv("MODELS_DIR", str(PROJECT_ROOT / "models"))
MIN_SAMPLES = 5   # fewer invoices than this makes a meaningless model


def train_pipeline(X: pd.DataFrame) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model", IsolationForest(
            n_estimators=200,
            contamination=0.05,   # expect ~5% of invoices to be anomalous
            random_state=42,
        )),
    ])
    pipe.fit(X)
    return pipe


def model_key(user_id, vendor_name: str, currency: str) -> str:
    """Consistent key used for both saving and loading models."""
    safe_vendor = (vendor_name or "").strip().lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
    return f"{user_id}__{safe_vendor}__{(currency or 'usd').lower()}"


def train_all(df: pd.DataFrame, models_dir: str = MODELS_DIR) -> dict:
    """
    Train one IsolationForest per (user_id, vendor_name, currency) group with
    enough history, plus one global fallback model. Returns {model_key: pipeline}.
    """
    os.makedirs(models_dir, exist_ok=True)
    df = build_features(df)
    models = {}

    for (user_id, vendor, currency), group in df.groupby(["user_id", "vendor_name", "currency"]):
        if len(group) < MIN_SAMPLES:
            continue
        key = model_key(user_id, vendor, currency)
        models[key] = train_pipeline(group[FEATURES].fillna(0))
        joblib.dump(models[key], os.path.join(models_dir, f"{key}.pkl"))

    X_global = df[FEATURES].fillna(0)
    if len(X_global) >= MIN_SAMPLES:
        models["global"] = train_pipeline(X_global)
        joblib.dump(models["global"], os.path.join(models_dir, "global.pkl"))

    vendor_count = len(models) - (1 if "global" in models else 0)
    logger.info("Trained %d vendor models%s.", vendor_count, " + 1 global fallback" if "global" in models else "")
    return models


_retrain_lock = threading.Lock()


def retrain_from_db() -> dict | None:
    """Train from all stored invoices and publish the models. Skips if a retrain is already running."""
    from backend.app.anomaly_detection.data_handling import get_invoice_sample
    from backend.app.anomaly_detection.predict import set_models

    if not _retrain_lock.acquire(blocking=False):
        return None
    try:
        df = get_invoice_sample()
        if len(df) < MIN_SAMPLES:
            logger.info("Not enough invoice data to train anomaly models yet (%d rows).", len(df))
            return None
        models = train_all(df)
        set_models(models)
        return models
    except Exception as exc:
        logger.warning("Anomaly model training skipped: %s", exc)
        return None
    finally:
        _retrain_lock.release()


def retrain_in_background():
    threading.Thread(target=retrain_from_db, name="anomaly-retrain", daemon=True).start()
