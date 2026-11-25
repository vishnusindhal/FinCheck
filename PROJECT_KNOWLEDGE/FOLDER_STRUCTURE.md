# Folder Structure

Paths are relative to the project root `FinCheck/`. Generated/ignored directories are listed but not documented in detail.

```
FinCheck/
├── AGENTS.md                     # Mandatory instructions for AI agents (read first)
├── PROJECT_KNOWLEDGE/            # This knowledge base
├── README.md                     # Public README (also HF Spaces frontmatter: sdk docker, port 7860)
├── FINCHECK_PROJECT_GUIDE.md     # Business/user guide: domain, personas, sample walkthroughs, limitations
├── Dockerfile                    # python:3.11 image, runs uvicorn backend.app.main:app on :7860
├── requirements.txt              # Pinned runtime deps
├── requirements-dev.txt          # + pytest, reportlab (dev/test only)
├── pytest.ini                    # testpaths = tests
├── .dockerignore                 # keeps .env/.venv/local DB/models out of images
├── tests/                        # Offline pytest suite (conftest fakes DB + Gemini)
│   ├── conftest.py, test_rules.py, test_graph.py, test_api.py
│   └── e2e/                      # Live checks (real DB/Gemini/Chrome): run_dev_server.py, e2e_api.py, e2e_ui.py
├── .env                          # Local secrets — gitignored. NEVER copy values into docs
├── .gitignore                    # Ignores .env, /data, /test, /models, notebooks, .venv, .local-postgres*, todo.txt
├── .gitattributes                # Git LFS patterns (HF Spaces default template)
├── .venv/                        # Local Python 3.12.1 venv (ignored; originally created at a different path)
├── .local-postgres/              # Local PostgreSQL 17.6 data directory (ignored; do not edit)
├── .local-postgres.log           # Its server log (shows it listened on 127.0.0.1:5433)
├── assets/
│   └── final-ui-ledger.png       # UI screenshot
├── output/pdf/fincheck-samples/  # 6 fictional sample PDFs (ReportLab-generated)
│   ├── 01-matching-{invoice,purchase-order,goods-receipt}.pdf
│   └── 02-mismatch-{invoice,purchase-order,goods-receipt}.pdf
├── backend/
│   └── app/                      # (no __init__.py anywhere — implicit namespace packages)
│       ├── main.py               # FastAPI app: lifespan (schema init, models, PostgresSaver + graph), auth,
│       │                         #   /api/process SSE, resume, read endpoints, /ui static mount
│       ├── agent.py              # LangGraph PipelineState, delta-returning nodes, routing, nodes/paths, create_graph()
│       ├── auth.py               # bcrypt hashing, JWT create/decode, get_current_user_id dependency
│       ├── auth_db.py            # users + pipeline_runs DDL, user/run CRUD, resume claim/release, decisions
│       ├── db.py                 # pooled get_connection(); invoices/PO/GR DDL + per-user migration; per-user
│       │                         #   duplicate checks; persist_documents/delete_documents; read queries
│       ├── dbs/
│       │   └── risk_db.py        # reviewer_decisions table: create, insert, get_vendor_decisions
│       ├── schemas.py            # Pydantic: ConfidentField, Invoice, PurchaseOrder, GoodsReceipt, MatchIssue, MatchResult
│       ├── system_prompt.py      # INVOICE/PO/GR extraction prompts
│       ├── extracter.py          # lazy Gemini client get_llm(), structured extractors, transient retry (sic: "extracter")
│       ├── validator.py          # Required fields, amounts, date formats, ISO-4217 currency
│       ├── matching.py           # 3-way match by normalized description; 2% price/total tolerance
│       ├── classify.py           # Keyword-rule expense classification
│       ├── risk_analysis.py      # Additive risk score + tier
│       ├── approval.py           # Routing rules (auto_approved / needs_review + approver)
│       ├── report.py             # generate_report (final/provisional) + generate_stopped_report
│       ├── anomaly_exp.py        # Gemini "risk explanation" prompt + call (name is misleading: not anomaly-specific)
│       ├── helper.py             # confidences, to_number/normalize_*, get_vendor_history, process_context, jsonable
│       └── anomaly_detection/
│           ├── data_handling.py  # get_invoice_sample(), get_vendor_invoices(), build_features(), FEATURES
│           ├── train.py          # train_all(), retrain_from_db(), retrain_in_background(); absolute MODELS_DIR
│           └── predict.py        # model registry (set/get_models), load_models(), detect_anomaly()
└── frontend/
    ├── index.html                # All views: auth, sidebar ledger, upload, pipeline, report, invoices, comparison
    ├── style.css                 # Design tokens (:root vars) + all styles (~860 lines)
    └── js/
        ├── config.js             # API_BASE resolution (FINCHECK_API_BASE → same origin /ui → localhost:8000)
        ├── utils.js              # escapeHtml, formatCurrency/Date/Timestamp, capitalize
        ├── auth.js               # token storage (localStorage keys ledger_token/ledger_email), authFetch, login/signup
        ├── main.js               # els refs, showView(), init (enterApp or showAuthScreen)
        ├── history.js            # Sidebar run list, Pending/Approved/Declined tabs, stats, search
        ├── pipeline.js           # Upload form, SSE parsing, live stage list, interrupt → Approve/Reject
        ├── report.js             # renderReport(), setupDecisionButtons(), submitDecision() → /resume
        ├── invoices.js           # My Invoices list/detail, JSON + CSV export
        └── comparison.js         # 3-way comparison panel (PO/GR/mismatch fetch + tables)
```

## Directories referenced by code but absent from the workspace

| Path | Referenced by | Status |
|---|---|---|
| `models/` | `anomaly_detection/train.py` (`MODELS_DIR`, default `<project root>/models`) | Absent; created on first successful training (needs ≥5 invoices) |
| `data/` | `__main__` blocks in `agent.py`, `extracter.py` | Absent (gitignored) |
| `notebooks/`, `test/` | `.gitignore` (evaluation notebooks, old test scripts) | Absent — README's benchmark cannot be reproduced. Automated tests live in the tracked `tests/` |
| `todo.txt` | `.gitignore` | Absent |
