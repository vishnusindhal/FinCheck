# Workflows

Verified against code on 2026-11-25 (after the bulk fix) and exercised by the offline tests where noted.

## 1. Server startup (`main.lifespan`)
1. Importing modules has no heavy side effects (LLM clients are created lazily on first use; no DB access at import).
2. `initialize_database()` if `AUTO_INIT_DB` (default true): `init_db` → `init_auth_db` → `migrate_per_user_uniqueness` (warning on failure).
3. `set_models(load_models())` loads `MODELS_DIR/*.pkl`; `retrain_in_background()` refreshes models from the DB in a daemon thread (needs ≥ 5 invoices).
4. `PostgresSaver.from_conn_string(DB_URL)` → `setup()` → `create_graph(...)` → `app.state.pipeline`. If the DB is unreachable, startup fails.
5. `frontend/` is served at `/ui/`.

## 2. Signup / login
`POST /api/auth/signup` → normalize email (+ optional DNS check) → password 8 chars–72 bytes → 409 if exists → bcrypt → insert → JWT.
`POST /api/auth/login` (form) → verify → JWT. Frontend stores it in `localStorage`, `enterApp()` → `loadHistory()`.

## 3. Invoice processing
```
Browser                                   Backend (sync generator in a worker thread)
FormData{invoice[,po][,gr]} ─POST──────►  save_upload ×3 (fixed names, %PDF- check, size limit) → 400 on failure
                                          stream(graph, stream_mode=[updates,tasks])
◄─ node_start (×1–3, parallel) ─────────    extract_* (Gemini) → normalize invoice / GR
◄─ node_complete (delta) ───────────────    validation ──invalid──► END (status rejected_invalid)
                                            duplicate_detect: per-user dup? ─yes─► END (rejected_duplicate)
                                               PO/GR: no number → warning; dup → warning; else inserted
                                               persist_documents(invoice[,po][,gr]) — one transaction
                                            3_way_matching (no PO/GR → issue "po/gr", unmatched)
                                            classify → anomaly_detect (history-aware; failures non-fatal)
                                            risk_analysis (user-scoped history, excludes this invoice)
                                            approval: auto_approved → report_gen → END
                                                      needs_review → interrupt()
                                          END   → run row (processed | stopped report) → event done → background retrain
                                          pause → run row pending_review + provisional report → event interrupted
                                          error → delete rows this run inserted → event error
```
Client disconnect before the run row is saved also triggers the cleanup. Tests: `test_api.py`, `test_graph.py`.

## 4. Human review
1. Live: the `interrupted` event shows Approve/Reject in the pipeline view (`#decisionActions`).
2. Later: the run appears under **Pending**; opening it renders the provisional report with Approve/Reject in the report view (`#reportDecisionActions`). Works after reload or restart.
3. `POST /api/runs/{id}/resume?decision=…[&note=…]`:
   - `claim_run_for_resume` atomically moves the caller's `pending_review` run to `resuming` and returns its `thread_id` (404 not yours, 409 not pending).
   - `pipeline.get_state` must show `next == ("approval",)` (else 409).
   - `Command(resume={decision, note})` → `approval_node` re-runs from the top (pre-interrupt code is side-effect-free) → `report_gen`.
   - `update_run_report` (user-scoped) + `update_run_decision` (also logs to `reviewer_decisions`) → background retrain.
   - Any failure → `release_run_claim` puts the run back to `pending_review`.

## 5. History
`GET /api/runs` → categorize: `rejected_*` status or human rejected → Declined; human approved or auto-approved → Approved; else Pending. Click → `GET /api/runs/{id}` → `renderReport(report, status, run)`.

## 6. My Invoices → detail → comparison
`GET /api/invoices` → View → `GET /api/invoices/{id}` (line items + latest `run_id`, may be null) → Compare (disabled without PO number) → parallel PO / GR / mismatches requests (all authenticated, user-scoped) → summary + line-item tables with highlights. Missing pieces show inline messages. JSON/CSV export is client-side.

## 7. Anomaly model lifecycle
- Train: `train.retrain_from_db()` at startup and after each completed run / human decision (non-blocking; skipped if one is running). Per `(user, vendor, currency)` with ≥ 5 invoices + global model.
- Predict: vendor model → global → skip. Features for the current invoice are computed together with the user's stored invoices for that vendor (excluding the current row), mirroring training.
