# Architecture

## High-level components

```
┌─────────────────────────────┐        HTTPS / fetch + SSE         ┌───────────────────────────────────────┐
│ Browser (frontend/)         │ ─────────────────────────────────► │ FastAPI app (backend/app/main.py)     │
│ index.html + js/*.js        │ ◄───────────────────────────────── │  • auth routes (JWT)                  │
│ JWT in localStorage         │   text/event-stream (SSE)          │  • /api/process  → LangGraph stream   │
└─────────────────────────────┘                                    │  • /api/runs/*/resume → Command(resume)│
                                                                   │  • read endpoints (runs/invoices/PO/GR)│
                                                                   └──────┬───────────────┬────────────────┘
                                                                          │               │
                                     ┌────────────────────────────────────┘               │
                                     ▼                                                    ▼
                    ┌──────────────────────────────┐                     ┌──────────────────────────────────┐
                    │ LangGraph pipeline (agent.py)│ ── psycopg2 ──────► │ PostgreSQL                       │
                    │ compiled with PostgresSaver  │ ── psycopg3 ──────► │  app tables + LangGraph          │
                    └──┬────────────┬──────────────┘   (checkpointer)    │  checkpoint tables               │
                       │            │                                    └──────────────────────────────────┘
                       ▼            ▼
        ┌─────────────────────┐  ┌──────────────────────────────┐
        │ Google Gemini API   │  │ Local joblib models          │
        │ (PDF extraction +   │  │ ./models/*.pkl (CWD-relative)│
        │  risk explanation)  │  │ IsolationForest pipelines    │
        └─────────────────────┘  └──────────────────────────────┘
```

## Backend layering

Modules are flat under `backend/app/`:

| Concern | Module(s) | Notes |
|---|---|---|
| HTTP / SSE / startup | `main.py` | Endpoints, upload validation, SSE generator, resume, lifespan (schema init, models, checkpointer), `/ui/` static mount. No SQL |
| Auth primitives | `auth.py` | bcrypt, JWT, `get_current_user_id` |
| Workflow graph | `agent.py` | State type, delta-returning nodes, routing, `create_graph()`. No import-time work |
| Pure domain logic | `validator.py`, `matching.py`, `classify.py`, `approval.py` | No I/O (approval reads env once) |
| Domain logic with I/O | `risk_analysis.py` (vendor history, reviewer decisions), `report.py` (explanation LLM) | |
| LLM | `extracter.py` (lazy shared client `get_llm()`, structured extraction, transient retry), `anomaly_exp.py` (explanation), `system_prompt.py` | |
| Persistence | `db.py` (pool, invoices/PO/GR, reads, migrations), `auth_db.py` (users, runs, resume claim), `dbs/risk_db.py` (reviewer decisions) | Raw SQL; `anomaly_detection/data_handling.py` reuses `db.get_connection` |
| ML | `anomaly_detection/{data_handling,train,predict}.py` | Model registry (`predict.set_models/get_models`), background retrain |
| Utilities | `helper.py` | Confidence unwrap, normalization, vendor history, LLM context, `jsonable` |

No `__init__.py` files under `backend/`; implicit namespace packages; run from the project root.

## LangGraph pipeline (verified from `agent.py`)

State type: `PipelineState` (TypedDict) at [agent.py:41-62](../backend/app/agent.py#L41-L62). `invoice`, `po`, `gr`, `invoice_confidences` use the `merge_optional` reducer (keep non-None) so parallel extraction branches can merge.

```mermaid
flowchart TD
    START((START)) -->|dispatch_extraction: Send fan-out| EI[extract_Invoice]
    START -.->|if po_path| EP[extract_PurchaseOrder]
    START -.->|if gr_path| EG[extract_GoodReceipt]
    EI --> V[validation]
    EP --> V
    EG --> V
    V -->|is_valid| D[duplicate_detect]
    V -->|invalid: status=rejected_invalid| END1((END))
    D -->|not duplicate| M[3_way_matching]
    D -->|duplicate: status=rejected_duplicate| END2((END))
    M --> C[classify]
    C --> A[anomaly_detect]
    A --> R[risk_analysis]
    R --> AP[approval]
    AP -->|needs_review → interrupt(), waits for Command(resume)| AP
    AP --> RG[report_gen]
    RG --> END3((END))
```

Node → function → side effects:

| Node | Function | External effects |
|---|---|---|
| `extract_Invoice` | `extract_Invoice` → `extracter.extract_invoice` | Gemini call |
| `extract_PurchaseOrder` | `extract_PurchaseOrder` → `extract_po` | Gemini call |
| `extract_GoodReceipt` | `extract_GoodReceipt` → `extract_gr` | Gemini call |
| `validation` | `validation_node` → `validator.validate_invoice` | none |
| `duplicate_detect` | `duplicate_node` | Per-user DB checks; inserts invoice (+ new PO/GR) in **one transaction** via `db.persist_documents` |
| `3_way_matching` | `matching_node` → `matching.match_invoice` | none |
| `classify` | `classification_node` → `classify.classify_invoice` | none |
| `anomaly_detect` | `anomaly_node` → `predict.detect_anomaly` | uses in-memory models |
| `risk_analysis` | `risk_node` → `risk_analysis.assess_risk` | DB reads (vendor history, reviewer decisions) |
| `approval` | `approval_node` → `approval.route_approval` (+ `interrupt`) | checkpoint persisted on interrupt |
| `report_gen` | `report_node` → `report.generate_report` | Gemini call if risk score > 0 |

Graph is assembled generically by `create_graph(nodes, paths, checkpointer)` ([agent.py:271-296](../backend/app/agent.py#L271-L296)) from the `nodes` and `paths` lists. A 3-tuple path with label `"fan_out"` becomes a `Send`-based conditional edge; other 3-tuples become ordinary conditional edges.

## Persistence & checkpointing

- `lifespan` in `main.py` runs `initialize_database()` (unless `AUTO_INIT_DB=false`), loads anomaly models, starts a background retrain, opens `PostgresSaver`, calls `setup()`, and compiles the graph into `app.state.pipeline`.
- Each `/api/process` call uses a new `thread_id`, stored on the `pipeline_runs` row. Resume looks the thread up server-side after an atomic ownership claim (`auth_db.claim_run_for_resume`).
- Rows inserted by a run are deleted if the run fails before its run row is saved.

## Frontend architecture

- Single page, multiple `<section class="view">` blocks toggled by `showView()` ([frontend/js/main.js](../frontend/js/main.js)); the comparison panel is closed on every view change and init runs on `DOMContentLoaded`.
- Served by the backend at `/ui/` or by any static host; `API_BASE` is resolved at runtime (`config.js`).
- All untrusted strings pass through `escapeHtml()` before `innerHTML`.
- Classic `<script>` tags sharing globals; load order matters ([index.html:315-323](../frontend/index.html#L315-L323)): config → utils → history → auth → main → report → pipeline → invoices → comparison.
- `authFetch()` in `auth.js` attaches `Authorization: Bearer <token>`; 401 → logout.
- SSE is consumed manually from `fetch()`'s `ReadableStream` (not `EventSource`, because POST + auth header) in `pipeline.js:consumeStream`.

## Design patterns in use

- **Fan-out / fan-in** with LangGraph `Send` + reducer (`merge_optional`).
- **Delta-only node updates**; SSE uses `stream_mode=["updates","tasks"]` for real start/finish events.
- **Atomic claim** (`UPDATE ... WHERE status='pending_review' RETURNING`) guarding resumes.
- **Compensating cleanup** (`db.delete_documents`) for failed runs.
- **Human-in-the-loop interrupt/resume** with durable Postgres checkpoints.
- **Structured LLM output** (`llm.with_structured_output(PydanticModel)`).
- **Confidence-wrapped fields** (`ConfidentField{value, confidence}`) unwrapped right after extraction (`helper.unwrap_confident_fields`), confidences kept separately for risk scoring.
- **Tiered model fallback** for anomaly detection (vendor → global → none).
- **Dependency-injected auth** (`Depends(get_current_user_id)`).
- **Rule tables** for classification (`CLASSIFICATION_RULES`) and additive risk scoring.

## Remaining architectural limitations
- Synchronous graph execution per request in a worker thread (fine for a prototype; consider an async graph or job queue at scale).
- Background retrain re-fits on all invoices (KNOWN_ISSUES L3).
- No migration framework; idempotent DDL at startup (DECISIONS D21).
