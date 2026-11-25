# Features

Status key: ✅ implemented and covered by offline tests · ☑️ implemented (code + static checks, no automated test) · 📋 planned / claimed only.
**2026-11-25: every feature below was also verified live** (real PostgreSQL + Gemini + headless Chrome, sample PDFs) — `tests/e2e/`, 43/43 API + 38/38 UI checks. Exception: anomaly vendor models (needs ≥ 5 invoices per vendor).

## Backend

| Feature | Status | Implementation |
|---|---|---|
| Signup / login (JWT, bcrypt) | ☑️ | `main.signup/login`, `auth.py`, `auth_db.py`. Normalized email; optional DNS check; 1-day tokens |
| Upload validation (PDF signature, size, safe filenames) | ✅ | `main.save_upload` |
| Parallel extraction (invoice/PO/GR, only uploaded ones) | ✅ | `agent.dispatch_extraction` + `Send` |
| Extraction confidence scores | ☑️ | Prompt asks for 0–1 confidence; `helper.extract_confidences` (skips null fields) |
| Post-extraction normalization (numbers, currency symbols, GR dates) | ✅ | `helper.normalize_invoice`, `normalize_goods_receipt` |
| Invoice validation | ✅ | `validator.validate_invoice` |
| Per-user duplicate detection (invoice → stop; PO/GR → warning) | ✅ | `agent.duplicate_node`, `db.check_duplicate*` |
| Invoice-only uploads | ✅ | Matching reports `po/gr` missing → human review |
| Transactional persistence + cleanup on failure | ✅ | `db.persist_documents`, `main._cleanup_failed_run` |
| 3-way matching (+ under-billing warning) | ✅ | `matching.match_invoice` |
| Expense classification | ✅ | `classify.py` |
| ML anomaly detection with vendor-history features | ✅ (features) / ☑️ (training) | `anomaly_detection/*`; background retrain |
| Risk scoring (user-scoped history + reviewer learning) | ✅ | `risk_analysis.assess_risk` |
| Approval routing (numeric env limits) | ✅ | `approval.route_approval` |
| Human-in-the-loop interrupt/resume, resumable after reload | ✅ | `agent.approval_node`, `main.resume_run`, `auth_db.claim_run_for_resume` |
| Durable checkpoints (PostgresSaver) | ☑️ | `main.lifespan` |
| Provisional / stopped / final reports + LLM explanation | ✅ | `report.py`, `main._provisional_report` |
| Real-time SSE with true start events | ✅ | `main.process_invoice` |
| Run history, run detail, mismatches | ✅ / ☑️ | `/api/runs*` |
| Invoices list/detail, PO/GR lookups (auth + user-scoped) | ☑️ (auth ✅) | `db.list_invoices/get_invoice/get_purchase_order/get_goods_receipt` |
| Automatic schema init / migration | ☑️ | `main.initialize_database` |
| Same-origin UI hosting at `/ui/` | ☑️ | `StaticFiles` mount |

## Frontend

| Feature | Status | File |
|---|---|---|
| Login / signup | ☑️ | `auth.js` |
| Upload 1–3 PDFs | ☑️ | `pipeline.js` |
| Live stage list with real start/finish, expandable logs (matching, anomaly, risk, validation, duplicate warnings) | ☑️ | `pipeline.js` |
| Approve / Reject right after a live run pauses | ☑️ | `report.js` (`#decisionActions`) |
| Approve / Reject later from history (report view) | ☑️ | `report.js` (`#reportDecisionActions`) |
| Report view (final, pending, stopped runs) | ☑️ | `report.js` |
| Sidebar: Pending / Approved / Declined, stats, search | ☑️ | `history.js` |
| My Invoices, detail, JSON/CSV export (formula-safe) | ☑️ | `invoices.js` |
| 3-way comparison with mismatch highlighting | ☑️ | `comparison.js` |
| XSS-safe rendering | ☑️ | `utils.escapeHtml` |

## Claimed in README, not verifiable from the repository
- 15-invoice evaluation benchmark (score 0.964).
- "~45 % extraction speedup".

## Planned
See [ROADMAP.md](ROADMAP.md).
