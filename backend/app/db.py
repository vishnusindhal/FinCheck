"""
PostgreSQL access for invoices, purchase orders and goods receipts.

Connections come from a small thread-safe pool. Callers keep the familiar
pattern `conn = get_connection(); ...; conn.close()` — `close()` on a pooled
connection returns it to the pool instead of closing the socket.
"""

import logging
import os
import threading

import psycopg2
import psycopg2.errors
from psycopg2 import pool as pg_pool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()
POOL_MIN = 1
POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))


class _PooledConnection:
    """Proxy around a pooled psycopg2 connection; close() returns it to the pool."""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._returned = False

    def close(self):
        if self._returned:
            return
        self._returned = True
        try:
            # putconn rolls back any open transaction before reuse.
            self._pool.putconn(self._conn, close=bool(self._conn.closed))
        except Exception:  # pool closed or connection unusable
            try:
                self._conn.close()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pg_pool.ThreadedConnectionPool(POOL_MIN, POOL_MAX, os.getenv("DB_URL"))
    return _pool


def get_connection():
    """Return a DB connection (pooled when possible). Always call .close() when done."""
    try:
        p = _get_pool()
        conn = p.getconn()
        if conn.closed:  # stale connection, e.g. after a DB restart
            p.putconn(conn, close=True)
            conn = p.getconn()
        return _PooledConnection(p, conn)
    except pg_pool.PoolError:
        logger.warning("DB pool exhausted; opening a direct connection")
        return psycopg2.connect(os.getenv("DB_URL"))


def _norm(value) -> str:
    return (value or "").strip().lower()


# ============================================================
# SCHEMA
# ============================================================

def init_db():
    """Create invoice / PO / GR tables (idempotent). Must run before auth_db.init_auth_db()."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            vendor_name TEXT NOT NULL,
            invoice_number TEXT NOT NULL,
            po_number TEXT,
            total_amount NUMERIC,
            tax_amount NUMERIC,
            currency TEXT,
            invoice_date DATE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoice_line_items (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            description TEXT,
            quantity NUMERIC,
            unit_price NUMERIC
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id SERIAL PRIMARY KEY,
            po_number TEXT NOT NULL,
            vendor_name TEXT,
            currency TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS po_line_items (
            id SERIAL PRIMARY KEY,
            po_id INTEGER REFERENCES purchase_orders(id) ON DELETE CASCADE,
            description TEXT,
            quantity NUMERIC,
            unit_price NUMERIC
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS goods_receipts (
            id SERIAL PRIMARY KEY,
            po_number TEXT NOT NULL,
            received_date DATE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gr_line_items (
            id SERIAL PRIMARY KEY,
            gr_id INTEGER REFERENCES goods_receipts(id) ON DELETE CASCADE,
            description TEXT,
            quantity_received NUMERIC
        )
    """)
    # Legacy column additions (older databases) — safe to re-run.
    cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS po_number TEXT")
    cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS tax_amount NUMERIC")
    cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS currency TEXT")

    conn.commit()
    cur.close()
    conn.close()


def migrate_per_user_uniqueness():
    """
    Replace the old GLOBAL unique constraints with PER-USER unique indexes so one
    user's documents never block (or reveal) another user's. Requires the
    user_id columns added by auth_db.init_auth_db(). Idempotent.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_vendor_name_invoice_number_key")
    cur.execute("ALTER TABLE purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_po_number_key")
    cur.execute("ALTER TABLE purchase_orders ALTER COLUMN vendor_name DROP NOT NULL")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS invoices_user_vendor_number_uidx
        ON invoices (user_id, vendor_name, invoice_number)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS purchase_orders_user_po_uidx
        ON purchase_orders (user_id, LOWER(po_number))
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS invoices_user_idx ON invoices (user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS goods_receipts_user_po_idx ON goods_receipts (user_id, LOWER(po_number))")
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# DUPLICATE CHECKS (all scoped to the requesting user)
# ============================================================

def check_duplicate(invoice: dict, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM invoices WHERE vendor_name = %s AND invoice_number = %s AND user_id = %s",
        (_norm(invoice.get("vendor_name")), _norm(invoice.get("invoice_number")), user_id),
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None


def check_duplicate_po(po: dict, user_id: int) -> bool:
    if not po or not po.get("po_number"):
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM purchase_orders WHERE LOWER(po_number) = %s AND user_id = %s",
        (_norm(po.get("po_number")), user_id),
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None


def check_duplicate_gr(gr: dict, user_id: int) -> bool:
    if not gr or not gr.get("po_number"):
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id FROM goods_receipts
           WHERE LOWER(po_number) = %s
             AND received_date IS NOT DISTINCT FROM %s
             AND user_id = %s""",
        (_norm(gr.get("po_number")), gr.get("received_date"), user_id),
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None


# ============================================================
# INSERTS (cursor-level helpers share one transaction)
# ============================================================

def _insert_invoice(cur, invoice: dict, user_id: int) -> int:
    cur.execute(
        """INSERT INTO invoices (vendor_name, invoice_number, po_number, total_amount,
                                 tax_amount, currency, invoice_date, user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            _norm(invoice.get("vendor_name")),
            _norm(invoice.get("invoice_number")),
            invoice.get("po_number"),
            invoice.get("total_amount"),
            invoice.get("tax_amount"),
            invoice.get("currency"),
            invoice.get("invoice_date"),
            user_id,
        ),
    )
    invoice_id = cur.fetchone()[0]
    for item in invoice.get("line_items") or []:
        cur.execute(
            """INSERT INTO invoice_line_items (invoice_id, description, quantity, unit_price)
               VALUES (%s, %s, %s, %s)""",
            (invoice_id, item.get("description"), item.get("quantity"), item.get("unit_price")),
        )
    return invoice_id


def _insert_po(cur, po: dict, user_id: int) -> int:
    cur.execute(
        """INSERT INTO purchase_orders (po_number, vendor_name, currency, user_id)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (po.get("po_number").strip(), po.get("vendor_name"), po.get("currency"), user_id),
    )
    po_id = cur.fetchone()[0]
    for item in po.get("line_items") or []:
        cur.execute(
            """INSERT INTO po_line_items (po_id, description, quantity, unit_price)
               VALUES (%s, %s, %s, %s)""",
            (po_id, item.get("description"), item.get("quantity"), item.get("unit_price")),
        )
    return po_id


def _insert_gr(cur, gr: dict, user_id: int) -> int:
    cur.execute(
        """INSERT INTO goods_receipts (po_number, received_date, user_id)
           VALUES (%s, %s, %s) RETURNING id""",
        (gr.get("po_number").strip(), gr.get("received_date"), user_id),
    )
    gr_id = cur.fetchone()[0]
    for item in gr.get("line_items") or []:
        cur.execute(
            """INSERT INTO gr_line_items (gr_id, description, quantity_received)
               VALUES (%s, %s, %s)""",
            (gr_id, item.get("description"), item.get("quantity_received")),
        )
    return gr_id


class DuplicateInvoiceError(Exception):
    """Raised when a concurrent request inserted the same invoice first."""


def persist_documents(invoice: dict, po: dict | None, gr: dict | None, user_id: int,
                      insert_po: bool, insert_gr: bool) -> dict:
    """
    Insert the invoice (+ PO/GR when requested) in ONE transaction.
    Returns {"invoice_id", "po_id", "gr_id"}. Raises DuplicateInvoiceError on a
    unique-index race.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        invoice_id = _insert_invoice(cur, invoice, user_id)
        po_id = _insert_po(cur, po, user_id) if insert_po else None
        gr_id = _insert_gr(cur, gr, user_id) if insert_gr else None
        conn.commit()
        return {"invoice_id": invoice_id, "po_id": po_id, "gr_id": gr_id}
    except psycopg2.errors.UniqueViolation as e:
        conn.rollback()
        raise DuplicateInvoiceError(str(e)) from e
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def delete_documents(user_id: int, invoice_id=None, po_id=None, gr_id=None):
    """Remove rows a failed run inserted (line items cascade)."""
    if not any([invoice_id, po_id, gr_id]):
        return
    conn = get_connection()
    cur = conn.cursor()
    try:
        if invoice_id:
            cur.execute("DELETE FROM invoices WHERE id = %s AND user_id = %s", (invoice_id, user_id))
        if po_id:
            cur.execute("DELETE FROM purchase_orders WHERE id = %s AND user_id = %s", (po_id, user_id))
        if gr_id:
            cur.execute("DELETE FROM goods_receipts WHERE id = %s AND user_id = %s", (gr_id, user_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


# Backwards-compatible single-document inserts (own transaction each).
def insert_invoice(invoice: dict, user_id: int) -> int:
    return persist_documents(invoice, None, None, user_id, False, False)["invoice_id"]


def insert_po(po: dict, user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    try:
        po_id = _insert_po(cur, po, user_id)
        conn.commit()
        return po_id
    finally:
        cur.close()
        conn.close()


def insert_gr(gr: dict, user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    try:
        gr_id = _insert_gr(cur, gr, user_id)
        conn.commit()
        return gr_id
    finally:
        cur.close()
        conn.close()


# ============================================================
# READS (user-scoped)
# ============================================================

def _rows_to_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def list_invoices(user_id: int, limit: int = 50) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT id, invoice_number, vendor_name, invoice_date,
                      total_amount, tax_amount, currency, created_at
               FROM invoices WHERE user_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (user_id, limit),
        )
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def get_invoice(user_id: int, invoice_id: int) -> dict | None:
    """Invoice + line items + the most recent run that processed it (run_id may be None)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM invoices WHERE id = %s AND user_id = %s", (invoice_id, user_id))
        rows = _rows_to_dicts(cur)
        if not rows:
            return None
        invoice = rows[0]
        cur.execute(
            "SELECT description, quantity, unit_price FROM invoice_line_items WHERE invoice_id = %s ORDER BY id",
            (invoice_id,),
        )
        invoice["line_items"] = _rows_to_dicts(cur)
        cur.execute(
            """SELECT id FROM pipeline_runs WHERE invoice_id = %s AND user_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (invoice_id, user_id),
        )
        run = cur.fetchone()
        invoice["run_id"] = run[0] if run else None
        return invoice
    finally:
        cur.close()
        conn.close()


def get_purchase_order(user_id: int, po_number: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT * FROM purchase_orders WHERE LOWER(po_number) = %s AND user_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (_norm(po_number), user_id),
        )
        rows = _rows_to_dicts(cur)
        if not rows:
            return None
        po = rows[0]
        cur.execute(
            "SELECT description, quantity, unit_price FROM po_line_items WHERE po_id = %s ORDER BY id",
            (po["id"],),
        )
        po["line_items"] = _rows_to_dicts(cur)
        return po
    finally:
        cur.close()
        conn.close()


def get_goods_receipt(user_id: int, po_number: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT * FROM goods_receipts WHERE LOWER(po_number) = %s AND user_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (_norm(po_number), user_id),
        )
        rows = _rows_to_dicts(cur)
        if not rows:
            return None
        gr = rows[0]
        cur.execute(
            "SELECT description, quantity_received AS quantity FROM gr_line_items WHERE gr_id = %s ORDER BY id",
            (gr["id"],),
        )
        gr["line_items"] = _rows_to_dicts(cur)
        return gr
    finally:
        cur.close()
        conn.close()
