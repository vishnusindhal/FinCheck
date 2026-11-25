"""
FastAPI app exposing the LangGraph invoice pipeline, with per-user auth.

Public:
  GET  /, /api/health
  POST /api/auth/signup        — create account, returns JWT
  POST /api/auth/login         — OAuth2 form login, returns JWT
  GET  /ui/                    — the static frontend (when frontend/ exists)

Protected (Authorization: Bearer <token>):
  POST /api/process                    — upload invoice (+ optional PO/GR), SSE progress stream
  POST /api/runs/{run_id}/resume       — approve/reject a run paused for human review
  GET  /api/runs                       — this user's runs
  GET  /api/runs/{run_id}              — one run with its report
  GET  /api/runs/{run_id}/mismatches   — matching results of a run
  GET  /api/invoices                   — this user's invoices
  GET  /api/invoices/{invoice_id}      — invoice + line items + latest run id
  GET  /api/purchase_orders/{po_number}
  GET  /api/goods_receipts/{po_number}

Run from the project root:  python -m uvicorn backend.app.main:app --reload --port 8000
"""

import json
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from email_validator import validate_email, EmailNotValidError
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, EmailStr

from backend.app.agent import create_graph, nodes, paths
from backend.app import db
from backend.app.auth import hash_password, verify_password, create_access_token, get_current_user_id
from backend.app.auth_db import (
    init_auth_db, create_user, get_user_by_email, update_run_report,
    insert_pipeline_run, list_pipeline_runs, get_pipeline_run,
    VALID_DECISIONS, update_run_decision, claim_run_for_resume, release_run_claim,
    PENDING_STATUS,
)
from backend.app.helper import jsonable
from backend.app.report import generate_report, generate_stopped_report
from backend.app.schemas import MatchResult
from backend.app.anomaly_detection.predict import load_models, set_models
from backend.app.anomaly_detection.train import retrain_in_background

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fincheck")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def initialize_database():
    """Create/upgrade application tables (idempotent)."""
    db.init_db()
    init_auth_db()
    try:
        db.migrate_per_user_uniqueness()
    except Exception as exc:  # e.g. legacy data violating the new per-user index
        logger.warning("Per-user uniqueness migration failed (duplicates checks still run in code): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from langgraph.checkpoint.postgres import PostgresSaver

    if _env_flag("AUTO_INIT_DB", True):
        initialize_database()

    set_models(load_models())   # models already on disk, available immediately
    retrain_in_background()     # refresh from the DB without blocking startup

    with PostgresSaver.from_conn_string(os.getenv("DB_URL")) as checkpointer:
        checkpointer.setup()
        app.state.checkpointer = checkpointer
        app.state.pipeline = create_graph(nodes, paths, checkpointer=checkpointer)
        yield


app = FastAPI(title="FinCheck Invoice Automation", lifespan=lifespan)

# CORS: set CORS_ORIGINS to a comma-separated list (e.g. your Vercel URL) in production.
# Auth uses bearer headers, not cookies, so credentials are not needed for "*".
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# AUTH ROUTES
# ============================================================

class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.get("/")
def home():
    return {"status": "ok", "ui": "/ui/"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/signup", response_model=TokenResponse)
def signup(payload: SignupRequest):
    try:
        email = validate_email(
            payload.email,
            check_deliverability=_env_flag("EMAIL_CHECK_DELIVERABILITY", True),
        ).normalized.lower()
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be at most 72 bytes.")

    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user_id = create_user(email, hash_password(payload.password))
    return TokenResponse(access_token=create_access_token(user_id, email))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # OAuth2PasswordRequestForm uses 'username'; we treat it as the email address.
    user = get_user_by_email(form_data.username)
    if user is None or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return TokenResponse(access_token=create_access_token(user["id"], user["email"]))


# ============================================================
# PIPELINE
# ============================================================

# Human-readable labels for each node — shown in the live progress UI
NODE_LABELS = {
    "extract_Invoice": "Extracting invoice",
    "extract_PurchaseOrder": "Extracting purchase order",
    "extract_GoodReceipt": "Extracting goods receipt",
    "validation": "Validating extracted data",
    "duplicate_detect": "Checking for duplicates",
    "3_way_matching": "Matching invoice against PO/GR",
    "classify": "Classifying expense category",
    "anomaly_detect": "Detecting anomalies from history",
    "risk_analysis": "Assessing risk",
    "approval": "Routing for approval",
    "report_gen": "Generating report",
}


def save_upload(file: Optional[UploadFile], dest_dir: Path, slot: str) -> Optional[str]:
    """
    Save an uploaded PDF under a fixed server-chosen name (never the client's
    filename — prevents path traversal). Enforces size limit and PDF signature.
    """
    if file is None or not file.filename:
        return None
    dest_path = dest_dir / f"{slot}.pdf"
    size = 0
    with open(dest_path, "wb") as out:
        first = file.file.read(1024 * 1024)
        if not first.startswith(b"%PDF-"):
            raise ValueError(f"{slot}: file is not a PDF")
        chunk = first
        while chunk:
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise ValueError(f"{slot}: file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
            out.write(chunk)
            chunk = file.file.read(1024 * 1024)
    return str(dest_path)


def sse_event(event: str, data: dict) -> str:
    """Format a single Server-Sent Event message."""
    return f"event: {event}\ndata: {json.dumps(jsonable(data), default=str)}\n\n"


def _cleanup_failed_run(user_id: int, state: dict):
    """Delete rows a failed run inserted so a retry isn't flagged as a duplicate."""
    try:
        db.delete_documents(user_id, state.get("invoice_id"), state.get("po_db_id"), state.get("gr_db_id"))
    except Exception as exc:
        logger.warning("Cleanup after failed run did not complete: %s", exc)


def _provisional_report(state: dict, approval: dict) -> dict:
    """Report stored while a run awaits human review (so history/comparison can show it)."""
    return generate_report(
        invoice=state.get("invoice") or {},
        validation=(state.get("is_valid"), state.get("validation_errors")),
        match_result=MatchResult(**(state.get("match_result") or {"matched": False})),
        classification=state.get("classification"),
        risk=state.get("risk") or {},
        approval={**(approval or {}), "decision": "needs_review"},
        warnings=state.get("warnings") or [],
        anomaly=state.get("anomaly_result"),
    )


@app.post("/api/process")
def process_invoice(
    invoice: UploadFile = File(...),
    po: Optional[UploadFile] = File(None),
    gr: Optional[UploadFile] = File(None),
    user_id: int = Depends(get_current_user_id),
):
    run_key = str(uuid.uuid4())
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"invoice_{run_key}_"))
    try:
        invoice_path = save_upload(invoice, tmp_dir, "invoice")
        po_path = save_upload(po, tmp_dir, "po")
        gr_path = save_upload(gr, tmp_dir, "gr")
    except ValueError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to save uploaded files: {e}")

    if not invoice_path:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="An invoice PDF is required.")

    initial_state = {"invoice_path": invoice_path, "po_path": po_path, "gr_path": gr_path, "user_id": user_id}
    pipeline = app.state.pipeline

    # A plain (sync) generator: Starlette iterates it in a worker thread, so the
    # blocking LLM/DB work never stalls the event loop.
    def event_generator():
        final_state: dict = {}
        interrupted = False
        interrupt_value: dict = {}
        run_saved = False
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        try:
            for mode, chunk in pipeline.stream(initial_state, config=config, stream_mode=["updates", "tasks"]):
                if mode == "tasks":
                    if "input" in chunk:  # task-start event (finish events carry "result")
                        name = chunk.get("name")
                        yield sse_event("node_start", {"node": name, "label": NODE_LABELS.get(name, name)})
                    continue
                for node_name, state_delta in chunk.items():
                    if node_name == "__interrupt__":
                        interrupted = True
                        interrupt_value = (state_delta[0].value if state_delta else {}) or {}
                        continue
                    if not isinstance(state_delta, dict):
                        continue
                    final_state.update(state_delta)
                    yield sse_event("node_complete", {
                        "node": node_name,
                        "label": NODE_LABELS.get(node_name, node_name),
                        "state_delta": state_delta,
                    })

            status = final_state.get("status") or "processed"
            if interrupted:
                report = jsonable(_provisional_report(final_state, interrupt_value.get("approval")))
                run_id = insert_pipeline_run(user_id, final_state.get("invoice_id"), PENDING_STATUS, report, thread_id)
                run_saved = True
                yield sse_event("interrupted", {
                    "message": interrupt_value.get("message", "Pending human review"),
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "status": PENDING_STATUS,
                    "report": report,
                })
                return

            if status in ("rejected_invalid", "rejected_duplicate"):
                report = generate_stopped_report(final_state.get("invoice"), status, final_state.get("validation_errors"))
            else:
                report = jsonable(final_state.get("report"))

            run_id = insert_pipeline_run(user_id, final_state.get("invoice_id"), status, report, thread_id)
            run_saved = True
            yield sse_event("done", {"status": status, "report": report, "run_id": run_id, "thread_id": thread_id})
            if status == "processed":
                retrain_in_background()

        except GeneratorExit:  # client disconnected mid-run
            if not run_saved:
                _cleanup_failed_run(user_id, final_state)
            raise
        except Exception as e:
            logger.exception("Pipeline run failed")
            if not run_saved:
                _cleanup_failed_run(user_id, final_state)
            yield sse_event("error", {"message": str(e)})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/resume")
def resume_run(
    run_id: int,
    decision: str,
    note: str | None = None,
    thread_id: str | None = None,   # optional/legacy: the server looks up the run's own thread
    user_id: int = Depends(get_current_user_id),
):
    if decision not in VALID_DECISIONS:
        raise HTTPException(status_code=400, detail=f"decision must be one of {sorted(VALID_DECISIONS)}")

    run_thread = claim_run_for_resume(user_id, run_id)
    if run_thread is None:
        if get_pipeline_run(user_id, run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        raise HTTPException(status_code=409, detail="This run is not awaiting review.")

    if thread_id and thread_id != run_thread:
        release_run_claim(user_id, run_id)
        raise HTTPException(status_code=400, detail="thread_id does not match this run.")

    pipeline = app.state.pipeline
    config = {"configurable": {"thread_id": run_thread}}
    try:
        snapshot = pipeline.get_state(config)
        if "approval" not in (snapshot.next or ()):
            raise LookupError("No paused checkpoint found for this run.")

        final_state: dict = {}
        for step in pipeline.stream(Command(resume={"decision": decision, "note": note or ""}), config=config):
            for _node, state_delta in step.items():
                if isinstance(state_delta, dict):
                    final_state.update(state_delta)

        report = jsonable(final_state.get("report"))
        if not report:
            raise RuntimeError("Pipeline resumed but produced no report.")
        status = final_state.get("status") or "processed"

        update_run_report(run_id, user_id, report, status)
        update_run_decision(run_id, user_id, decision, note or "")
    except LookupError as e:
        release_run_claim(user_id, run_id)
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Resume failed for run %s", run_id)
        release_run_claim(user_id, run_id)
        raise HTTPException(status_code=500, detail=str(e))

    retrain_in_background()
    return {"run_id": run_id, "decision": decision, "report": report, "status": status}


# ============================================================
# READ ENDPOINTS (all user-scoped)
# ============================================================

@app.get("/api/runs")
def get_my_runs(user_id: int = Depends(get_current_user_id), limit: int = 50):
    return list_pipeline_runs(user_id, limit=max(1, min(limit, 200)))


@app.get("/api/runs/{run_id}")
def get_my_run(run_id: int, user_id: int = Depends(get_current_user_id)):
    """404 (not 403) for other users' runs so existence isn't leaked."""
    run = get_pipeline_run(user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@app.get("/api/runs/{run_id}/mismatches")
def get_mismatches(run_id: int, user_id: int = Depends(get_current_user_id)):
    run = get_pipeline_run(user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    matching = ((run.get("report") or {}).get("stages") or {}).get("matching")
    if matching is None:
        raise HTTPException(status_code=404, detail="This run has no matching results.")
    return matching


@app.get("/api/invoices")
def list_invoices(user_id: int = Depends(get_current_user_id), limit: int = 50):
    return jsonable(db.list_invoices(user_id, max(1, min(limit, 200))))


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user_id: int = Depends(get_current_user_id)):
    invoice = db.get_invoice(user_id, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return jsonable(invoice)


@app.get("/api/purchase_orders/{po_number}")
def get_purchase_order(po_number: str, user_id: int = Depends(get_current_user_id)):
    po = db.get_purchase_order(user_id, po_number)
    if po is None:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    return jsonable(po)


@app.get("/api/goods_receipts/{po_number}")
def get_goods_receipt(po_number: str, user_id: int = Depends(get_current_user_id)):
    gr = db.get_goods_receipt(user_id, po_number)
    if gr is None:
        raise HTTPException(status_code=404, detail="Goods receipt not found.")
    return jsonable(gr)


# Serve the frontend from the same origin (used by Docker / HF Spaces). Mounted last.
if FRONTEND_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")
