# Testing

## Automated tests (added 2026-11-25)

Run from the project root: `python -m pytest` (config in `pytest.ini`, `testpaths = tests`). Requires `requirements-dev.txt` (pytest).

**Last run: 2026-11-25 — 37 passed in ~4 s.**

Tests are fully **offline**: `tests/conftest.py` sets dummy env vars before importing the backend, replaces DB functions with an in-memory `FakeDB`, replaces Gemini extractors with fixed Pydantic documents (sample sets "matching" and "mismatch" mirroring `output/pdf/fincheck-samples/`), stubs the explanation LLM, and compiles the real graph with `MemorySaver`.

| File | Covers |
|---|---|
| `tests/test_rules.py` | validator (incl. None invoice), currency normalization, numeric coercion, confidence extraction, GR date normalization, `process_context` field descriptions, `jsonable`, 3-way matching (match, mismatch, under-billing warning, missing PO number), classification, approval env limits, history-aware anomaly features |
| `tests/test_graph.py` | auto-approve path, new-vendor signal, interrupt → resume with human decision, invoice-only upload, invalid stop, per-user duplicates, duplicate-PO warning |
| `tests/test_api.py` | SSE order (`node_start` before `node_complete`), `invoice_id` on run rows, provisional report + mismatches for pending runs, resume without thread id, double-resume 409, cross-user resume 404, invoice-only → interrupted, duplicate stopped report, cleanup after failure, non-PDF rejected, filename not used as path, auth required on data endpoints |

`TestClient` is used without a context manager so the real lifespan (DB, checkpointer) never runs; `app.state.pipeline` is injected.

## Other checks performed 2026-11-25
- All backend files compile with `-W error::SyntaxWarning`.
- `node --check` passes for every `frontend/js/*.js`.
- Every `getElementById` id used in JS exists in `index.html` (except `stage-*` rows created dynamically).

## Runtime verification — 2026-11-25 (real PostgreSQL 17.6 + real Gemini `MODEL_NAME` + headless Chrome)

Server started with `tests/e2e/run_dev_server.py` against an isolated **`fincheck_dev`** database (the user's `reconcile` database was left untouched). Sample PDFs from `output/pdf/fincheck-samples/`.

| Suite | Result | What it covers |
|---|---|---|
| `tests/e2e/e2e_api.py` | **43/43** | health, `/ui/` + assets, auth (signup/dup/short pw/wrong pw/login), 401s, non-PDF 400, set 1: parallel extraction start events, exact extraction (FC-INV-1001, 220, 20, USD, confidences 1.0), match reconciles, new-vendor signal, auto-approve; set 2: price/qty/GR-qty/total issues, interrupt + provisional report; history, `invoice_id` linkage, `can_resume`, run detail, mismatches; user isolation (runs, resume, PO); resume with a fresh token and no thread id, human decision in report, double-resume 409; invoices list/detail with run_id, PO/GR lookups; duplicate → stopped report; other user's invoice-only upload → review, only invoice extracted |
| `tests/e2e/e2e_ui.py` | **38/38**, zero JS errors | sign-up flow, hidden decision buttons, live active stages, auto-approved report (headline, vendor, matching, explanation wording), set 2 pause with Approve/Reject, extraction row complete, **reload → decide from history** (reject with note), Declined/Approved tabs, search, stats, My Invoices, detail, JSON + CSV downloads (content checked), comparison with 7 highlighted cells, panel closes on navigation, duplicate stopped report, logout. Screenshots saved by the script |
| `python -m pytest` | **37/37** | offline unit/graph/API tests |

Observed during the live run: Gemini returned many `503 UNAVAILABLE` (model overloaded); the SDK's internal retries plus `extracter._is_transient` retries recovered every time (one run took ~63 s).

Found and fixed during live testing: explanation said "Flagged…" for auto-approved invoices; missing favicon caused a console 404; blob URL revoked synchronously could cancel downloads.

How to rerun:
```bash
# once: CREATE DATABASE fincheck_dev;  (same server/credentials as .env DB_URL)
python tests/e2e/run_dev_server.py           # terminal 1 — serves http://127.0.0.1:8010
python tests/e2e/e2e_api.py                  # terminal 2 — real Gemini calls
python tests/e2e/e2e_ui.py                   # needs Chrome (CHROME_PATH to override)
```
E2E scripts are not collected by pytest (no `test_` prefix) because they need a live server, network and API quota. Each run creates new random users, so they can be repeated.

## Not covered / not yet verified
- Migrating an **existing** database with legacy data (only a fresh `fincheck_dev` was migrated; `reconcile` was deliberately not touched).
- Anomaly models with ≥ 5 invoices per vendor (training path ran but had too little data for vendor models).
- Docker image build.
- README's 15-invoice evaluation benchmark (data/notebooks not in repo).

## Conventions for new tests
- Add a regression test with every bug fix; name it after the behavior.
- Keep tests offline; patch at the module attribute used by the caller (e.g. `backend.app.db.persist_documents`, `backend.app.extracter.extract_invoice`, `backend.app.main.insert_pipeline_run`).
