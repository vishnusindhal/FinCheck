/* ============================================================
   LEDGER HISTORY (sidebar) — backed by this user's pipeline_runs
   Three tabs: Pending / Approved / Declined
   Depends on: authFetch (auth.js), renderReport (report.js), escapeHtml (utils.js)
   ============================================================ */

let runHistory = []; // cached, unfiltered run list
let activeTab = "pending";

async function loadHistory() {
  try {
    const res = await authFetch("/api/runs");
    if (!res.ok) return;
    runHistory = await res.json();
    applyLedgerFilter();
    updateStats(runHistory);
  } catch (err) {
    // session expired or backend unreachable — authFetch already handled the redirect if needed
  }
}

/* ============================================================
   CATEGORIZATION — single source of truth for which bucket a run is in
   ============================================================ */
function categorize(run) {
  if (run.status === "rejected_invalid" || run.status === "rejected_duplicate") return "declined";
  if (run.human_decision === "rejected") return "declined";
  if (run.human_decision === "approved") return "approved";
  if (run.report?.stages?.approval?.decision === "auto_approved") return "approved";
  return "pending"; // needs_review, no human decision recorded yet
}

function provenanceLabel(run) {
  if (run.human_decision === "approved") return "Approved by you";
  if (run.human_decision === "rejected") return "Declined by you";
  if (run.report?.stages?.approval?.decision === "auto_approved") return "Auto-approved";
  if (run.status === "rejected_invalid") return "Stopped: failed validation";
  if (run.status === "rejected_duplicate") return "Stopped: duplicate invoice";
  return null;
}

function filterByTab(items, tab) {
  return items.filter(run => categorize(run) === tab);
}

function applyLedgerFilter() {
  const q = (els.searchInput.value || "").toLowerCase();
  const items = filterByTab(runHistory, activeTab).filter(run => {
    if (!q) return true;
    const report = run.report || {};
    return (report.vendor_name || "").toLowerCase().includes(q) ||
           (report.invoice_number || "").toLowerCase().includes(q);
  });
  renderLedgerList(items);
}

/* ============================================================
   TAB SWITCHING + SEARCH
   ============================================================ */
document.querySelectorAll(".ledger-tab").forEach(tabBtn => {
  tabBtn.addEventListener("click", () => {
    document.querySelectorAll(".ledger-tab").forEach(b => b.classList.remove("active"));
    tabBtn.classList.add("active");
    activeTab = tabBtn.dataset.tab;
    applyLedgerFilter();
  });
});

document.getElementById("searchInput").addEventListener("input", applyLedgerFilter);

/* ============================================================
   RENDERING
   ============================================================ */
function renderLedgerList(items) {
  els.ledgerEmpty.hidden = items.length > 0;
  els.ledgerList.querySelectorAll(".ledger-row").forEach(el => el.remove());

  items.forEach(run => {
    const report = run.report || {};
    const provenance = provenanceLabel(run);
    const row = document.createElement("button");
    row.className = "ledger-row";
    if (run.id === currentRunId) row.classList.add("active");
    row.innerHTML = `
      <div class="ledger-row-top">
        <span class="ledger-row-vendor">${escapeHtml(report.vendor_name || "Unknown vendor")}</span>
        <span class="ledger-row-amount">${escapeHtml(formatCurrency(report.total_amount, report.currency))}</span>
      </div>
      <div class="ledger-row-bottom">
        <span class="ledger-row-meta">${escapeHtml(report.invoice_number || "—")} · ${escapeHtml(formatTimestamp(run.created_at))}</span>
        <span class="tag ${tagClassForRun(run)}">${escapeHtml(tagLabelForRun(run))}</span>
      </div>
      ${provenance ? `<div class="ledger-row-provenance">${escapeHtml(provenance)}</div>` : ""}
    `;
    row.addEventListener("click", () => loadRunDetail(run.id, row));
    els.ledgerList.appendChild(row);
  });
}

function tagClassForRun(run) {
  const cat = categorize(run);
  if (cat === "approved") return "tag-approved";
  if (cat === "declined") return "tag-rejected";
  return "tag-review";
}

function tagLabelForRun(run) {
  if (run.status === "rejected_invalid") return "Invalid";
  if (run.status === "rejected_duplicate") return "Duplicate";
  const cat = categorize(run);
  if (cat === "approved") return "Approved";
  if (cat === "declined") return "Declined";
  return "Pending";
}

async function loadRunDetail(runId, rowEl) {
  document.querySelectorAll(".ledger-row").forEach(r => r.classList.remove("active"));
  if (rowEl) rowEl.classList.add("active");
  currentRunId = runId;

  try {
    const res = await authFetch(`/api/runs/${runId}`);
    if (!res.ok) return;
    const run = await res.json();
    renderReport(run.report, run.status, run);
  } catch (err) {
    // leave current view as-is
  }
}

function updateStats(items) {
  els.statTotal.textContent = items.length;
  els.statFlagged.textContent = filterByTab(items, "pending").length;
  els.statApproved.textContent = filterByTab(items, "approved").length;
}
