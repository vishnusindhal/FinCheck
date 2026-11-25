# Setup and Deployment

Status: the offline test suite has been run (36 passed, 2026-11-25). Starting the server against a real database / Gemini has **not** been done yet — update this file when it is.

## Get the code
```bash
git clone https://github.com/vishnusindhal/FinCheck.git
cd FinCheck
```

## Prerequisites
- Python 3.11+ (Docker 3.11; local venv 3.12.1).
- PostgreSQL reachable via `DB_URL` (use a dev database first — startup migrates the schema).
- Gemini API key + an available model id.

## Local development (run everything from the project root `FinCheck/`)

```bash
python -m venv .venv
.venv/Scripts/activate                 # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # + pytest, reportlab (optional)

# .env in the project root: API_KEY, MODEL_NAME, DB_URL, JWT_SECRET (see CONFIGURATION.md)

python -m uvicorn backend.app.main:app --reload --port 8000
# UI:  http://localhost:8000/ui/
```

- Tables are created/migrated automatically at startup (`AUTO_INIT_DB=true`). Manual alternative: `python -m backend.app.auth_db`.
- Alternative frontend server: `cd frontend && python -m http.server 5500` → http://localhost:5500 (talks to `http://127.0.0.1:8000`).
- The existing `.venv` was created at another path; use `python -m …` rather than `uvicorn.exe`.
- Anomaly models live in `<project root>/models` (override `MODELS_DIR`); they load at startup and retrain in the background (needs ≥ 5 invoices).
- Local Postgres: `.local-postgres/` (PostgreSQL 17.6, last seen on port 5433) vs `.env` port 5432 — confirm which one you mean.

## Tests
```bash
python -m pytest          # from the project root; offline, no DB/API key needed
```

## Docker / Hugging Face Spaces
- `Dockerfile`: `python:3.11`, non-root user, installs `requirements.txt`, runs `uvicorn backend.app.main:app --host 0.0.0.0 --port 7860`.
- The container serves both the API and the UI (`/ui/`), so a single Space works without editing JS.
- `.dockerignore` excludes `.env`, `.venv`, `.local-postgres`, `models/`, `output/`, caches.
- Provide env vars as Space secrets. Set `CORS_ORIGINS` if a separately hosted frontend calls the API.
- `models/` inside the container is ephemeral; models retrain at startup.

## Separately hosted frontend (e.g. Vercel)
- Deploy `frontend/` as static files and define `window.FINCHECK_API_BASE` (inline script before `js/config.js`) pointing to the API.
- Add that origin to `CORS_ORIGINS` on the backend.

## Smoke test checklist (manual, not yet performed)
1. `GET /api/health` → ok; server log shows no migration warnings.
2. Sign up / log in at `/ui/`.
3. Sample set 1 (`output/pdf/fincheck-samples/01-*`) → matched; low risk (+10 new vendor) → auto-approved; report view renders.
4. Sample set 2 (`02-*`) → price/qty/total mismatches → pauses for review. Reload the page, open the run from **Pending**, approve/reject from the report view.
5. Re-upload set 1 → `rejected_duplicate` (listed under Declined).
6. Upload only an invoice → pauses for review (no crash).
7. My Invoices → View → Compare Documents shows highlights; JSON/CSV download.
