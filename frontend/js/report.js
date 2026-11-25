/* ============================================================
   REPORT VIEW — renders a pipeline run, plus human review
   (Approve / Reject) for runs paused at the approval stage.
   Depends on: authFetch (auth.js), showView/els (main.js), loadHistory (history.js)
   ============================================================ */

let currentRunId = null;     // run currently shown / being reviewed
let currentThreadId = null;  // informational only — the server resolves a run's thread itself

const STOP_LABELS = {
  rejected_invalid: "Rejected — invalid invoice",
  rejected_duplicate: "Rejected — duplicate invoice",
};

/* run: optional {id, status, human_decision, reviewer_note, can_resume} */
function renderReport(report, status, run = null) {
  if (!report) {
    els.pipelineTitle.textContent = `Stopped — ${status || "unknown reason"}`;
    showView("pipeline");
    return;
  }
  if (run?.id) currentRunId = run.id;
  const stages = report.stages || {};
  const runStatus = run?.status || status;

  document.getElementById("reportVendor").textContent = report.vendor_name || "Unknown vendor";
  document.getElementById("reportMeta").textContent =
    `Invoice ${report.invoice_number || "—"} · processed ${formatTimestamp(report.generated_at)}`;

  // Headline decision
  const decisionEl = document.getElementById("reportDecision");
  const headline = headlineDecision(report, runStatus);
  decisionEl.textContent = headline.text;
  decisionEl.className = `report-decision ${headline.cls}`;

  document.getElementById("reportAmount").textContent = formatCurrency(report.total_amount, report.currency);
  document.getElementById("reportAmountSub").textContent = report.invoice_number || "—";

  const v = stages.validation;
  if (v) {
    setStatus("reportValidation", v.passed ? "Passed" : "Failed", v.passed ? "ok" : "flagged");
    fillList("reportValidationErrors", v.errors || []);
  } else {
    setStatus("reportValidation", "Not run", "warn");
    fillList("reportValidationErrors", []);
  }

  const m = stages.matching;
  if (m) {
    setStatus("reportMatching", m.matched ? "Reconciled" : "Discrepancy found", m.matched ? "ok" : "flagged");
    fillList("reportMatchingIssues", (m.issues || []).map(i => `${i.field}: expected ${i.expected}, got ${i.actual}`));
  } else {
    setStatus("reportMatching", "Not run", "warn");
    fillList("reportMatchingIssues", []);
  }

  const c = stages.classification;
  setStatus("reportClassification", c ? (c.primary_category || "Uncategorized") : "Not run", c ? "ok" : "warn");
  const tagsEl = document.getElementById("reportClassBreakdown");
  tagsEl.innerHTML = "";
  Object.entries(c?.category_breakdown || {}).forEach(([cat, count]) => {
    const tag = document.createElement("span");
    tag.className = "tag-cat";
    tag.textContent = `${cat} × ${count}`;
    tagsEl.appendChild(tag);
  });

  const r = stages.risk;
  if (r) {
    setStatus("reportRisk", `${capitalize(r.tier || "—")} (score ${r.score ?? "—"})`,
      r.tier === "high" ? "flagged" : r.tier === "medium" ? "warn" : "ok");
    fillList("reportRiskReasons", r.reasons || []);
  } else {
    setStatus("reportRisk", "Not run", "warn");
    fillList("reportRiskReasons", []);
  }

  const explanationSection = document.getElementById("reportExplanationSection");
  explanationSection.hidden = !report.explanation;
  document.getElementById("reportExplanation").textContent = report.explanation || "";

  const a = stages.approval;
  if (a) {
    const label = {
      auto_approved: ["Auto-approved", "ok"],
      approved: [`Approved by reviewer${a.note ? ` — “${a.note}”` : ""}`, "ok"],
      rejected: [`Rejected by reviewer${a.note ? ` — “${a.note}”` : ""}`, "flagged"],
    }[a.decision] || [`Sent to ${a.approver || a.routed_to || "review"}`, "warn"];
    setStatus("reportApproval", label[0], label[1]);
  } else {
    setStatus("reportApproval", "Not run", "warn");
  }

  setupReportDecision(run, runStatus);
  showView("report");
}

function headlineDecision(report, runStatus) {
  if (STOP_LABELS[report.outcome]) return { text: STOP_LABELS[report.outcome], cls: "rejected" };
  if (STOP_LABELS[runStatus]) return { text: STOP_LABELS[runStatus], cls: "rejected" };
  const a = report.stages?.approval || {};
  if (a.decision === "auto_approved") return { text: "Auto-approved", cls: "approved" };
  if (a.decision === "approved") return { text: "Approved by reviewer", cls: "approved" };
  if (a.decision === "rejected") return { text: "Rejected by reviewer", cls: "rejected" };
  return { text: `Needs review — ${a.approver || a.routed_to || "AP team"}`, cls: "review" };
}

function setStatus(id, text, cls) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = `report-status ${cls}`;
}

function fillList(id, items) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.style.color = "var(--ink-faint)";
    li.textContent = "None";
    el.appendChild(li);
    return;
  }
  items.forEach(item => {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  });
}

/* ============================================================
   HUMAN REVIEW
   Two decision panels share one submit routine:
     • pipeline view  (#decisionActions)        — right after a live run pauses
     • report view    (#reportDecisionActions)  — for pending runs opened from history
   ============================================================ */
const decisionPanels = {
  pipeline: {
    actions: () => document.getElementById("decisionActions"),
    note: () => document.getElementById("reviewerNote"),
    result: () => document.getElementById("decisionResult"),
    approve: () => document.getElementById("approveBtn"),
    reject: () => document.getElementById("rejectBtn"),
  },
  report: {
    actions: () => document.getElementById("reportDecisionActions"),
    note: () => document.getElementById("reportReviewerNote"),
    result: () => document.getElementById("reportDecisionResult"),
    approve: () => document.getElementById("reportApproveBtn"),
    reject: () => document.getElementById("reportRejectBtn"),
  },
};

function bindDecisionPanel(panelName, runId) {
  const p = decisionPanels[panelName];
  p.note().value = "";
  p.result().textContent = "";
  p.actions().hidden = false;
  p.approve().disabled = false;
  p.reject().disabled = false;
  p.approve().onclick = () => submitDecision(runId, "approved", panelName);
  p.reject().onclick = () => submitDecision(runId, "rejected", panelName);
}

function hideDecisionPanel(panelName) {
  const p = decisionPanels[panelName];
  p.actions().hidden = true;
  p.result().textContent = "";
}

function showPipelineDecision(runId) { bindDecisionPanel("pipeline", runId); }
function hidePipelineDecision() { hideDecisionPanel("pipeline"); }

function setupReportDecision(run, runStatus) {
  const pending = run?.id && (run.can_resume || runStatus === "pending_review");
  if (pending) bindDecisionPanel("report", run.id);
  else hideDecisionPanel("report");
}

async function submitDecision(runId, decision, panelName) {
  const p = decisionPanels[panelName];
  if (!runId) {
    p.result().textContent = "Error: no run selected.";
    return;
  }
  const note = p.note().value.trim();
  p.approve().disabled = true;
  p.reject().disabled = true;
  p.result().textContent = "Submitting decision…";

  try {
    const params = new URLSearchParams({ decision });
    if (note) params.set("note", note);
    const res = await authFetch(`/api/runs/${runId}/resume?${params.toString()}`, { method: "POST" });
    if (!res.ok) {
      let detail = "Could not resume pipeline.";
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    const data = await res.json();
    hideDecisionPanel(panelName);
    currentRunId = data.run_id;
    renderReport(data.report, data.status, { id: data.run_id, status: data.status, human_decision: decision });
    loadHistory();
  } catch (err) {
    p.result().textContent = `Error: ${err.message}`;
    p.approve().disabled = false;
    p.reject().disabled = false;
  }
}
