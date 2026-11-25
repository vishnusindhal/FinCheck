# Coding Guidelines

These describe the conventions **actually used** in the code, plus rules to follow going forward. Where current code violates a "going forward" rule, don't mass-refactor unless the task asks for it.

## Backend (Python)

### Observed conventions
- Absolute imports from the project root: `from backend.app.x import y`. No `__init__.py` files. Always run from `FinCheck/`.
- Flat modules in `backend/app/`, one concern each (validator, matching, classify, risk_analysis, approval, report).
- Raw SQL with psycopg2, `%s` parameter placeholders (never string-format values into SQL). `get_connection()` returns a pooled connection; always `close()` it (returns it to the pool), ideally in `finally`.
- Vendor names and invoice numbers are normalized with `.strip().lower()` before storing/comparing. Keep this consistent in any new query.
- Pydantic models in `schemas.py` for LLM output and match results; downstream code works with **plain dicts** (`model_dump()` / `unwrap_confident_fields`).
- Pipeline node functions are named `<thing>_node` (except extraction nodes: `extract_Invoice`, `extract_PurchaseOrder`, `extract_GoodReceipt`), take `state: PipelineState`, read optional keys with `state.get(...)`, and return **only the keys they change**. New state keys must be declared in `PipelineState`.
- Graph wiring is data-driven via the `nodes` and `paths` lists in `agent.py`. Add a node by appending to both lists; for a new fan-out target, also add it to `EXTRACTION_NODES`. Nodes call collaborators through module attributes (`extracter.extract_invoice`, `db.persist_documents`) so tests can patch them.
- User-owned data queries filter with `WHERE ... AND user_id = %s` and return 404 (not 403) when not owned.
- FastAPI auth via `user_id: int = Depends(get_current_user_id)`.
- Errors raised as `HTTPException(status_code, detail="...")`.
- Logging via `logging.getLogger(__name__)`; configured in `main.py` (`LOG_LEVEL`).

### Rules going forward
1. Every new endpoint that returns user data **must** depend on `get_current_user_id` and scope SQL by `user_id`.
2. Nodes that run before `interrupt()` in the same node will run again on resume — keep pre-interrupt code side-effect-free.
3. When adding state keys written by parallel branches, give them a reducer (`Annotated[..., reducer]`).
4. Don't do I/O or model construction at import time (use lazy getters like `extracter.get_llm()`; startup work goes in `main.lifespan`).
5. Reading env vars that are numbers: cast explicitly (`int(os.getenv(...))`).
6. Use `db.get_connection()`; don't create new connection helpers. Multi-row writes that belong together go in one transaction (see `db.persist_documents`).
7. Put SQL in a db module (`db.py`, `auth_db.py`, `dbs/`) rather than in `main.py`.
8. Never log or return secrets; never commit `.env`.
9. Keep pure logic (validator/matching/classify/approval) free of DB/LLM calls so it stays unit-testable.
10. Every bug fix gets a regression test in `tests/` (offline; patch DB/LLM).

## Frontend (vanilla JS)

### Observed conventions
- No modules/bundler: classic scripts sharing globals; dependencies documented in each file's header comment. Respect the load order in `index.html`.
- All protected calls go through `authFetch(path, options)`.
- DOM refs cached in `els` (main.js) or local `document.getElementById`.
- View switching with `showView(name)` and the `hidden` attribute.
- CSS design tokens in `:root` of `style.css` (`--paper`, `--ink`, `--ledger-green`, `--rust`, `--amber`, fonts Source Serif 4 / IBM Plex Mono / Inter). Reuse tokens; don't hard-code colors.
- Status classes: `ok` / `warn` / `flagged`; tags `tag-approved` / `tag-review` / `tag-rejected`; headline `report-decision approved|review|rejected`.
- Toggle visibility with the `hidden` attribute (a global `[hidden]{display:none!important}` makes it reliable).
- Init code runs on `DOMContentLoaded` (scripts share globals across files).

### Rules going forward
1. Use `textContent`, or `escapeHtml()` from `utils.js` inside `innerHTML` templates, for any data from documents/LLM/DB.
2. Keep SSE event names/payloads in sync with `main.py` and update API_DOCUMENTATION.md when changing them.
3. Frontend matching-issue parsing must use the exact `field` formats produced by `matching.py`.

## Documentation
- Update `PROJECT_KNOWLEDGE/` in the same change as the code (see AGENTS.md).
- Reference real paths, e.g. `backend/app/agent.py:approval_node`.
