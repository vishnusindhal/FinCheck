# Testing

## Automated tests (added 2026-11-25)

Run from the project root: `python -m pytest` (config in `pytest.ini`, `testpaths = tests`). Requires `requirements-dev.txt` (pytest).

**Last run: 2026-11-25 — 36 passed in ~4 s.**

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

## Not covered / not yet verified
- Real PostgreSQL: migrations and SQL (KNOWN_ISSUES R1). Suggested: a disposable DB and an integration test that runs `initialize_database()` twice and the db functions once.
- Real Gemini extraction quality and confidence values.
- Browser UI behavior (no JS test harness; manual checklist in SETUP_AND_DEPLOYMENT.md).
- README's 15-invoice evaluation benchmark (data/notebooks not in repo).

## Conventions for new tests
- Add a regression test with every bug fix; name it after the behavior.
- Keep tests offline; patch at the module attribute used by the caller (e.g. `backend.app.db.persist_documents`, `backend.app.extracter.extract_invoice`, `backend.app.main.insert_pipeline_run`).
