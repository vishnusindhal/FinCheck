# Configuration

**Never write real secret values into this repository's docs.** The local `.env` is gitignored and docker-ignored.

## Environment variables

| Variable | Required | Default | Read in | Purpose |
|---|---|---|---|---|
| `API_KEY` | Yes | `""` | `extracter.get_llm` | Gemini API key |
| `MODEL_NAME` | No | `gemini-2.5-flash` | `extracter.get_llm` | Gemini model (extraction + explanation) |
| `DB_URL` | Yes | — | `db._get_pool`, `main.lifespan` (checkpointer) | `postgresql://USER:PASSWORD@HOST:PORT/DBNAME` (used by psycopg2 and psycopg 3) |
| `JWT_SECRET` | Yes (prod) | random per process (warning logged) | `auth.py` | HS256 signing key; without it tokens reset on every restart |
| `JWT_EXPIRE_MINUTES` | No | `1440` | `auth.py` | Token lifetime |
| `CORS_ORIGINS` | No | `*` | `main.py` | Comma-separated allowed origins; credentials enabled only when not `*` |
| `AUTO_INIT_DB` | No | `true` | `main.lifespan` | Create/upgrade tables at startup |
| `DB_POOL_MAX` | No | `20` | `db.py` | Max pooled connections |
| `MAX_UPLOAD_MB` | No | `20` | `main.py` | Per-file upload limit |
| `EMAIL_CHECK_DELIVERABILITY` | No | `true` | `main.signup` | DNS check on signup emails (set `false` offline) |
| `AUTO_APPROVE_LIMIT` | No | `5000` | `approval.py` | Auto-approve threshold (cast to float) |
| `DIRECTOR_REVIEW_LIMIT` | No | `5000` | `approval.py` | Finance Director threshold |
| `MODELS_DIR` | No | `<project root>/models` | `anomaly_detection/train.py` | Where anomaly models are stored |
| `LOG_LEVEL` | No | `INFO` | `main.py` | Python logging level |

The current local `.env` defines `API_KEY`, `DB_URL`, `JWT_SECRET`, `MODEL_NAME` (values not recorded).

Every module that reads env at import calls `load_dotenv()` itself, so import order no longer matters.

## Frontend configuration
`frontend/js/config.js` resolves `API_BASE`:
1. `window.FINCHECK_API_BASE` if defined (add `<script>window.FINCHECK_API_BASE="https://…"</script>` before `config.js` for a separately hosted frontend),
2. same origin when served under `/ui/` by the backend,
3. otherwise `http://127.0.0.1:8000`.

localStorage keys: `ledger_token`, `ledger_email`.

## Hard-coded settings
| Setting | Location | Value |
|---|---|---|
| JWT algorithm | `auth.py` | HS256 |
| Matching tolerance | `matching.py` | 2 % |
| Risk weights / tiers, low-confidence threshold 0.6 | `risk_analysis.py` | see AI_SYSTEM.md |
| Anomaly min samples / contamination | `train.py` | 5 / 0.05 |
| Extraction retries | `extracter.py` | 3 (transient errors only) |
| Container port | `Dockerfile` | 7860 |

## External services
| Service | Used for |
|---|---|
| Google Gemini API | PDF extraction, explanation sentence |
| PostgreSQL (e.g. Supabase) | App data + LangGraph checkpoints |
| Google Fonts | Frontend fonts |
| Vercel Web Analytics | Only when hosted on Vercel (404 elsewhere, harmless) |
| DNS | Signup email deliverability check (toggle above) |
