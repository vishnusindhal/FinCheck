# Changelog

Chronological record of significant changes. Newest first. Reference KNOWN_ISSUES IDs where relevant.

Git history starts on 2026-11-25 (baseline import of the code as found); entries before that are reconstructed and approximate.

## 2026-11-25 — Version control set up
- Initialized git in `FinCheck/` with remote `https://github.com/vishnusindhal/FinCheck`; baseline commit of the original code, followed by the fix commit.
- `.gitattributes`: `*.pdf`, `*.png`, `*.jpg` marked `binary` (the user's global `core.autocrlf=true` would otherwise treat the ReportLab PDFs as text).

## 2026-11-25 — Bulk fix of all known issues (Claude Code)
Fixes every item from the initial analysis (B1–B16, S1–S7, S9, S10, F1–F9, A1–A13) plus issues found while fixing. Details per ID in KNOWN_ISSUES.md → Resolved.

**Backend**
- `main.py`: sync SSE generator (no event-loop blocking); `stream_mode=["updates","tasks"]` for real `node_start` events; safe uploads (fixed names, PDF signature, size limit); cleanup of inserted rows on failure/disconnect; provisional report for pending runs and stopped report for early exits; resume resolves `thread_id` server-side with atomic ownership claim; all read SQL moved to `db.py`; static frontend at `/ui/`; `CORS_ORIGINS`; logging; auto schema init (`AUTO_INIT_DB`).
- `agent.py`: delta-only nodes; optional PO/GR handled; single-transaction persistence via `db.persist_documents`; no import-time training; anomaly failures non-fatal.
- `db.py`: connection pool; per-user duplicate checks and reads; `persist_documents`, `delete_documents`, `migrate_per_user_uniqueness`.
- `auth_db.py`: `claim_run_for_resume`, `release_run_claim`, user-scoped `update_run_report`, `can_resume` in run payloads; `__main__` runs full schema init.
- `auth.py`: loads `.env`, random secret fallback, `JWT_EXPIRE_MINUTES` (default 1 day).
- `helper.py`: `to_number`, `normalize_invoice`, `normalize_date`, `normalize_goods_receipt`, issue descriptions for every matching field format, unified `jsonable`, user-scoped/excluding `get_vendor_history`.
- `matching.py`: `Invoice:price_low:` warning for under-billing.
- `risk_analysis.py`, `dbs/risk_db.py`: user-scoped vendor history and reviewer decisions.
- `approval.py`: numeric env limits.
- `extracter.py` / `anomaly_exp.py`: lazy shared Gemini client; retry on transient errors (429/5xx) only.
- `system_prompt.py`: asks for 0–1 confidence values.
- `anomaly_detection/`: absolute `MODELS_DIR`, model registry, history-aware inference features, background retrain.

**Frontend**
- `report.js` rewritten (decision panels for pipeline + report views); `history.js` (escaping, stopped runs → Declined, search/filter unified); `pipeline.js` (per-run extraction count, error slot, more stage logs); `comparison.js` (correct mismatch keys, no alert, single handler); `invoices.js` (escaping, CSV formula guard); `config.js` (API base resolution); `main.js` (DOMContentLoaded init, comparison handled by `showView`); `index.html` (report-view decision panel, `#pipelineError`); `style.css` (`[hidden]` fix, `.ledger-footer-btns` typo, new styles).

**Project**
- Added `tests/` (36 offline tests), `pytest.ini`, `requirements-dev.txt`, `.dockerignore`.
- `requirements.txt` trimmed to runtime deps (+ `psycopg-binary`).
- README setup instructions and claims corrected.
- Pre-fix backup at `../_backup_before_fixes_2026-11-25/`.

## 2026-11-25 — Project knowledge base created
- Added `PROJECT_KNOWLEDGE/` (18 documents) and root `AGENTS.md` after a full read-through. No code changed.

## Before 2026-11-25 (reconstructed, unverified dates)
- `FINCHECK_PROJECT_GUIDE.md` and sample PDFs (`output/pdf/fincheck-samples/`, ReportLab-generated) added.
- Local PostgreSQL 17.6 data directory `.local-postgres/` created.
- **FinCheck 1.4** (per README): parallel extraction fan-out, PostgresSaver checkpointing, human-in-the-loop via `interrupt()`.
- Earlier: per-user auth + run history, reviewer-decision risk learning, adaptive anomaly detection, 3-way comparison UI, invoice export.
- Project earlier named **Reconcile**.
