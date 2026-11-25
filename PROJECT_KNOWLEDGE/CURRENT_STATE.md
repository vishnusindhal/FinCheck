# Current State

_Last updated: 2026-11-25 by Claude Code (live end-to-end verification)._

## Summary

All issues from the initial analysis are fixed, and the app has been **verified live** with the sample PDFs: real PostgreSQL + real Gemini + headless Chrome — **43/43 API checks, 38/38 browser checks (no JS errors), 37/37 offline tests**. Details in [TESTING.md](TESTING.md).

## Verification status

| What | Status |
|---|---|
| Unit tests: validator, matching, classify, approval, helpers, anomaly features | ✅ verified (pytest, offline) |
| Graph routing: auto-approve, interrupt → resume, invoice-only, invalid, per-user duplicate, duplicate-PO warning | ✅ verified with `MemorySaver` + fakes |
| API: SSE events order, run row gets `invoice_id`, provisional report, resume ownership / double resume, cleanup on failure, upload validation, auth on data endpoints | ✅ verified with `TestClient` + fakes |
| Python compiles without warnings; all `frontend/js/*.js` pass `node --check`; every JS element id exists in `index.html` | ✅ verified |
| Real PostgreSQL (auto-migrations on a fresh DB, all SQL paths) | ✅ verified live (`fincheck_dev`) |
| Real Gemini extraction + confidences + explanation | ✅ verified live (sample sets exact; confidences 1.0) |
| Browser UI end to end | ✅ verified live (headless Chrome, `tests/e2e/e2e_ui.py`) |
| Migrating the existing `reconcile` DB | ❌ not done on purpose (R2) |
| Docker image build | ❌ not run |

## What changed (high level)
- Backend: per-user isolation everywhere, transactional persistence + cleanup, ownership-checked resume that no longer needs the browser's thread id, provisional reports for pending runs, stopped reports for early exits, real `node_start` SSE events, non-blocking streaming, pooled DB connections, lazy LLM clients, startup schema init, history-aware anomaly features with background retraining.
- Frontend: report view fixed, pending reviews can be decided from history, HTML escaping, comparison panel fixed, same-origin UI served at `/ui/`.
- Config: trimmed `requirements.txt`, `requirements-dev.txt`, `.dockerignore`, `pytest.ini`, README corrected.

## Behavior changes to be aware of
- JWT lifetime default is now **1 day** (was 7) — set `JWT_EXPIRE_MINUTES=10080` to restore.
- If `JWT_SECRET` is missing, a random secret is used (tokens reset on restart) instead of a public constant.
- On first startup the app **alters the database**: creates missing tables/columns, drops the global unique constraints on `invoices(vendor_name, invoice_number)` and `purchase_orders(po_number)`, drops `NOT NULL` on `purchase_orders.vendor_name`, and creates per-user unique indexes. Disable with `AUTO_INIT_DB=false`.
- Invoices without PO/GR no longer crash; they're routed to human review.
- Under-billing now appears as a matching **warning** (doesn't change approval).
- PO/GR/invoice lookups only see rows owned by the caller (legacy NULL-owner rows are hidden).

## Recommended next steps
1. The old uvicorn on port 8000 still runs pre-fix code — stop it and start the new code (`python -m uvicorn backend.app.main:app --port 8000`).
2. Before pointing the new code at `reconcile`, back it up (`pg_dump`) — startup migrates it (R2). Or keep using `fincheck_dev` / set `AUTO_INIT_DB=false`.
3. Build and smoke-test the Docker image.
4. Decide on token storage (S8).

## Files not inspected / unverified (unchanged from initial analysis)
- `.env` values (only variable names, model name and DB host/port/db name were read; nothing recorded).
- Live DB schema and `.local-postgres/` data; `assets/final-ui-ledger.png`; sample PDF text contents.

## Version control
Repository: https://github.com/vishnusindhal/FinCheck (`main`). Commit 1 = the codebase as found (pre-fix baseline); commit 2 = knowledge base + all 2026-11-25 fixes, so `git diff HEAD~1` shows every change. The temporary folder backup `../_backup_before_fixes_2026-11-25/` is now redundant and can be deleted.
