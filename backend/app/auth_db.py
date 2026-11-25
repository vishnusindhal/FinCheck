"""
Schema + queries for users, per-user pipeline run history and reviewer decisions.

init_auth_db() must run AFTER db.init_db() (it adds user_id columns to the
invoice/PO/GR tables). Both run automatically at app startup unless
AUTO_INIT_DB=false — see main.py lifespan.
"""

import json
from datetime import datetime, timezone

from backend.app.db import get_connection
from backend.app.dbs.risk_db import insert_reviewer_decision, create_reviewer_decisions_table

VALID_DECISIONS = {"approved", "rejected"}
PENDING_STATUS = "pending_review"
RESUMING_STATUS = "resuming"


def init_auth_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # One row per pipeline execution — the user's "session history".
    # report is JSONB since it's read as a whole object, not queried field-by-field.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            report JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Ownership columns on document tables (nullable: legacy rows have no owner).
    cur.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
    cur.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
    cur.execute("ALTER TABLE goods_receipts ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
    cur.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS human_decision TEXT")
    cur.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS decided_by INTEGER REFERENCES users(id)")
    cur.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP")
    cur.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS reviewer_note TEXT")
    cur.execute("ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS thread_id TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS pipeline_runs_user_idx ON pipeline_runs (user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS pipeline_runs_invoice_idx ON pipeline_runs (invoice_id)")
    conn.commit()
    cur.close()
    conn.close()
    # The helper uses a separate connection, so users must be committed first.
    create_reviewer_decisions_table()


# ============================================================
# USERS
# ============================================================

def create_user(email: str, password_hash: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
        (email.strip().lower(), password_hash),
    )
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return user_id


def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, password_hash FROM users WHERE email = %s", (email.strip().lower(),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "password_hash": row[2]}


# ============================================================
# PIPELINE RUNS
# ============================================================

def insert_pipeline_run(user_id: int, invoice_id: int | None, status: str,
                        report: dict | None, thread_id: str | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO pipeline_runs (user_id, invoice_id, status, report, thread_id)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (user_id, invoice_id, status, json.dumps(report) if report else None, thread_id),
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return run_id


_RUN_COLUMNS = "id, invoice_id, status, report, human_decision, decided_at, created_at, reviewer_note"


def _run_row_to_dict(r) -> dict:
    return {
        "id": r[0],
        "invoice_id": r[1],
        "status": r[2],
        "report": r[3],
        "human_decision": r[4],
        "decided_at": r[5].isoformat() if r[5] else None,
        "created_at": r[6].isoformat() if r[6] else None,
        "reviewer_note": r[7],
        "can_resume": r[2] == PENDING_STATUS,
    }


def list_pipeline_runs(user_id: int, limit: int = 50) -> list[dict]:
    """Returns this user's run history only — never another user's data."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"""SELECT {_RUN_COLUMNS} FROM pipeline_runs
            WHERE user_id = %s ORDER BY created_at DESC LIMIT %s""",
        (user_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_run_row_to_dict(r) for r in rows]


def get_pipeline_run(user_id: int, run_id: int) -> dict | None:
    """Fetches one run, scoped to the requesting user — None if it belongs to someone else."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT {_RUN_COLUMNS} FROM pipeline_runs WHERE id = %s AND user_id = %s",
        (run_id, user_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _run_row_to_dict(row) if row else None


def claim_run_for_resume(user_id: int, run_id: int) -> str | None:
    """
    Atomically move an owned run from pending_review → resuming and return its
    thread_id. Returns None if the run doesn't exist, isn't owned by the user,
    or isn't pending (prevents double resumes and cross-user resumes).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE pipeline_runs SET status = %s
           WHERE id = %s AND user_id = %s AND status = %s AND thread_id IS NOT NULL
           RETURNING thread_id""",
        (RESUMING_STATUS, run_id, user_id, PENDING_STATUS),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row[0] if row else None


def release_run_claim(user_id: int, run_id: int):
    """Put a run back to pending_review after a failed resume."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pipeline_runs SET status = %s WHERE id = %s AND user_id = %s AND status = %s",
        (PENDING_STATUS, run_id, user_id, RESUMING_STATUS),
    )
    conn.commit()
    cur.close()
    conn.close()


def update_run_report(run_id: int, user_id: int, report: dict | None, status: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pipeline_runs SET report = %s, status = %s WHERE id = %s AND user_id = %s",
        (json.dumps(report) if report else None, status, run_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def update_run_decision(run_id: int, user_id: int, decision: str, note: str = "") -> bool:
    """
    Records the human decision on a pipeline run AND logs it to
    reviewer_decisions for future vendor risk adjustment.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE pipeline_runs
           SET human_decision = %s, decided_by = %s, decided_at = %s, reviewer_note = %s
           WHERE id = %s AND user_id = %s
           RETURNING invoice_id, report""",
        (decision, user_id, datetime.now(timezone.utc), note, run_id, user_id),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if row is None:
        return False

    invoice_id, report = row
    report = report or {}
    risk = report.get("stages", {}).get("risk", {}) or {}
    insert_reviewer_decision(
        invoice_id=invoice_id,
        reviewer_id=user_id,
        vendor_name=report.get("vendor_name"),
        decision=decision,
        risk_score_at_decision=risk.get("score"),
        risk_factors=risk.get("reasons", []),
        reviewer_note=note,
    )
    return True


if __name__ == "__main__":
    from backend.app.db import init_db, migrate_per_user_uniqueness
    init_db()
    init_auth_db()
    migrate_per_user_uniqueness()
    print("Schema initialised.")
