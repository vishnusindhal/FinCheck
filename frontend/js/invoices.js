/* ============================================================
   MY INVOICES — list, detail view, JSON + CSV download
   Depends on: authFetch (auth.js), showView (main.js),
               formatCurrency/formatDate/escapeHtml (utils.js)
   The "Compare Documents" button is wired in comparison.js.
   ============================================================ */

let currentInvoice = null; // invoice currently shown in the detail panel

/* ============================================================
   NAVIGATION
   ============================================================ */
document.getElementById("myInvoicesBtn").addEventListener("click", () => {
  showView("invoices");
  loadInvoiceList();
});

document.getElementById("backFromInvoicesBtn").addEventListener("click", () => {
  showView("upload");
});

document.getElementById("closeDetailBtn").addEventListener("click", () => {
  document.getElementById("invoiceDetailPanel").hidden = true;
  els.comparisonPanel.hidden = true;
  currentInvoice = null;
});

/* ============================================================
   LOAD + RENDER LIST
   ============================================================ */
async function loadInvoiceList() {
  const tbody = document.getElementById("invoiceTableBody");
  const table = document.getElementById("invoiceTable");
  const empty = document.getElementById("invoiceListEmpty");

  tbody.innerHTML = "";
  table.hidden = true;
  empty.hidden = true;
  document.getElementById("invoiceDetailPanel").hidden = true;

  try {
    const res = await authFetch("/api/invoices");
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
    const invoices = await res.json();

    if (!invoices.length) {
      empty.hidden = false;
      return;
    }

    invoices.forEach(inv => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${escapeHtml(inv.invoice_number || "—")}</td>
        <td>${escapeHtml(inv.vendor_name || "—")}</td>
        <td class="mono">${escapeHtml(formatDate(inv.invoice_date))}</td>
        <td class="mono">${escapeHtml(formatCurrency(inv.total_amount, inv.currency))}</td>
        <td class="mono">${escapeHtml(inv.currency || "—")}</td>
        <td><button class="btn-row-view">View</button></td>
      `;
      tr.querySelector(".btn-row-view").addEventListener("click", () => loadInvoiceDetail(inv.id));
      tbody.appendChild(tr);
    });
    table.hidden = false;
  } catch (err) {
    empty.hidden = false;
  }
}

/* ============================================================
   LOAD + RENDER DETAIL
   ============================================================ */
async function loadInvoiceDetail(invoiceId) {
  try {
    const res = await authFetch(`/api/invoices/${invoiceId}`);
    if (!res.ok) return;
    const inv = await res.json();
    currentInvoice = inv;
    els.comparisonPanel.hidden = true;
    renderInvoiceDetail(inv);
  } catch (err) {
    // ignore
  }
}

function renderInvoiceDetail(inv) {
  document.getElementById("detailInvoiceNumber").textContent = inv.invoice_number || "Invoice Detail";

  const fields = [
    { label: "Invoice Number", value: inv.invoice_number },
    { label: "Vendor Name", value: inv.vendor_name },
    { label: "Invoice Date", value: formatDate(inv.invoice_date) },
    { label: "PO Number", value: inv.po_number || "N/A" },
    { label: "Total Amount", value: formatCurrency(inv.total_amount, inv.currency) },
    { label: "Tax Amount", value: formatCurrency(inv.tax_amount, inv.currency) },
    { label: "Currency", value: inv.currency },
    { label: "Processed On", value: formatDate(inv.created_at) },
  ];

  const grid = document.getElementById("invoiceDetailGrid");
  grid.innerHTML = "";
  fields.forEach(f => {
    const div = document.createElement("div");
    div.className = "detail-field";
    div.innerHTML = `
      <div class="detail-field-label">${escapeHtml(f.label)}</div>
      <div class="detail-field-value">${escapeHtml(f.value || "—")}</div>
    `;
    grid.appendChild(div);
  });

  const tbody = document.getElementById("lineItemsBody");
  tbody.innerHTML = "";
  const lineItems = inv.line_items || [];

  if (!lineItems.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="color: var(--ink-faint); padding: 12px;">No line items recorded.</td></tr>`;
  } else {
    lineItems.forEach(item => {
      const amount = Number(item.quantity || 0) * Number(item.unit_price || 0);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(item.description || "—")}</td>
        <td class="mono">${escapeHtml(item.quantity ?? "—")}</td>
        <td class="mono">${escapeHtml(formatCurrency(item.unit_price, inv.currency))}</td>
        <td class="mono">${escapeHtml(formatCurrency(amount, inv.currency))}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  const compareBtn = document.getElementById("compareDocumentsBtn");
  compareBtn.disabled = !inv.po_number;
  compareBtn.title = inv.po_number ? "" : "No PO number on this invoice";

  const panel = document.getElementById("invoiceDetailPanel");
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ============================================================
   DOWNLOAD HELPERS
   ============================================================ */
document.getElementById("downloadJsonBtn").addEventListener("click", () => {
  if (!currentInvoice) return;
  const clean = buildCleanInvoice(currentInvoice);
  downloadFile(`invoice_${safeFileName(clean.invoice_number || currentInvoice.id)}.json`,
    JSON.stringify(clean, null, 2), "application/json");
});

document.getElementById("downloadCsvBtn").addEventListener("click", () => {
  if (!currentInvoice) return;
  const clean = buildCleanInvoice(currentInvoice);
  downloadFile(`invoice_${safeFileName(clean.invoice_number || currentInvoice.id)}.csv`,
    invoiceToCsv(clean), "text/csv");
});

function safeFileName(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]/g, "_");
}

function buildCleanInvoice(inv) {
  return {
    invoice_number: inv.invoice_number,
    vendor_name: inv.vendor_name,
    invoice_date: inv.invoice_date,
    po_number: inv.po_number,
    total_amount: inv.total_amount,
    tax_amount: inv.tax_amount,
    currency: inv.currency,
    line_items: (inv.line_items || []).map(item => ({
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
      amount: Number(item.quantity || 0) * Number(item.unit_price || 0),
    })),
    processed_at: inv.created_at,
  };
}

/* Quote a CSV cell; prefix formula-leading characters so spreadsheets don't execute them. */
function csvCell(value) {
  let s = (value ?? "").toString();
  if (/^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

function invoiceToCsv(inv) {
  const header = ["invoice_number", "vendor_name", "invoice_date", "po_number",
                  "total_amount", "tax_amount", "currency", "processed_at"];
  const lineHeader = ["description", "quantity", "unit_price", "amount"];
  return [
    "# Invoice Fields",
    header.join(","),
    header.map(k => csvCell(inv[k])).join(","),
    "",
    "# Line Items",
    lineHeader.join(","),
    ...(inv.line_items || []).map(item => lineHeader.map(k => csvCell(item[k])).join(",")),
  ].join("\n");
}

function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoking synchronously can cancel the download in Chromium; give it time to start.
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
