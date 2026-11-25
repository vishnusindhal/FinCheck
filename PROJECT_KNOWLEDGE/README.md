# PROJECT_KNOWLEDGE — Start Here

This folder is the persistent knowledge base for **FinCheck**, an AI-assisted Accounts Payable invoice-review prototype (FastAPI + LangGraph + Gemini + PostgreSQL + vanilla JS frontend).

Every AI coding agent (and human) must read this folder before changing code. The source code is always the final authority; if a document disagrees with the code, trust the code and fix the document.

## Recommended reading order

| # | File | Read when |
|---|------|-----------|
| 1 | [CURRENT_STATE.md](CURRENT_STATE.md) | Always first — what works, what's broken, what to do next |
| 2 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Purpose, business domain, tech stack |
| 3 | [ARCHITECTURE.md](ARCHITECTURE.md) | Components, LangGraph pipeline, diagrams |
| 4 | [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) | Where things live |
| 5 | [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Before touching any module — many verified bugs |
| 6 | [WORKFLOWS.md](WORKFLOWS.md) | End-to-end request/data flow |
| 7 | [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | Endpoint contracts, SSE events |
| 8 | [DATABASE.md](DATABASE.md) | Tables, columns, init order |
| 9 | [AI_SYSTEM.md](AI_SYSTEM.md) | Gemini calls, prompts, LangGraph graph, ML anomaly models |
| 10 | [FEATURES.md](FEATURES.md) | Feature inventory with verified status |
| 11 | [CONFIGURATION.md](CONFIGURATION.md) | Env vars (names only — never secrets) |
| 12 | [SETUP_AND_DEPLOYMENT.md](SETUP_AND_DEPLOYMENT.md) | Running locally, Docker, deploy |
| 13 | [CODING_GUIDELINES.md](CODING_GUIDELINES.md) | Conventions to follow |
| 14 | [TESTING.md](TESTING.md) | Test suite, how to run, coverage gaps |
| 15 | [ROADMAP.md](ROADMAP.md) | Planned work |
| 16 | [DECISIONS.md](DECISIONS.md) | Why things are the way they are |
| 17 | [CHANGELOG.md](CHANGELOG.md) | History of significant changes |

## Quick facts

- **Project root:** the `FinCheck/` directory (contains `backend/`, `frontend/`, `Dockerfile`, `requirements.txt`).
- **Backend entry point:** [backend/app/main.py](../backend/app/main.py) — run from the project root as `python -m uvicorn backend.app.main:app --port 8000` (imports are absolute `backend.app.*`). UI served at `/ui/`.
- **Pipeline definition:** [backend/app/agent.py](../backend/app/agent.py).
- **Frontend:** static files in [frontend/](../frontend/); backend URL resolved in [frontend/js/config.js](../frontend/js/config.js).
- **Tests:** `python -m pytest` (offline, 37 tests) + live end-to-end scripts in `tests/e2e/` — see TESTING.md.
- **Repository:** https://github.com/vishnusindhal/FinCheck (`main`). History starts with a pre-fix baseline commit, then the 2026-11-25 fix commit.

## Verification legend used across these docs

- **Verified (code)** — confirmed by reading the source code on 2026-11-25.
- **Verified (tests)** — covered by the offline pytest suite.
- **Verified (runtime)** — confirmed against real PostgreSQL/Gemini/browser (done 2026-11-25, `tests/e2e/`).
- **Unverified / claimed** — stated in README or other docs but not provable from the repository.
- **Planned** — not implemented.

## Maintenance rules (summary — full rules in [../AGENTS.md](../AGENTS.md))

1. After any code change, update every affected doc here.
2. Log significant changes in CHANGELOG.md, update CURRENT_STATE.md, record decisions in DECISIONS.md.
3. Never write secrets (API keys, DB passwords, JWT secrets) into these files.
4. Prefer editing existing files over creating new ones.
