/* ============================================================
   MAIN — shared element references, view switching, app init.
   Loaded after auth.js; its `els` object is used by pipeline.js,
   report.js and history.js.
   ============================================================ */

const els = {
  viewUpload: document.getElementById("viewUpload"),
  viewPipeline: document.getElementById("viewPipeline"),
  viewReport: document.getElementById("viewReport"),
  viewInvoices: document.getElementById("viewInvoices"),
  comparisonPanel: document.getElementById("comparisonPanel"),
  uploadForm: document.getElementById("uploadForm"),
  submitBtn: document.getElementById("submitBtn"),
  formNote: document.getElementById("formNote"),
  stageList: document.getElementById("stageList"),
  pipelineTitle: document.getElementById("pipelineTitle"),
  pipelineSub: document.getElementById("pipelineSub"),
  pipelineError: document.getElementById("pipelineError"),
  ledgerList: document.getElementById("ledgerList"),
  ledgerEmpty: document.getElementById("ledgerEmpty"),
  statTotal: document.getElementById("statTotal"),
  statFlagged: document.getElementById("statFlagged"),
  statApproved: document.getElementById("statApproved"),
  newInvoiceBtn: document.getElementById("newInvoiceBtn"),
  backToUploadBtn: document.getElementById("backToUploadBtn"),
  searchInput: document.getElementById("searchInput"),
};

/* ============================================================
   VIEW SWITCHING
   The comparison panel belongs to the invoices view and is closed
   whenever the user navigates anywhere.
   ============================================================ */
function showView(name) {
  els.viewUpload.hidden = name !== "upload";
  els.viewPipeline.hidden = name !== "pipeline";
  els.viewReport.hidden = name !== "report";
  els.viewInvoices.hidden = name !== "invoices";
  els.comparisonPanel.hidden = true;
}

function resetUploadForm() {
  els.uploadForm.reset();
  document.querySelectorAll(".dropzone").forEach(dz => {
    dz.classList.remove("filled");
    dz.querySelector(".dz-filename").textContent = "";
  });
  els.formNote.textContent = "";
}

els.newInvoiceBtn.addEventListener("click", () => {
  resetUploadForm();
  showView("upload");
});

els.backToUploadBtn.addEventListener("click", () => {
  resetUploadForm();
  showView("upload");
});

/* ============================================================
   INIT — deferred until every script has executed, because
   enterApp() → loadHistory() touches globals defined in later
   files (e.g. currentRunId in report.js).
   ============================================================ */
document.addEventListener("DOMContentLoaded", () => {
  if (getToken()) {
    enterApp();
  } else {
    showAuthScreen();
  }
});
