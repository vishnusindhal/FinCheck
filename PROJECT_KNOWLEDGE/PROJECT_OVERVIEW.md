# Project Overview

## Purpose

FinCheck is an **Accounts Payable (AP) invoice-review prototype**. A user uploads a supplier invoice PDF plus (optionally) the matching Purchase Order (PO) and Goods Receipt (GR) PDFs. The system:

1. Extracts structured data from each PDF with a Gemini multimodal model.
2. Validates the invoice fields.
3. Detects duplicate invoices / POs / GRs against the database.
4. Performs **3-way matching** (Invoice ↔ PO ↔ GR) on quantities, unit prices and subtotal.
5. Classifies expense category (keyword rules).
6. Runs ML anomaly detection (scikit-learn Isolation Forest) when trained models exist.
7. Computes a rule-based risk score.
8. Routes for approval — auto-approve, or **pause for human review** using LangGraph `interrupt()`.
9. Generates a report with an LLM-written one-sentence explanation.

Progress is streamed to the browser via Server-Sent Events (SSE). FinCheck does **not** pay invoices or integrate with any ERP/bank — it is decision support only.

The project was previously named **"Reconcile"** (venv path `Reconcile-main`, example DB name `reconcile`). README frontmatter targets a Hugging Face Docker Space (port 7860); the README describes the current version as **"FinCheck 1.4"**.

## Business domain

| Document | Created by | Represents |
|---|---|---|
| Purchase Order (PO) | Buyer | What was agreed (items, qty, unit price) |
| Goods Receipt (GR) | Buyer's receiving team | What actually arrived |
| Invoice | Supplier | What the supplier asks to be paid |

3-way matching flags price/quantity disagreements for a human to investigate. A detailed business explanation, personas and sample walkthroughs exist in [../FINCHECK_PROJECT_GUIDE.md](../FINCHECK_PROJECT_GUIDE.md).

## Objectives (from README, partially verified)

- Go beyond extraction to "should this invoice be paid?" decision support.
- Stateful, resumable workflow with human-in-the-loop (implemented via LangGraph checkpointing + `interrupt()` — verified in code).
- Per-user data isolation (implemented for runs, invoices, PO/GR, duplicates, vendor history and reviewer learning).
- Adaptive vendor anomaly detection (vendor model → global model → skip, history-aware features, background retraining).

## Technology stack (verified against code and requirements.txt)

| Layer | Technology | Where |
|---|---|---|
| Language | Python 3.11 (Docker) / 3.12.1 (local venv) | [Dockerfile](../Dockerfile), `.venv/pyvenv.cfg` |
| Web framework | FastAPI 0.136.1, Uvicorn 0.47.0 | [backend/app/main.py](../backend/app/main.py) |
| Orchestration | LangGraph 1.2.0 (`StateGraph`, `Send`, `interrupt`, `Command`) | [backend/app/agent.py](../backend/app/agent.py) |
| Checkpointing | `langgraph-checkpoint-postgres` 3.1.2 (`PostgresSaver`, psycopg 3) | `main.py` lifespan |
| LLM | Google Gemini via `langchain-google-genai` 4.2.5 (`ChatGoogleGenerativeAI`) | [extracter.py](../backend/app/extracter.py), [anomaly_exp.py](../backend/app/anomaly_exp.py) |
| Schemas | Pydantic 2.13 | [schemas.py](../backend/app/schemas.py) |
| Database | PostgreSQL via `psycopg2` (raw SQL, no ORM) | [db.py](../backend/app/db.py), [auth_db.py](../backend/app/auth_db.py), [dbs/risk_db.py](../backend/app/dbs/risk_db.py) |
| ML | scikit-learn 1.9 IsolationForest + StandardScaler, pandas, joblib | [anomaly_detection/](../backend/app/anomaly_detection/) |
| Auth | JWT (`python-jose`, HS256) + bcrypt (`passlib`, bcrypt pinned 4.0.1) | [auth.py](../backend/app/auth.py) |
| Validation helpers | `pycountry` (ISO 4217), `email-validator` | [validator.py](../backend/app/validator.py), `main.py` |
| Frontend | Plain HTML/CSS/JS, no build step, no framework | [frontend/](../frontend/) |
| Hosting | Hugging Face Spaces (Docker) serving API + UI at `/ui/`; optional separate static frontend (Vercel Insights script in `index.html`) | README, `Dockerfile`, `main.py` |

`requirements.txt` holds runtime dependencies only (trimmed 2026-11-25); `requirements-dev.txt` adds pytest and reportlab (the sample PDFs are ReportLab-generated). Tests: pytest, offline (`tests/`).

## Status in one line

Working prototype; all issues found on 2026-11-25 fixed and covered by an offline test suite; **not yet run against real PostgreSQL/Gemini** (see [CURRENT_STATE.md](CURRENT_STATE.md)).
