import warnings

import numpy as np
import pandas as pd

from backend.app.db import get_connection

FEATURES = [
    "invoice_total",
    "tax_percent",
    "line_item_count",
    "avg_unit_price",
    "vendor_avg_invoice_total",
    "vendor_std_invoice_total",
    "vendor_avg_line_items",
    "vendor_invoice_frequency",
    "days_since_last_vendor_invoice",
    "invoice_total_ratio",       # most important — relative deviation
    "line_item_count_ratio",     # most important — relative deviation
]

_INVOICE_COLUMNS = "id, user_id, vendor_name, invoice_number, invoice_date, total_amount, tax_amount, currency"


def _read_sql(sql: str, params=None) -> pd.DataFrame:
    conn = get_connection()
    try:
        with warnings.catch_warnings():
            # pandas warns for non-SQLAlchemy DBAPI connections; psycopg2 works fine here.
            warnings.simplefilter("ignore", UserWarning)
            return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def _attach_line_items(invoices: pd.DataFrame) -> pd.DataFrame:
    if invoices.empty:
        return invoices.assign(line_items=[])
    ids = [int(i) for i in invoices["id"].tolist()]
    line_items = _read_sql(
        "SELECT invoice_id, description, quantity, unit_price FROM invoice_line_items WHERE invoice_id = ANY(%s)",
        (ids,),
    )
    grouped = {
        inv_id: grp[["description", "quantity", "unit_price"]].to_dict("records")
        for inv_id, grp in line_items.groupby("invoice_id")
    } if not line_items.empty else {}
    invoices = invoices.copy()
    invoices["line_items"] = invoices["id"].map(lambda i: grouped.get(i, []))
    for col in ("total_amount", "tax_amount"):
        invoices[col] = pd.to_numeric(invoices[col], errors="coerce")
    return invoices


def get_invoice_sample() -> pd.DataFrame:
    """All owned invoices + line items as a flat DataFrame ready for build_features()."""
    invoices = _read_sql(f"""
        SELECT {_INVOICE_COLUMNS} FROM invoices
        WHERE user_id IS NOT NULL AND total_amount IS NOT NULL AND vendor_name IS NOT NULL
    """)
    return _attach_line_items(invoices)


def get_vendor_invoices(user_id, vendor_name: str, exclude_invoice_id=None) -> pd.DataFrame:
    """This user's past invoices for one vendor (used to build inference features)."""
    sql = f"""SELECT {_INVOICE_COLUMNS} FROM invoices
              WHERE user_id = %s AND vendor_name = %s AND total_amount IS NOT NULL"""
    params = [user_id, (vendor_name or "").strip().lower()]
    if exclude_invoice_id is not None:
        sql += " AND id <> %s"
        params.append(exclude_invoice_id)
    return _attach_line_items(_read_sql(sql, params))


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce")
    df["tax_amount"] = pd.to_numeric(df["tax_amount"], errors="coerce").fillna(0)
    df["invoice_total"] = df["total_amount"].fillna(0)

    # Tax as a percentage of pre-tax subtotal
    subtotal = df["total_amount"] - df["tax_amount"]
    df["tax_percent"] = (df["tax_amount"] / subtotal.replace(0, np.nan)).fillna(0)

    df["line_item_count"] = df["line_items"].apply(lambda items: len(items) if isinstance(items, list) else 0)
    df["avg_unit_price"] = df["line_items"].apply(
        lambda items: float(np.mean([float(x.get("unit_price") or 0) for x in items]))
        if isinstance(items, list) and len(items) > 0 else 0.0
    )

    # Vendor-level historical statistics (per user + vendor pair)
    vendor_stats = (
        df.groupby(["user_id", "vendor_name"], dropna=False)
          .agg(
              vendor_avg_invoice_total=("invoice_total", "mean"),
              vendor_std_invoice_total=("invoice_total", "std"),
              vendor_avg_line_items=("line_item_count", "mean"),
              vendor_invoice_frequency=("invoice_total", "count"),
          )
          .reset_index()
    )
    df = df.merge(vendor_stats, on=["user_id", "vendor_name"], how="left")
    df["vendor_std_invoice_total"] = df["vendor_std_invoice_total"].fillna(0)

    # Days since previous invoice from same vendor — capped at 365; 180 = neutral for first invoice
    df = df.sort_values(["user_id", "vendor_name", "invoice_date"])
    df["days_since_last_vendor_invoice"] = (
        df.groupby(["user_id", "vendor_name"], dropna=False)["invoice_date"]
          .diff()
          .dt.days
          .clip(upper=365)
          .fillna(180)
    )

    # Relative features — deviation from the vendor norm
    df["invoice_total_ratio"] = (
        df["invoice_total"] / df["vendor_avg_invoice_total"].replace(0, np.nan)
    ).fillna(1.0)
    df["line_item_count_ratio"] = (
        df["line_item_count"] / df["vendor_avg_line_items"].replace(0, np.nan)
    ).fillna(1.0)

    return df
