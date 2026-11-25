# API Documentation

Source: [backend/app/main.py](../backend/app/main.py). Local base URL `http://127.0.0.1:8000`; Docker/HF port `7860`. Behavior verified by `tests/test_api.py` (offline, 2026-11-25).

## Authentication

- OAuth2 password bearer (`tokenUrl="/api/auth/login"`), header `Authorization: Bearer <JWT>`.
- JWT HS256 signed with `JWT_SECRET`; payload `{sub: "<user_id>", email, exp}`; lifetime `JWT_EXPIRE_MINUTES` (default 1440 = 1 day).
- Invalid/expired → `401 {"detail": "Invalid or expired token"}`.
- CORS: `CORS_ORIGINS` (comma-separated; default `*`, in which case credentials are disabled — the API uses bearer headers, not cookies).
- Errors use FastAPI's `{"detail": ...}` format (422 for validation errors).
- Resources owned by another user return **404** (not 403).

## Endpoints

### Public
| Method | Path | Description |
|---|---|---|
| GET | `/` | `{"status":"ok","ui":"/ui/"}` |
| GET | `/api/health` | `{"status":"ok"}` (no DB check) |
| POST | `/api/auth/signup` | JSON `{email, password}` → `{access_token, token_type}`. 400 invalid email (DNS deliverability checked unless `EMAIL_CHECK_DELIVERABILITY=false`) / password < 8 chars or > 72 bytes; 409 exists |
| POST | `/api/auth/login` | form `username` (=email), `password` → token; 401 on bad credentials |
| GET | `/ui/` | Static frontend (`frontend/` mounted with `StaticFiles`, `html=True`) |

### Protected
| Method | Path | Params | Response |
|---|---|---|---|
| POST | `/api/process` | multipart `invoice` (required PDF), `po`, `gr` (optional PDFs) | `text/event-stream` (below). 400 if a file isn't a PDF (`%PDF-` signature), exceeds `MAX_UPLOAD_MB` (default 20), or the invoice is missing |
| POST | `/api/runs/{run_id}/resume` | query `decision` = `approved`\|`rejected`; optional `note`; optional legacy `thread_id` (must match if sent) | `{run_id, decision, report, status}`. 400 bad decision / thread mismatch; **404** not your run; **409** run not pending (already decided, in progress, or no paused checkpoint); 500 graph error (run returns to pending) |
| GET | `/api/runs` | `limit` (1–200, default 50) | `[run]` newest first |
| GET | `/api/runs/{run_id}` | — | `run`; 404 if not owned |
| GET | `/api/runs/{run_id}/mismatches` | — | `report.stages.matching` = `{matched, issues[]}`; 404 if not owned or the run has no matching stage (e.g. invalid/duplicate) |
| GET | `/api/invoices` | `limit` (1–200) | `[{id, invoice_number, vendor_name, invoice_date, total_amount, tax_amount, currency, created_at}]` |
| GET | `/api/invoices/{invoice_id}` | — | all invoice columns + `line_items[{description, quantity, unit_price}]` + `run_id` (latest run, or `null`); 404 if not owned |
| GET | `/api/purchase_orders/{po_number}` | — | latest owned PO with that number (case-insensitive) + `line_items[{description, quantity, unit_price}]`; 404 |
| GET | `/api/goods_receipts/{po_number}` | — | latest owned GR for that PO + `line_items[{description, quantity}]`; 404 |

`run` object: `{id, invoice_id, status, report, human_decision, decided_at, created_at, reviewer_note, can_resume}`.
`status` ∈ `processed`, `pending_review`, `resuming` (transient during a resume), `rejected_invalid`, `rejected_duplicate`.

## SSE protocol (`POST /api/process`)

Each message: `event: <name>\ndata: <json>\n\n`. Graph streamed with `stream_mode=["updates","tasks"]`.

| Event | Data | When |
|---|---|---|
| `node_start` | `{node, label}` | A node actually starts (from LangGraph task events). Parallel extraction nodes start together |
| `node_complete` | `{node, label, state_delta}` | Node finished; `state_delta` contains **only the keys that node changed** |
| `interrupted` | `{message, thread_id, run_id, status:"pending_review", report}` | Approval needs a human. A run row is stored with a **provisional report** (approval decision `needs_review`) |
| `done` | `{status, report, run_id, thread_id}` | Graph reached END. For `rejected_invalid` / `rejected_duplicate` the report is a "stopped" report (`outcome` = status, validation stage only, `explanation` = reason) |
| `error` | `{message}` | Exception; rows inserted by this run are deleted; no run row is written |

Node names: `extract_Invoice`, `extract_PurchaseOrder`, `extract_GoodReceipt`, `validation`, `duplicate_detect`, `3_way_matching`, `classify`, `anomaly_detect`, `risk_analysis`, `approval`, `report_gen` (labels in `NODE_LABELS`).

## Report object

```json
{
  "invoice_number": "fc-inv-1001", "vendor_name": "Greenfield Supplies", "total_amount": 220.0, "currency": "USD",
  "outcome": "completed | rejected_invalid | rejected_duplicate",
  "stages": {
    "validation": {"passed": true, "errors": []},
    "matching": {"matched": true, "issues": [{"field": "...", "expected": "...", "actual": "...", "severity": "critical|warning"}]},
    "classification": {"primary_category": "Office Supplies", "category_breakdown": {"Office Supplies": 1}},
    "anomaly": {"is_anomaly": false, "anomaly_score": 0.0, "model_used": "none|global|<key>|error", "logs": []},
    "risk": {"score": 10, "tier": "low|medium|high", "reasons": ["New/unseen vendor"]},
    "approval": {"decision": "auto_approved|needs_review|approved|rejected", "approver": "...", "routed_to": "...", "note": "...", "source": "automated|human"},
    "warnings": [{"DuplicatePurchaseOrder": "..."}]
  },
  "generated_at": "ISO timestamp",
  "explanation": "One sentence or null"
}
```
Stopped reports contain only `stages.validation`.

Matching issue `field` formats (`matching.py`): `po_number`, `po/gr` (documents missing), `GR:<desc>`, `GR:qty:<desc>`, `Invoice:<desc>`, `Invoice:price:<desc>` (critical, over-billing), `Invoice:price_low:<desc>` (warning, under-billing), `Invoice:qty:<desc>`, `total_amount`. `<desc>` = lower-cased, stripped description.
