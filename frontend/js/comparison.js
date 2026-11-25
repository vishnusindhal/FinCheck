/* ============================================================
   DOCUMENT COMPARISON — invoice vs purchase order vs goods receipt
   Depends on: authFetch (auth.js), currentInvoice (invoices.js),
               els (main.js), formatCurrency/formatDate/escapeHtml (utils.js)

   Mismatch highlighting uses the issue `field` formats produced by
   backend/app/matching.py (lower-cased here):
     gr:<desc> | gr:qty:<desc> | invoice:<desc> | invoice:price:<desc>
     invoice:price_low:<desc> | invoice:qty:<desc> | total_amount
   ============================================================ */

let comparisonState = { invoice: null, purchaseOrder: null, goodsReceipt: null, mismatches: null };

async function loadComparison(invoice) {
  comparisonState = { invoice, purchaseOrder: null, goodsReceipt: null, mismatches: null };
  const po = encodeURIComponent(invoice.po_number || "");

  const requests = [
    authFetch(`/api/purchase_orders/${po}`),
    authFetch(`/api/goods_receipts/${po}`),
    invoice.run_id ? authFetch(`/api/runs/${invoice.run_id}/mismatches`) : Promise.resolve(null),
  ];
  const [poRes, grRes, mismatchRes] = await Promise.allSettled(requests);
  const json = async (r) => (r.status === "fulfilled" && r.value && r.value.ok ? r.value.json() : null);

  comparisonState.purchaseOrder = await json(poRes);
  comparisonState.goodsReceipt = await json(grRes);
  comparisonState.mismatches = await json(mismatchRes);
}

function itemKey(item) {
  return (item?.description || "").toLowerCase().trim();
}

function toMap(items) {
  return Object.fromEntries((items || []).filter(i => i.description).map(i => [itemKey(i), i]));
}

function renderComparisonMessage(message) {
  document.getElementById("comparisonSummary").innerHTML =
    `<p class="comparison-message">${escapeHtml(message)}</p>`;
  document.getElementById("comparisonLineItems").innerHTML = "";
  els.comparisonPanel.hidden = false;
}

function renderComparison() {
  const { invoice, purchaseOrder: po, goodsReceipt: gr, mismatches } = comparisonState;

  if (!invoice) return;
  if (!po && !gr) {
    renderComparisonMessage("No purchase order or goods receipt was found for this invoice's PO number.");
    return;
  }

  const issueFields = new Set((mismatches?.issues || []).map(i => (i.field || "").toLowerCase()));
  const totalMismatch = issueFields.has("total_amount");
  const totalClass = totalMismatch ? "mismatch-cell" : "";
  const poTotal = (po?.line_items || []).reduce(
    (sum, item) => sum + Number(item.quantity || 0) * Number(item.unit_price || 0), 0);

  document.getElementById("comparisonSummary").innerHTML = `
    ${mismatches ? "" : `<p class="comparison-message">Matching results are not available for this invoice; showing documents only.</p>`}
    <table class="comparison-table">
      <thead>
        <tr><th>Field</th><th>Invoice</th><th>Purchase Order</th><th>Goods Receipt</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>Vendor</td>
          <td>${escapeHtml(invoice.vendor_name ?? "—")}</td>
          <td>${escapeHtml(po?.vendor_name ?? "—")}</td>
          <td>—</td>
        </tr>
        <tr>
          <td>PO Number</td>
          <td>${escapeHtml(invoice.po_number ?? "—")}</td>
          <td>${escapeHtml(po?.po_number ?? "—")}</td>
          <td>${escapeHtml(gr?.po_number ?? "—")}</td>
        </tr>
        <tr>
          <td>Currency</td>
          <td>${escapeHtml(invoice.currency ?? "—")}</td>
          <td>${escapeHtml(po?.currency ?? "—")}</td>
          <td>—</td>
        </tr>
        <tr>
          <td>Total Amount</td>
          <td class="${totalClass}">${totalMismatch ? "⚠ " : ""}${escapeHtml(formatCurrency(invoice.total_amount, invoice.currency))}</td>
          <td class="${totalClass}">${totalMismatch ? "⚠ " : ""}${po ? escapeHtml(formatCurrency(poTotal, po.currency)) : "—"}<span class="comparison-note">${po ? " (pre-tax)" : ""}</span></td>
          <td>—</td>
        </tr>
        <tr>
          <td>Invoice Date</td>
          <td>${escapeHtml(formatDate(invoice.invoice_date))}</td>
          <td>—</td>
          <td>—</td>
        </tr>
        <tr>
          <td>Received Date</td>
          <td>—</td>
          <td>—</td>
          <td>${escapeHtml(formatDate(gr?.received_date))}</td>
        </tr>
      </tbody>
    </table>
  `;

  renderLineItemComparison(issueFields);
  els.comparisonPanel.hidden = false;
  els.comparisonPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderLineItemComparison(issueFields) {
  const { invoice, purchaseOrder: po, goodsReceipt: gr } = comparisonState;
  const invoiceMap = toMap(invoice.line_items);
  const poMap = toMap(po?.line_items);
  const grMap = toMap(gr?.line_items);
  const descriptions = new Set([...Object.keys(invoiceMap), ...Object.keys(poMap), ...Object.keys(grMap)]);

  let rows = "";
  descriptions.forEach(desc => {
    const inv = invoiceMap[desc];
    const poItem = poMap[desc];
    const grItem = grMap[desc];

    const invQtyIssue = issueFields.has(`invoice:qty:${desc}`);
    const grQtyIssue = issueFields.has(`gr:qty:${desc}`);
    const priceIssue = issueFields.has(`invoice:price:${desc}`) || issueFields.has(`invoice:price_low:${desc}`);
    const notOrdered = issueFields.has(`invoice:${desc}`);
    const notReceived = issueFields.has(`gr:${desc}`);
    const anyIssue = invQtyIssue || grQtyIssue || priceIssue || notOrdered || notReceived;

    const cls = (flag) => (flag ? "mismatch-cell" : "");
    const status = notOrdered ? "⚠ Not on PO" : notReceived ? "⚠ Not received" : anyIssue ? "⚠ Mismatch" : "✅ Match";

    rows += `
      <tr>
        <td>${escapeHtml(inv?.description || poItem?.description || grItem?.description || desc)}</td>
        <td class="${cls(invQtyIssue)}">${escapeHtml(inv?.quantity ?? "—")}</td>
        <td class="${cls(grQtyIssue)}">${escapeHtml(poItem?.quantity ?? "—")}</td>
        <td class="${cls(invQtyIssue || grQtyIssue || notReceived)}">${escapeHtml(grItem?.quantity ?? "—")}</td>
        <td class="${cls(priceIssue)}">${priceIssue ? "⚠ " : ""}${escapeHtml(inv?.unit_price ?? "—")}</td>
        <td class="${cls(priceIssue)}">${priceIssue ? "⚠ " : ""}${escapeHtml(poItem?.unit_price ?? "—")}</td>
        <td>${status}</td>
      </tr>
    `;
  });

  document.getElementById("comparisonLineItems").innerHTML = `
    <h3>Line Item Comparison</h3>
    <table class="comparison-table">
      <thead>
        <tr>
          <th>Description</th><th>Invoice Qty</th><th>PO Qty</th><th>GR Qty</th>
          <th>Invoice Price</th><th>PO Price</th><th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/* ============================================================
   EVENTS (single handler — invoices.js no longer binds this button)
   ============================================================ */
document.getElementById("compareDocumentsBtn").addEventListener("click", async () => {
  if (!currentInvoice) return;
  if (!currentInvoice.po_number) {
    renderComparisonMessage("This invoice has no PO number, so there is nothing to compare against.");
    return;
  }
  try {
    await loadComparison(currentInvoice);
    renderComparison();
  } catch (err) {
    renderComparisonMessage(`Unable to load comparison data: ${err.message}`);
  }
});

document.getElementById("closeComparisonBtn").addEventListener("click", () => {
  els.comparisonPanel.hidden = true;
});
