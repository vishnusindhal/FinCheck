# Database

PostgreSQL. App tables via `psycopg2` with a `ThreadedConnectionPool` (`db.get_connection()` returns a proxy whose `close()` returns the connection to the pool; falls back to a direct connection if the pool is exhausted; size `DB_POOL_MAX`, default 20). LangGraph checkpoints via `psycopg` 3 (`PostgresSaver`). Raw SQL, no ORM.

The live schema has **not** been inspected; everything below comes from DDL in code. The SQL has not yet been run against a real server (KNOWN_ISSUES R1).

## Initialization & migrations (automatic)

At startup, `main.lifespan` → `initialize_database()` (unless `AUTO_INIT_DB=false`):
1. `db.init_db()` — invoice/PO/GR tables + legacy column additions.
2. `auth_db.init_auth_db()` — `users`, `pipeline_runs`, `user_id` columns, decision/thread columns, indexes, then `risk_db.create_reviewer_decisions_table()`.
3. `db.migrate_per_user_uniqueness()` — drops global constraints `invoices_vendor_name_invoice_number_key` and `purchase_orders_po_number_key` (Postgres default names), drops `NOT NULL` on `purchase_orders.vendor_name`, creates per-user unique indexes. Failure is logged as a warning, not fatal.
4. `PostgresSaver.setup()` — checkpoint tables.

All DDL is idempotent. Manual equivalent: `python -m backend.app.auth_db` (runs steps 1–3).

## Tables

### `invoices`
`id SERIAL PK, vendor_name TEXT NOT NULL (lower-cased), invoice_number TEXT NOT NULL (lower-cased), po_number TEXT, total_amount NUMERIC, tax_amount NUMERIC, currency TEXT (ISO code), invoice_date DATE, created_at TIMESTAMP, user_id INT → users`
- Unique index `invoices_user_vendor_number_uidx (user_id, vendor_name, invoice_number)`; index `invoices_user_idx (user_id)`.

### `invoice_line_items`
`id, invoice_id → invoices ON DELETE CASCADE, description, quantity NUMERIC, unit_price NUMERIC`

### `purchase_orders`
`id SERIAL PK, po_number TEXT NOT NULL (as extracted, stripped), vendor_name TEXT (nullable after migration), currency TEXT, created_at, user_id INT → users`
- Unique index `purchase_orders_user_po_uidx (user_id, LOWER(po_number))`.
- A legacy `invoice_id TEXT` column may exist on old databases (from a removed migration helper); unused.

### `po_line_items`
`id, po_id → purchase_orders ON DELETE CASCADE, description, quantity, unit_price`

### `goods_receipts`
`id SERIAL PK, po_number TEXT NOT NULL, received_date DATE (normalized to ISO or NULL), created_at, user_id INT → users`
- Index `goods_receipts_user_po_idx (user_id, LOWER(po_number))`. Duplicate = same user + PO number + received date (`IS NOT DISTINCT FROM`).

### `gr_line_items`
`id, gr_id → goods_receipts ON DELETE CASCADE, description, quantity_received NUMERIC`

### `users`
`id SERIAL PK, email TEXT NOT NULL UNIQUE (normalized, lower-cased), password_hash TEXT NOT NULL (bcrypt), created_at`

### `pipeline_runs`
| Column | Notes |
|---|---|
| id SERIAL PK | the API `run_id` |
| user_id INT NOT NULL → users ON DELETE CASCADE | |
| invoice_id INT → invoices ON DELETE SET NULL | set for runs that got past duplicate detection |
| status TEXT NOT NULL | `processed`, `pending_review`, `resuming`, `rejected_invalid`, `rejected_duplicate` |
| report JSONB | final, provisional (pending) or stopped report |
| created_at, human_decision, decided_by → users, decided_at, reviewer_note, thread_id | |
Indexes: `pipeline_runs_user_idx (user_id, created_at DESC)`, `pipeline_runs_invoice_idx (invoice_id)`.

### `reviewer_decisions`
`id, invoice_id INT, reviewer_id → users, vendor_name TEXT (lower-cased, nullable), decision TEXT NOT NULL, risk_score_at_decision INT, risk_factors JSONB, reviewer_note TEXT, created_at`. Index `reviewer_decisions_vendor_idx (reviewer_id, vendor_name)`. Queried per reviewer (user).

### LangGraph checkpoint tables
Library-managed (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`). Do not hand-edit.

## Write patterns
- `duplicate_detect` node → `db.persist_documents()` inserts invoice (+PO/GR when new) **in one transaction**; a unique-index race becomes `rejected_duplicate`.
- If the run later fails or the client disconnects before the run row is saved, `db.delete_documents()` removes exactly the rows that run inserted.
- `claim_run_for_resume` uses `UPDATE … WHERE status='pending_review' … RETURNING thread_id` as an atomic lock.

## Relationships
```
users 1─* pipeline_runs *─0..1 invoices 1─* invoice_line_items
users 1─* invoices / purchase_orders / goods_receipts (user_id)
purchase_orders 1─* po_line_items ; goods_receipts 1─* gr_line_items (linked to invoices logically via po_number)
users 1─* reviewer_decisions (reviewer_id)
```

## Local instances (observed)
`.env` points at `localhost:5432/reconcile`; the local `.local-postgres/` server last logged port 5433. Confirm which you use (KNOWN_ISSUES E1).
