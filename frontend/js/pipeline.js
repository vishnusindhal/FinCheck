/* ============================================================
   PIPELINE — upload form, SSE stream consumption, live stage list
   Depends on: authFetch (auth.js), showView/els (main.js),
               renderReport/showPipelineDecision (report.js)
   ============================================================ */

const EXTRACTION_NODES = ["extract_Invoice", "extract_PurchaseOrder", "extract_GoodReceipt"];
const NODE_SEQUENCE = [
  { key: "extraction", label: "Extracting document fields" },
  { key: "validation", label: "Validating extracted data" },
  { key: "duplicate_detect", label: "Checking for duplicates" },
  { key: "3_way_matching", label: "Matching invoice against PO/GR" },
  { key: "classify", label: "Classifying expense category" },
  { key: "anomaly_detect", label: "Detecting anomalies from history" },
  { key: "risk_analysis", label: "Assessing risk" },
  { key: "approval", label: "Routing for approval" },
  { key: "report_gen", label: "Generating report" },
];

// Per-run extraction bookkeeping (reset on every submit)
let extractionExpected = 1;
let extractionCompleted = 0;
let extractionSummary = "";

/* ============================================================
   DROPZONE FILE LABELS
   ============================================================ */
document.querySelectorAll(".dropzone input[type=file]").forEach(input => {
  input.addEventListener("change", () => {
    const dz = input.closest(".dropzone");
    const nameEl = dz.querySelector(".dz-filename");
    if (input.files.length) {
      dz.classList.add("filled");
      nameEl.textContent = input.files[0].name;
    } else {
      dz.classList.remove("filled");
      nameEl.textContent = "";
    }
  });
});

/* ============================================================
   UPLOAD + STREAM PIPELINE
   ============================================================ */
els.uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const invoiceFile = document.getElementById("invoiceFile").files[0];
  const poFile = document.getElementById("poFile").files[0];
  const grFile = document.getElementById("grFile").files[0];

  if (!invoiceFile) {
    els.formNote.textContent = "An invoice file is required.";
    return;
  }

  els.formNote.textContent = "";
  els.submitBtn.disabled = true;
  els.submitBtn.textContent = "Starting…";

  const formData = new FormData();
  formData.append("invoice", invoiceFile);
  if (poFile) formData.append("po", poFile);
  if (grFile) formData.append("gr", grFile);

  extractionExpected = 1 + (poFile ? 1 : 0) + (grFile ? 1 : 0);
  extractionCompleted = 0;
  extractionSummary = "";

  resetPipelineView(`Processing ${invoiceFile.name}`);
  showView("pipeline");

  try {
    const response = await authFetch("/api/process", { method: "POST", body: formData });
    if (!response.ok || !response.body) {
      let detail = `Server responded ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    await consumeStream(response.body);
  } catch (err) {
    markPipelineError(err.message);
  } finally {
    els.submitBtn.disabled = false;
    els.submitBtn.textContent = "Run pipeline";
  }
});

function resetPipelineView(title) {
  els.pipelineTitle.textContent = title;
  els.pipelineSub.textContent = "Each stage runs in sequence — watch the ledger stamp as it goes.";
  els.pipelineError.hidden = true;
  els.pipelineError.textContent = "";
  hidePipelineDecision();
  buildStageList();
}

function buildStageList() {
  els.stageList.innerHTML = "";
  NODE_SEQUENCE.forEach((node, i) => {
    const row = document.createElement("div");
    row.className = "stage-row";
    row.id = `stage-${node.key}`;
    row.innerHTML = `
      <div class="stage-row-main">
        <span class="stage-num">${String(i + 1).padStart(2, "0")}</span>
        <span class="stage-stamp">✓</span>
        <span class="stage-body">
          <span class="stage-label">${escapeHtml(node.label)}</span>
          <span class="stage-detail"></span>
        </span>
      </div>
      <div class="stage-logs" hidden></div>
    `;
    els.stageList.appendChild(row);
  });
}

function markPipelineError(message) {
  els.pipelineTitle.textContent = "Pipeline stopped";
  els.pipelineError.textContent = message;
  els.pipelineError.hidden = false;
  document.querySelectorAll(".stage-row.active").forEach(r => r.classList.remove("active"));
}

/* Parses a fetch ReadableStream as Server-Sent Events and dispatches each. */
async function consumeStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (raw) => {
    if (!raw.trim()) return;
    const eventMatch = raw.match(/^event: (.+)$/m);
    const dataLines = raw.split("\n").filter(l => l.startsWith("data: ")).map(l => l.slice(6));
    if (!eventMatch || !dataLines.length) return;
    handleStreamEvent(eventMatch[1].trim(), JSON.parse(dataLines.join("\n")));
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop(); // last chunk may be incomplete — keep for next read
    events.forEach(dispatch);
  }
  buffer += decoder.decode();
  dispatch(buffer);
}

function handleStreamEvent(eventName, data) {
  // The fan-out extraction nodes share the single "extraction" UI row
  if (EXTRACTION_NODES.includes(data.node)) {
    const row = document.getElementById("stage-extraction");
    if (!row) return;
    if (eventName === "node_start") row.classList.add("active");
    if (eventName === "node_complete") {
      extractionCompleted++;
      if (data.node === "extract_Invoice" && data.state_delta?.invoice) {
        const inv = data.state_delta.invoice;
        extractionSummary = `${inv.invoice_number || "unknown"} — ${inv.vendor_name || "unknown vendor"}`;
      }
      if (extractionCompleted >= extractionExpected) {
        row.classList.remove("active");
        row.classList.add("complete");
        const docs = extractionExpected === 3 ? "invoice, PO and GR" : extractionExpected === 2 ? "2 documents" : "invoice";
        row.querySelector(".stage-detail").textContent = extractionSummary || `${docs} extracted`;
      }
    }
    return;
  }

  if (eventName === "node_start") {
    const row = document.getElementById(`stage-${data.node}`);
    if (row) row.classList.add("active");
    return;
  }

  if (eventName === "node_complete") {
    const row = document.getElementById(`stage-${data.node}`);
    if (!row) return;
    row.classList.remove("active");
    row.classList.add("complete");

    const detail = row.querySelector(".stage-detail");
    const summary = summarizeStageDelta(data.node, data.state_delta);
    if (summary.flagged) {
      row.classList.add("flagged");
      detail.classList.add("flagged-text");
    }
    detail.textContent = summary.text;

    const logs = extractStageLogs(data.node, data.state_delta);
    if (logs.length) attachStageLogs(row, logs);
    return;
  }

  if (eventName === "interrupted") {
    currentRunId = data.run_id;
    currentThreadId = data.thread_id;

    const approvalRow = document.getElementById("stage-approval");
    if (approvalRow) {
      approvalRow.classList.remove("active");
      approvalRow.classList.add("interrupted");
      approvalRow.querySelector(".stage-detail").textContent = "waiting for your decision";
    }
    els.pipelineTitle.textContent = "Review required";
    els.pipelineSub.textContent = "The pipeline has paused for human review. Approve or reject to continue.";
    showPipelineDecision(data.run_id);
    loadHistory(); // the pending run now appears in the sidebar
    return;
  }

  if (eventName === "done") {
    currentRunId = data.run_id;
    currentThreadId = data.thread_id;
    setTimeout(() => renderReport(data.report, data.status, { id: data.run_id, status: data.status }), 500);
    return;
  }

  if (eventName === "error") {
    markPipelineError(`Error: ${data.message}`);
  }
}

function extractStageLogs(node, delta) {
  if (!delta) return [];
  if (node === "anomaly_detect") return delta.anomaly_result?.logs || [];
  if (node === "risk_analysis") return delta.risk?.reasons || [];
  if (node === "3_way_matching") {
    return (delta.match_result?.issues || []).map(
      i => `${i.field}: expected ${i.expected}, got ${i.actual} [${i.severity}]`
    );
  }
  if (node === "validation") return delta.validation_errors || [];
  if (node === "duplicate_detect") {
    return (delta.warnings || []).flatMap(w => Object.entries(w).map(([k, v]) => `${k}: ${v}`));
  }
  return [];
}

function attachStageLogs(row, logs) {
  const logsDiv = row.querySelector(".stage-logs");
  if (!logsDiv) return;
  logsDiv.innerHTML = "";
  logs.forEach(log => {
    const p = document.createElement("p");
    p.className = "stage-log-line";
    p.textContent = log;
    logsDiv.appendChild(p);
  });
  logsDiv.hidden = false;
  row.classList.add("has-logs");
  row.querySelector(".stage-row-main").onclick = () => {
    logsDiv.hidden = !logsDiv.hidden;
    row.classList.toggle("logs-open", !logsDiv.hidden);
  };
}

/* One-line human summary for each node's result, shown under the stage label. */
function summarizeStageDelta(node, delta) {
  if (!delta) return { text: "", flagged: false };

  switch (node) {
    case "validation":
      return delta.is_valid
        ? { text: "all required fields present", flagged: false }
        : { text: `${(delta.validation_errors || []).length} issue(s) found`, flagged: true };
    case "duplicate_detect":
      if (delta.is_duplicate) return { text: "already exists in the ledger", flagged: true };
      return (delta.warnings || []).length
        ? { text: `no prior invoice · ${delta.warnings.length} warning(s)`, flagged: false }
        : { text: "no prior record found", flagged: false };
    case "3_way_matching":
      return delta.match_result?.matched
        ? { text: "invoice reconciles with PO/GR", flagged: false }
        : { text: `${(delta.match_result?.issues || []).length} mismatch(es)`, flagged: true };
    case "classify":
      return { text: delta.classification?.primary_category || "uncategorized", flagged: false };
    case "anomaly_detect": {
      const a = delta.anomaly_result || {};
      if (a.model_used === "none") return { text: "skipped — no model trained yet", flagged: false };
      return a.is_anomaly ? { text: "unusual for this vendor", flagged: true } : { text: "looks normal", flagged: false };
    }
    case "risk_analysis":
      return { text: `${delta.risk?.tier || "—"} risk (score ${delta.risk?.score ?? "—"})`, flagged: delta.risk?.tier === "high" };
    case "approval": {
      const d = delta.approval?.decision;
      if (d === "auto_approved") return { text: "auto-approved", flagged: false };
      if (d === "approved") return { text: "approved by reviewer", flagged: false };
      if (d === "rejected") return { text: "rejected by reviewer", flagged: true };
      return { text: `routed to ${delta.approval?.approver || "review"}`, flagged: true };
    }
    case "report_gen":
      return { text: "report compiled", flagged: false };
    default:
      return { text: "", flagged: false };
  }
}
