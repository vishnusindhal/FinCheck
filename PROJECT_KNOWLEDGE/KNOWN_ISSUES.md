# Known Issues

IDs are stable — reference them in commits and CHANGELOG. When fixing one, move it to **Resolved** with the date instead of deleting it.

Severity: 🔴 blocking / security · 🟠 functional bug · 🟡 limitation / debt

_Last full review: 2026-11-25. Fixes on 2026-11-25 are covered by the offline test suite (`tests/`, 36 tests); none have been exercised against a real PostgreSQL database or the real Gemini API yet._

## Open

| ID | Sev | Issue | Location | Notes |
|---|---|---|---|---|
| R1 | 🟠 | **Not runtime-verified against real services.** New SQL (per-user unique indexes, `DROP CONSTRAINT IF EXISTS invoices_vendor_name_invoice_number_key` / `purchase_orders_po_number_key`, `received_date IS NOT DISTINCT FROM`, `ANY(%s)`) and the Gemini prompt changes have only run against fakes | `db.py`, `auth_db.py`, `system_prompt.py` | First real startup applies migrations automatically. If the old constraint had a non-default name it stays, and cross-user duplicates then show up as `rejected_duplicate` (handled, not a crash) |
| S8 | 🟡 | JWT kept in `localStorage`; no revocation. *Partially mitigated:* default lifetime cut from 7 days to 1 day (`JWT_EXPIRE_MINUTES`) | `auth.js`, `auth.py` | Full fix = httpOnly cookies + CSRF protection; that's a design decision across the HF Space + Vercel origins |
| L1 | 🟡 | Matching keys line items by exact normalized description; different wording for the same item is reported as "not on PO" / "not received" | `matching.py` | Product limitation (D8) |
| L2 | 🟡 | Legacy rows created before per-user ownership (`user_id IS NULL`) are invisible to every user's PO/GR lookups and duplicate checks | `db.py` | Intentional for isolation; back-fill `user_id` manually if needed |
| L3 | 🟡 | Background retrain re-fits on **all** invoices after every completed run (skipped if one is already running) | `anomaly_detection/train.py:retrain_in_background` | Fine for a prototype; schedule/batch it at larger volumes |
| L4 | 🟡 | Rule weights, thresholds and keyword categories are hard-coded | `risk_analysis.py`, `classify.py`, `matching.py` | Roadmap "policy engine" |
| L5 | 🟡 | `/_vercel/insights/script.js` 404s when not hosted on Vercel | `frontend/index.html` | Harmless |
| E1 | 🟡 | Environment: `.env` DB port 5432 vs local Postgres log 5433; configured `MODEL_NAME` must exist for the key; `.venv` copied from another path (use `python -m ...`) | local machine | Not code issues — check before running |

## Resolved

All resolved 2026-11-25 (Claude Code). Test references are in `tests/`.

### Backend — functional
| ID | Issue | Fix |
|---|---|---|
| B1 | Run rows never stored `invoice_id` (`invoice_db_id` key typo) → invoice detail 404 | `main.py` reads `invoice_id`; `db.get_invoice` returns `run_id: null` instead of 404 when no run exists. Test: `test_process_matching_streams_real_starts_and_done` |
| B2 | Invoice-only uploads crashed in `duplicate_detect` | `duplicate_node` handles absent/None PO/GR and PO/GR without numbers (warning). Tests: `test_invoice_only_upload_*` |
| B3 | "New vendor" never fired; vendor average included current invoice | `get_vendor_history(..., user_id, exclude_invoice_id)`. Test: `test_new_vendor_signal_fires_despite_insert` |
| B4 | Env approval limits were strings | `approval._env_amount` casts to float. Test: `test_approval_limits_from_env_are_numeric` |
| B5 | Prompt never asked for confidence (default 0.0) | Prompt now requests 0–1 confidences; `extract_confidences` ignores null-valued fields |
| B6 | Amounts could arrive as strings → false `rejected_invalid` | `helper.normalize_invoice` coerces numbers and currency symbols. Test: `test_numeric_strings_coerced_so_validation_passes` |
| B7 | Mid-pipeline inserts left orphans on failure | `db.persist_documents` (single transaction) + `_cleanup_failed_run` on error/disconnect. Test: `test_failed_run_cleans_up_inserted_rows` |
| B8 | Mismatches endpoint 500 on NULL report | Pending runs store a provisional report; endpoint 404s cleanly when no matching stage |
| B9 | Pending reviews lost on reload (thread_id only in browser) | Server resolves `thread_id` from the run; report view shows Approve/Reject for pending runs; `/api/runs` returns `can_resume` |
| B10 | `vendor_name.strip()` on None | Guarded in `risk_db.insert_reviewer_decision` |
| B11 | PO `vendor_name NOT NULL` / global PO uniqueness | NOT NULL dropped by migration; per-user unique index; PO without number not saved (warning) |
| B12 | `process_context` didn't recognise matching field formats | `helper._describe_issue` maps every format. Test: `test_process_context_describes_real_issue_fields` |
| B13 | Under-billing never surfaced | New `Invoice:price_low:<desc>` **warning** (doesn't fail matching). Test: `test_underbilling_is_warning_not_critical` |
| B14 | `extract()` unbound vars; unused import | Fixed / removed |
| B15 | Misleading training log | Correct vendor/global counts via `logging` |
| B16 | Signup stored raw email; DNS check mandatory | Normalized email stored; `EMAIL_CHECK_DELIVERABILITY` toggle; 72-byte bcrypt limit enforced |
| — | (found during fix) GR `received_date` in arbitrary format crashed DATE insert | `helper.normalize_goods_receipt`. Test: `test_goods_receipt_date_normalized_for_db` |

### Backend — security
| ID | Issue | Fix |
|---|---|---|
| S1 | PO/GR endpoints unauthenticated | Require JWT, scoped by `user_id`. Test: `test_data_endpoints_require_auth` |
| S2 | Global duplicate checks/uniqueness | All duplicate checks take `user_id`; per-user unique indexes. Test: `test_duplicate_is_per_user` |
| S3 | Resume didn't verify ownership; double resume possible | `claim_run_for_resume` atomically moves an owned `pending_review` run to `resuming`; checkpoint verified; released on failure. Tests: `test_resume_other_users_run_is_404`, double-resume 409 |
| S4 | Hard-coded JWT fallback secret | Random per-process secret + warning when unset; `auth.py` loads `.env` itself |
| S5 | CORS `*` with credentials | `CORS_ORIGINS` env; credentials only with explicit origins |
| S6 | Client filename used as path; no limits | Fixed server names, `%PDF-` signature check, `MAX_UPLOAD_MB`. Tests: `test_non_pdf_upload_rejected`, `test_upload_filename_never_used_as_path` |
| S7 | XSS via `innerHTML` | `escapeHtml()` in `utils.js` applied to every templated value; CSV export guards against formula injection |
| S9 | No `.dockerignore` | Added |
| S10 | PO/GR rows had no owner | Inserted with `user_id` |
| — | Reviewer decisions from one user influenced another user's risk scores | `get_vendor_decisions(vendor, reviewer_id=user_id)` |

### Frontend
| ID | Issue | Fix |
|---|---|---|
| F1 | Report view crashed (`resultEl` undefined) | `report.js` rewritten with two decision panels; no thread id needed |
| F2 | Extraction row stuck with < 3 docs; counter leaked | Expected count computed per upload and reset each run |
| F3 | Comparison mismatch keys wrong | Uses real `invoice:qty:` / `gr:qty:` / `invoice:price(_low):` / `invoice:` / `gr:` fields |
| F4 | Duplicate Compare handlers | Single handler in `comparison.js` |
| F5 | Comparison panel ignored by `showView`; `alert()` | `showView` closes it; inline messages |
| F6 | Wrong label for human decisions | Headline/approval labels for approved/rejected/stopped runs |
| F7 | No decision UI in report view | `#reportDecisionActions` panel for pending runs |
| F8 | Hard-coded `API_BASE` | `window.FINCHECK_API_BASE` → same-origin under `/ui/` → localhost fallback; backend serves `/ui/` |
| F9 | `node_start` emitted after completion | Stream `["updates","tasks"]`; real start events |
| — | (found during fix) `display:flex` overrode `hidden`, so Approve/Reject were always visible | Global `[hidden]{display:none!important}` |
| — | (found during fix) `.ledger-footer-btns` selector missing its dot | Fixed |
| — | (found during fix) `enterApp()` could touch globals from later scripts | Init deferred to `DOMContentLoaded` |
| — | Early-exit runs listed under Pending with no report | Stopped report stored; categorized as Declined |

### Architecture / debt
| ID | Issue | Fix |
|---|---|---|
| A1 | Sync graph in async generator blocked event loop | `process_invoice` is a sync endpoint with a sync generator (runs in threadpool) |
| A2 | Anomaly features computed from a single row | `predict._feature_row` builds features with the vendor's stored history. Test: `test_inference_features_use_vendor_history` |
| A3 | Import-time training/DB/LLM work | LLM clients lazy (`extracter.get_llm`); models loaded + retrained from `lifespan` |
| A4 | CWD-relative models dir; startup-only retraining | `MODELS_DIR` absolute (env override); background retrain after runs/decisions |
| A5 | Manual schema init | `AUTO_INIT_DB` (default on) runs `init_db`, `init_auth_db`, `migrate_per_user_uniqueness` at startup |
| A6 | No pooling; SQL in `main.py` | `ThreadedConnectionPool` behind `get_connection()`; read queries moved to `db.py` |
| A7 | Nodes returned full state | Nodes return deltas only |
| A8 | Unused deps | `requirements.txt` trimmed 113 → 76 (+ `psycopg-binary`); `requirements-dev.txt` added |
| A9 | Two `jsonable` helpers | Single recursive `helper.jsonable` |
| A10 | `print` logging | `logging` throughout |
| A11 | Invalid escape sequences | `__main__` blocks rewritten |
| A12 | No tests | `tests/` (36 offline tests), `pytest.ini` |
| A13 | README wrong setup / unverifiable claims | README corrected |
| E2 | No project-level git repository | 2026-11-25: repo initialized in `FinCheck/`, pushed to https://github.com/vishnusindhal/FinCheck; `.gitattributes` marks PDF/PNG binary |
