"""FastAPI endpoint tests. The lifespan (real DB) is NOT run: TestClient is used
without a context manager and app.state.pipeline is set to a MemorySaver graph."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.auth import create_access_token

PDF = b"%PDF-1.4\n%fake test pdf\n"


class RunStore:
    def __init__(self):
        self.runs = {}

    def insert(self, user_id, invoice_id, status, report, thread_id=None):
        rid = len(self.runs) + 1
        self.runs[rid] = {"id": rid, "user_id": user_id, "invoice_id": invoice_id, "status": status,
                          "report": report, "thread_id": thread_id, "human_decision": None}
        return rid

    def get(self, user_id, run_id):
        r = self.runs.get(run_id)
        return dict(r, can_resume=r["status"] == "pending_review") if r and r["user_id"] == user_id else None

    def claim(self, user_id, run_id):
        r = self.runs.get(run_id)
        if r and r["user_id"] == user_id and r["status"] == "pending_review":
            r["status"] = "resuming"
            return r["thread_id"]
        return None

    def release(self, user_id, run_id):
        r = self.runs.get(run_id)
        if r and r["status"] == "resuming":
            r["status"] = "pending_review"

    def update_report(self, run_id, user_id, report, status):
        self.runs[run_id].update(report=report, status=status)

    def update_decision(self, run_id, user_id, decision, note=""):
        self.runs[run_id]["human_decision"] = decision
        return True


@pytest.fixture
def client(monkeypatch, graph, fake_db):
    store = RunStore()
    monkeypatch.setattr(main, "insert_pipeline_run", store.insert)
    monkeypatch.setattr(main, "get_pipeline_run", store.get)
    monkeypatch.setattr(main, "claim_run_for_resume", store.claim)
    monkeypatch.setattr(main, "release_run_claim", store.release)
    monkeypatch.setattr(main, "update_run_report", store.update_report)
    monkeypatch.setattr(main, "update_run_decision", store.update_decision)
    monkeypatch.setattr(main, "retrain_in_background", lambda: None)
    main.app.state.pipeline = graph
    c = TestClient(main.app)
    c.store = store
    c.fake_db = fake_db
    return c


def auth(user_id=1):
    return {"Authorization": f"Bearer {create_access_token(user_id, 'u@example.com')}"}


def events(body: str):
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def upload(client, user=1, with_docs=True, invoice=PDF):
    files = {"invoice": ("my invoice.pdf", invoice, "application/pdf")}
    if with_docs:
        files["po"] = ("po.pdf", PDF, "application/pdf")
        files["gr"] = ("gr.pdf", PDF, "application/pdf")
    return client.post("/api/process", files=files, headers=auth(user))


def test_process_matching_streams_real_starts_and_done(client, use_scenario):
    use_scenario("matching")
    res = upload(client)
    assert res.status_code == 200
    evs = events(res.text)
    names = [e for e, _ in evs]
    assert names[0] == "node_start" and names[-1] == "done"
    # a node's start arrives before its completion
    assert names.index("node_start") < names.index("node_complete")
    done = evs[-1][1]
    assert done["status"] == "processed"
    run = client.store.runs[done["run_id"]]
    assert run["invoice_id"] is not None          # B1: invoice id is now stored on the run
    assert done["report"]["stages"]["approval"]["decision"] == "auto_approved"


def test_interrupt_stores_provisional_report_and_resume_works_without_thread_id(client, use_scenario):
    use_scenario("mismatch")
    evs = events(upload(client).text)
    kind, data = evs[-1]
    assert kind == "interrupted"
    run = client.store.runs[data["run_id"]]
    assert run["status"] == "pending_review"
    assert run["report"]["stages"]["matching"]["matched"] is False   # mismatches endpoint works for pending runs

    mm = client.get(f"/api/runs/{data['run_id']}/mismatches", headers=auth())
    assert mm.status_code == 200 and mm.json()["issues"]

    res = client.post(f"/api/runs/{data['run_id']}/resume?decision=approved", headers=auth())
    assert res.status_code == 200, res.text
    assert res.json()["report"]["stages"]["approval"]["decision"] == "approved"
    assert client.store.runs[data["run_id"]]["human_decision"] == "approved"

    again = client.post(f"/api/runs/{data['run_id']}/resume?decision=approved", headers=auth())
    assert again.status_code == 409                         # no double resume


def test_resume_other_users_run_is_404(client, use_scenario):
    use_scenario("mismatch")
    run_id = events(upload(client, user=1).text)[-1][1]["run_id"]
    res = client.post(f"/api/runs/{run_id}/resume?decision=approved", headers=auth(2))
    assert res.status_code == 404
    assert client.store.runs[run_id]["status"] == "pending_review"


def test_invoice_only_upload_pauses_for_review(client, use_scenario):
    use_scenario("matching")
    kind, _ = events(upload(client, with_docs=False).text)[-1]
    assert kind == "interrupted"


def test_duplicate_run_gets_stopped_report(client, use_scenario):
    use_scenario("matching")
    upload(client)
    kind, data = events(upload(client).text)[-1]
    assert kind == "done" and data["status"] == "rejected_duplicate"
    assert data["report"]["outcome"] == "rejected_duplicate"


def test_failed_run_cleans_up_inserted_rows(client, use_scenario, monkeypatch):
    use_scenario("matching")
    from backend.app import agent

    def boom(*a, **k):
        raise RuntimeError("classifier exploded")
    monkeypatch.setattr(agent, "classify_invoice", boom)
    kind, data = events(upload(client).text)[-1]
    assert kind == "error" and "exploded" in data["message"]
    assert client.fake_db.invoices == {} and client.fake_db.deleted


def test_non_pdf_upload_rejected(client):
    res = upload(client, invoice=b"<html>not a pdf</html>")
    assert res.status_code == 400 and "not a PDF" in res.json()["detail"]


def test_upload_filename_never_used_as_path():
    from pathlib import Path
    import tempfile
    from fastapi import UploadFile
    import io
    tmp = Path(tempfile.mkdtemp())
    path = main.save_upload(UploadFile(file=io.BytesIO(PDF), filename="../../evil.pdf"), tmp, "invoice")
    assert Path(path).parent == tmp and Path(path).name == "invoice.pdf"


@pytest.mark.parametrize("url", ["/api/purchase_orders/PO-1", "/api/goods_receipts/PO-1", "/api/invoices", "/api/runs"])
def test_data_endpoints_require_auth(client, url):
    assert client.get(url).status_code == 401
