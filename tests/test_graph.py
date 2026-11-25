"""LangGraph pipeline routing tests with fake extraction + DB (MemorySaver checkpoints)."""

from langgraph.types import Command

from tests.conftest import make_invoice


def run(graph, state, thread="t1"):
    cfg = {"configurable": {"thread_id": thread}}
    result = graph.invoke(state, cfg)
    return result, cfg


FULL = {"invoice_path": "inv.pdf", "po_path": "po.pdf", "gr_path": "gr.pdf", "user_id": 7}


def test_matching_set_auto_approves(graph, fake_db, use_scenario):
    use_scenario("matching")
    result, cfg = run(graph, FULL)
    assert result["status"] == "processed"
    assert result["report"]["stages"]["approval"]["decision"] == "auto_approved"
    assert result["invoice_id"] is not None
    assert graph.get_state(cfg).next == ()


def test_new_vendor_signal_fires_despite_insert(graph, fake_db, use_scenario):
    use_scenario("matching")
    result, _ = run(graph, FULL)
    assert "New/unseen vendor" in result["risk"]["reasons"]


def test_mismatch_interrupts_then_resumes_with_human_decision(graph, fake_db, use_scenario):
    use_scenario("mismatch")
    result, cfg = run(graph, FULL)
    assert "report" not in result or result.get("report") is None
    assert graph.get_state(cfg).next == ("approval",)

    final = graph.invoke(Command(resume={"decision": "rejected", "note": "price too high"}), cfg)
    approval = final["report"]["stages"]["approval"]
    assert approval == {"decision": "rejected", "approver": "human_reviewer", "routed_to": "AP Manager",
                        "note": "price too high", "source": "human"}


def test_invoice_only_upload_does_not_crash(graph, fake_db, use_scenario):
    use_scenario("matching")
    result, cfg = run(graph, {"invoice_path": "inv.pdf", "po_path": None, "gr_path": None, "user_id": 7})
    # No PO/GR → matching can't run → routed for review instead of crashing
    assert result["match_result"]["issues"][0]["field"] == "po/gr"
    assert graph.get_state(cfg).next == ("approval",)
    assert fake_db.pos == {} and fake_db.grs == {}


def test_invalid_invoice_stops_early(graph, fake_db, monkeypatch):
    from backend.app import extracter
    monkeypatch.setattr(extracter, "extract_invoice", lambda p: make_invoice(total=-1))
    result, _ = run(graph, {"invoice_path": "inv.pdf", "user_id": 7})
    assert result["status"] == "rejected_invalid"
    assert fake_db.invoices == {}


def test_duplicate_is_per_user(graph, fake_db, use_scenario):
    use_scenario("matching")
    run(graph, FULL, "a")
    dup, _ = run(graph, FULL, "b")
    assert dup["status"] == "rejected_duplicate"
    other_user, _ = run(graph, {**FULL, "user_id": 8}, "c")
    assert other_user["status"] == "processed"


def test_duplicate_po_becomes_warning_not_reinserted(graph, fake_db, use_scenario, monkeypatch):
    use_scenario("matching")
    run(graph, FULL, "a")
    from backend.app import extracter
    monkeypatch.setattr(extracter, "extract_invoice", lambda p: make_invoice(number="FC-INV-1002"))
    second, _ = run(graph, FULL, "b")
    assert {"DuplicatePurchaseOrder"} <= {k for w in second["warnings"] for k in w}
    assert second["po_db_id"] is None
