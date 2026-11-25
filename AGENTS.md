# AGENTS.md — Instructions for AI Coding Agents

This file applies to every AI coding agent (Claude Code, Codex, Cursor, Copilot, Gemini, etc.) working in this repository.

## 1. Read the knowledge base first (mandatory)

Before starting **any** task, read [`PROJECT_KNOWLEDGE/README.md`](PROJECT_KNOWLEDGE/README.md), then at minimum:

1. `PROJECT_KNOWLEDGE/CURRENT_STATE.md`
2. `PROJECT_KNOWLEDGE/KNOWN_ISSUES.md`
3. The documents relevant to the task (ARCHITECTURE, API_DOCUMENTATION, DATABASE, AI_SYSTEM, WORKFLOWS, …)

Do not re-analyze the whole codebase from scratch; use the knowledge base, then verify the specific parts you'll touch against the source.

## 2. Workflow for every task (feature, bug fix, refactor, improvement)

1. Read the relevant `PROJECT_KNOWLEDGE` files.
2. Understand the current project state.
3. Verify the relevant documentation against the actual source code (the code is the source of truth).
4. Identify affected files, modules and dependencies.
5. Prepare an implementation plan.
6. Implement following existing architecture and `PROJECT_KNOWLEDGE/CODING_GUIDELINES.md`.
7. Test the implementation and check for regressions (see `PROJECT_KNOWLEDGE/TESTING.md`).
8. Update every affected document in `PROJECT_KNOWLEDGE/`.
9. Record significant changes in `PROJECT_KNOWLEDGE/CHANGELOG.md`.
10. Update `PROJECT_KNOWLEDGE/CURRENT_STATE.md` (progress, verification status, pending work, next steps).
11. Update `PROJECT_KNOWLEDGE/DECISIONS.md` whenever an important technical decision is made.
12. Finish with a summary: what was implemented, files modified, test results, documentation updated.

**A task is not complete until both the code and its documentation are updated.**

## 3. Knowledge maintenance rules

- Source code is the ultimate source of truth; fix docs that disagree with it.
- Never leave outdated documentation after changing code; remove or correct obsolete information.
- Update existing documents instead of creating duplicates.
- Record incomplete implementations and failed attempts (CURRENT_STATE / KNOWN_ISSUES).
- Document the reasoning behind important decisions (DECISIONS).
- Reference real file paths, functions and modules.
- Clearly distinguish **verified (code)**, **verified (runtime)**, **unverified/claimed** and **planned**.
- When fixing an item from KNOWN_ISSUES, move it to its "Resolved" section with the date; keep its ID.
- **Never** write passwords, API keys, tokens, connection strings with credentials, or other secrets into any file. Never read out or copy `.env` values.
- Keep `PROJECT_KNOWLEDGE/` under version control alongside the code.

## 4. Project-specific essentials

- Project root is this directory (`FinCheck/`). Run Python from here: `python -m uvicorn backend.app.main:app --port 8000` (imports are `backend.app.*`).
- Git repository: `https://github.com/vishnusindhal/FinCheck` (remote `origin`, branch `main`). Commit or push only when the user asks; use feature branches for larger work. End commit messages with the attribution trailer the session specifies. Never commit `.env`, `.venv/`, `.local-postgres/` or `models/` (all gitignored).
- Don't modify the database, install dependencies, or change `.env` unless the task requires it and the user agrees.
- Pipeline graph: `backend/app/agent.py` (`nodes` + `paths` lists). Code before `interrupt()` in `approval_node` re-runs on resume — keep it side-effect-free.
- New user-data endpoints must use `Depends(get_current_user_id)` and filter by `user_id`.
- Run `python -m pytest` (offline, no DB/API key needed) before finishing any change, and add a regression test for every bug fix.
- Starting the app auto-migrates the database (`AUTO_INIT_DB`, default true) — point `DB_URL` at a dev database when experimenting.
