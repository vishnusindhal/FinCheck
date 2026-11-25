# Architectural & Technical Decisions

Format: ID · decision · reasoning · source · status. Decisions D1–D14 were **inferred** from the existing code and README during the 2026-11-25 analysis; their reasoning is reconstructed, not confirmed by the original author unless the README states it. Add new decisions at the bottom with date and author/agent.

| ID | Decision | Reasoning (inferred unless noted) | Source |
|---|---|---|---|
| D1 | Orchestrate the review as a **LangGraph `StateGraph`** rather than ad-hoc function calls | Explicit stages, conditional early exits, streaming per node, checkpointing and interrupts for free | `agent.py`, README |
| D2 | **Parallel fan-out extraction** with `Send` + `merge_optional` reducer | README: run time gated by slowest document instead of sum (~45 % claimed speedup) | README "What's New 1.4" |
| D3 | **PostgresSaver checkpointing** with a per-run `thread_id` | README: survive restarts, resumable runs | `main.py` lifespan, README |
| D4 | **Human review via `interrupt()` + `Command(resume)`** instead of re-running the pipeline | README: "proper resumable workflow, not a re-run" | `agent.approval_node`, README |
| D5 | **Gemini multimodal with structured output** (PDF bytes sent inline, Pydantic schema) instead of OCR + parsing | Simplest high-quality extraction; one model for all three doc types | `extracter.py` |
| D6 | **Confidence-wrapped invoice fields** unwrapped immediately after extraction | Keep downstream code on plain dicts while still feeding confidences to risk scoring (docstring in `helper.unwrap_confident_fields` says so) | `helper.py` |
| D7 | **Deterministic rules** for validation, matching, classification, risk, approval; LLM only for extraction + explanation | Auditability and predictability of decisions | module code |
| D8 | Match line items by **normalized description** instead of item IDs | Documents rarely share item IDs (comment in `matching.py:11`) | `matching.py` |
| D9 | **Tiered anomaly models** (per user+vendor+currency → global → skip), min 5 samples | Become more specific as history grows; avoid meaningless tiny models (comment `train.py:14`) | `anomaly_detection/` |
| D10 | Store run **report as JSONB** | Read as a whole object, not queried field-by-field (comment `auth_db.py:27`) | `auth_db.py` |
| D11 | Return **404 (not 403)** for resources owned by other users | Don't leak existence (docstring `main.py:359-363`) | `main.py` |
| D12 | **Raw psycopg2 SQL**, no ORM | Simplicity / prototype speed | all db modules |
| D13 | **Vanilla JS frontend**, no build step; SSE consumed via `fetch` stream | POST with auth header isn't possible with `EventSource`; zero tooling | `frontend/` |
| D14 | Backend on **HF Spaces (Docker, :7860)**, frontend on **Vercel** | Free hosting tiers; README frontmatter + Vercel Insights script | README, `Dockerfile`, `index.html` |
| D15 | **2026-11-25 — Knowledge base established** in `PROJECT_KNOWLEDGE/` with `AGENTS.md` mandating it | Allow any AI agent to resume work without re-reading the whole codebase | This analysis (Claude Code) |
| D16 | **2026-11-25 — Documented bugs instead of fixing them** during the initial analysis | User instructed: no application code changes in the initial pass | User instruction |
| D17 | **2026-11-25 — Per-user data isolation** for duplicates, PO/GR lookups, vendor history and reviewer-decision learning; global unique constraints replaced by per-user unique indexes | One tenant's documents must neither block nor reveal another's; risk learning should reflect the user's own reviews | Bulk fix (S1, S2) |
| D18 | **2026-11-25 — Server resolves the resume thread** from `run_id` with an atomic `pending_review → resuming` claim; client `thread_id` optional | Makes reviews resumable after reload/restart and prevents cross-user or double resumes | Bulk fix (B9, S3) |
| D19 | **2026-11-25 — Store a provisional report for pending runs and a "stopped" report for early exits** | History, comparison and the mismatches endpoint always have data to show | Bulk fix (B8, F1) |
| D20 | **2026-11-25 — Persist invoice/PO/GR in one transaction; delete them if the run later fails** (instead of moving persistence to the end of the graph) | Keeps duplicate detection and "My Invoices" working for pending runs while avoiding orphan rows | Bulk fix (B7) |
| D21 | **2026-11-25 — Schema init/migrations run automatically at startup** (`AUTO_INIT_DB`, default on), idempotent DDL, no migration framework | Removes manual setup steps; still lightweight for a prototype. Revisit (e.g. Alembic) if schema churn grows | Bulk fix (A5) |
| D22 | **2026-11-25 — Under-billing reported as a warning, not critical** | Paying less than the PO price isn't a payment risk but is worth surfacing | Bulk fix (B13) |
| D23 | **2026-11-25 — Backend serves the frontend at `/ui/`; `API_BASE` resolves at runtime** | Single-origin Docker/HF deployment works without editing JS; separate hosting still possible via `window.FINCHECK_API_BASE` | Bulk fix (F8) |
| D24 | **2026-11-25 — JWT default lifetime 1 day; tokens stay in localStorage** | Reduces exposure without the cross-origin cookie/CSRF redesign (left open as S8) | Bulk fix (S4/S8) |
| D25 | **2026-11-25 — Tests run fully offline** with fakes for DB/Gemini and `MemorySaver` | Fast, deterministic, no secrets needed; real-service verification tracked separately (R1) | Bulk fix (A12) |
