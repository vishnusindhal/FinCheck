"""
Stores reviewer decisions for vendor-level risk adjustment.
Each row is one human decision on one invoice run — over time,
this table becomes the basis for adaptive risk scoring per vendor.
"""

import json

from backend.app.db import get_connection


def create_reviewer_decisions_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviewer_decisions (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER,
            reviewer_id INTEGER REFERENCES users(id),
            vendor_name TEXT,
            decision TEXT NOT NULL,
            risk_score_at_decision INTEGER,
            risk_factors JSONB,
            reviewer_note TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS reviewer_decisions_vendor_idx
        ON reviewer_decisions (reviewer_id, vendor_name)
    """)
    conn.commit()
    cur.close()
    conn.close()


def insert_reviewer_decision(
    invoice_id: int | None,
    reviewer_id: int,
    vendor_name: str | None,
    decision: str,
    risk_score_at_decision: int | None,
    risk_factors: list,
    reviewer_note: str = "",
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO reviewer_decisions
           (invoice_id, reviewer_id, vendor_name, decision, risk_score_at_decision, risk_factors, reviewer_note)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            invoice_id,
            reviewer_id,
            (vendor_name or "").strip().lower() or None,
            decision,
            risk_score_at_decision,
            json.dumps(risk_factors or []),
            reviewer_note,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_vendor_decisions(vendor_name: str, reviewer_id: int | None = None) -> list[dict]:
    """
    Past reviewer decisions for a vendor, scoped to one user when reviewer_id is
    given (so one user's reviews never influence another user's risk scores).
    """
    conn = get_connection()
    cur = conn.cursor()
    sql = """SELECT decision, risk_score_at_decision, risk_factors, created_at
             FROM reviewer_decisions WHERE vendor_name = %s"""
    params = [(vendor_name or "").strip().lower()]
    if reviewer_id is not None:
        sql += " AND reviewer_id = %s"
        params.append(reviewer_id)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "decision": r[0],
            "risk_score_at_decision": r[1],
            "risk_factors": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]
