# FinCheck: Project and Real-World Use Guide

FinCheck is an accounts payable (AP) invoice-review prototype. It helps a business inspect a supplier invoice against the documents that support it, identify possible discrepancies, and record an approval decision. Its purpose is to help a person decide whether an invoice is ready to move forward for payment; FinCheck does not itself send money or integrate with a bank or accounting system.

This guide explains the business problem, the people and companies that could use FinCheck, the workflow represented in the code, and the practical limitations to consider before using it with real company data.

## 1. The business problem

Businesses buy goods and services from suppliers. After an order is placed and fulfilled, the supplier sends an invoice asking to be paid. The accounts payable team checks that the invoice is correct and authorized before arranging payment.

This can take time when information is spread across email, PDF documents, purchasing records, and warehouse records. A reviewer may need to answer questions such as:

- Did our company place this order?
- Did we receive the goods or services being invoiced?
- Is the supplier charging the agreed price and quantity?
- Has the invoice already been submitted?
- Is there anything unusual that needs a manager's attention?

FinCheck brings several of these checks into one review workflow. It extracts information from uploaded PDFs, runs checks, and presents results for the reviewer. Automated extraction and risk signals can be wrong, so a person remains responsible for reviewing exceptions and making business decisions.

## 2. The three important documents

| Document | Who normally creates it | What it represents |
|---|---|---|
| Purchase order (PO) | The buying company | What the company agreed to buy, including quantities and prices. |
| Goods receipt (GR) | The buying company's receiving team | What was recorded as received and when. |
| Invoice | The supplier | What the supplier is asking the company to pay. |

For example, a company orders two printers at USD 100 each. The purchase order records the agreement; the goods receipt records whether two printers arrived; and the invoice requests payment for those printers plus any applicable tax.

**Three-way matching** means comparing these three documents. A price or quantity difference may be a simple mistake or may need investigation. It is a signal to review, not proof of fraud.

## 3. What FinCheck is designed to do

The application combines a browser interface, a Python backend, a PostgreSQL database, a Gemini document model, and a LangGraph workflow. The code implements the following intended stages:

1. **Upload:** The user supplies an invoice PDF and can provide a purchase order and goods receipt PDF. Supplying all three provides the data needed for full three-way matching. Although the interface labels supporting documents optional, the current processing code has limitations for missing documents, so use all three when evaluating the prototype.
2. **Document extraction:** Gemini reads the PDFs and returns structured information such as invoice number, supplier, date, currency, total, and line items. The three document extraction steps are dispatched in parallel when the documents are present.
3. **Validation:** The invoice is checked for required fields, valid dates and currency, and acceptable amounts. Invalid invoices can stop the workflow early.
4. **Duplicate checks:** Existing invoice records are checked by supplier and invoice number. Existing PO and goods receipt records can also produce warnings. A duplicate invoice can stop processing.
5. **Three-way matching:** The application compares item descriptions, quantities, prices, and invoice subtotal against the supplied PO and goods receipt. Critical discrepancies are included in the matching result.
6. **Expense classification:** Simple keyword rules categorize invoice line items, for example as software, travel, or office supplies. Items that do not match a rule are uncategorized.
7. **Anomaly detection:** An Isolation Forest model may flag unusual invoices when models are available. The code chooses a vendor-specific model, a global model, or skips this step when no model is available; it is not a guarantee of fraud detection.
8. **Risk assessment:** The application combines signals such as matching issues, extraction confidence, vendor history, anomaly results, and past reviewer decisions into a score and reasons.
9. **Approval and report:** The workflow can automatically approve a qualifying invoice or pause for a human review decision. A report is then intended to summarize the validation, matching, classification, risk, and approval results.

The frontend also includes run history, invoice details, JSON and CSV export, and a document comparison screen. These features are part of the prototype and should be checked end to end before relying on them; they are not a replacement for an enterprise accounting system.

## 4. A realistic example

Imagine a fictional company, Greenfield Office Services, buys printers for a new office:

1. The purchasing team issues a PO for **four printers at USD 100 each**.
2. The receiving team records that **three printers arrived**.
3. The supplier sends an invoice for **four printers at USD 120 each**, plus tax.
4. An AP analyst uploads the invoice, PO, and goods receipt to FinCheck.
5. If extraction succeeds, FinCheck should highlight that the invoice price exceeds the PO price, that the invoice quantity exceeds the received quantity, and that the received quantity differs from the PO.
6. The analyst reviews the original documents and contacts purchasing, the receiving team, or the supplier to understand the difference.
7. Depending on company policy and the outcome of that investigation, a reviewer may approve or reject the invoice in the application. Payment, if appropriate, is arranged separately through the company's existing process.

There are several legitimate explanations: one printer may be on back order, a receipt may not have been recorded, or the supplier may have billed an incorrect price. FinCheck can surface the difference; it cannot determine the correct business resolution by itself.

### A matching example

If the PO says two printers at USD 100 each, the goods receipt shows two received, and the invoice lists those same items and prices with USD 20 tax, the invoice total is USD 220. Assuming accurate extraction, the three-way comparison should not find a critical item discrepancy. Approval still depends on the application's risk and routing rules and on the company's policy.

## 5. Who could use this kind of system?

Any organization that receives supplier invoices and uses purchase orders and receiving records may find this kind of workflow useful. The fit depends on document volume, processes, controls, and integration needs.

| Organization | Example purchases | Potential use |
|---|---|---|
| Retail and e-commerce | Stock, packaging, store equipment | Compare supplier invoices with purchasing and delivery records. |
| Manufacturing and distribution | Components, raw materials, maintenance supplies | Review prices and quantities when shipments and invoices differ. |
| Hospitals and healthcare providers | Medical supplies, equipment, office goods | Help AP staff organize invoice checks before payment approval. |
| Construction and facilities businesses | Materials, equipment, maintenance supplies | Review supplier charges against orders and recorded deliveries. |
| Hotels and restaurants | Food, linen, cleaning supplies, equipment | Check repeated purchases and flag invoice differences for staff. |
| Technology and professional-services firms | Software, equipment, office services | Extract and categorize invoices and review charges where supporting records exist. |
| Accounting or outsourced AP teams | Invoices handled for client businesses | Explore a repeatable document-review workflow, provided client separation and other controls are strengthened first. |

For a very small business with only a few invoices, manual review may be sufficient. A company with many invoices may benefit from automation, but would normally need reliable integrations, accounting controls, secure access, and extensive testing before adopting a prototype.

## 6. People involved in a company

- **Purchasing or procurement:** Creates purchase orders and confirms agreed prices and quantities.
- **Receiving or warehouse staff:** Records what was delivered and resolves receiving differences.
- **Accounts payable analyst:** Uploads documents, examines extracted fields and matching issues, and follows up on exceptions.
- **AP manager or finance director:** Reviews higher-risk or disputed invoices according to company policy.
- **Finance or accounting team:** Uses the approved information in its existing accounting and payment process.
- **IT or security team:** Configures the application, database, access, model service, and operational controls.

These are typical business roles, not a claim that the current prototype has a complete role-based access-control system or multi-person approval hierarchy.

## 7. How a company could use FinCheck

A practical evaluation would start with fictional or otherwise authorized test documents in a separate development database:

1. Set up the application, PostgreSQL database, and a supported Gemini model and API key. Keep credentials private.
2. Create a user account and sign in. Use the provided matching and mismatch sample PDFs for the first tests.
3. Upload one invoice and its corresponding PO and goods receipt. Do not mix documents from different transactions unless intentionally testing a mismatch.
4. Watch the processing stages. Compare extracted values against the original documents; specifically check invoice number, supplier, date, PO number, currency, amount, tax, description, quantity, and unit price.
5. Inspect validation, duplicate, matching, classification, anomaly, and risk results. Treat every result as decision support and investigate errors or missing data.
6. When the workflow requests a human decision, record the decision and a useful note. Verify that the resulting status and report reflect that decision.
7. Check run history, invoice details, document comparison, and the JSON and CSV downloads. Confirm that the exported values match the source documents.
8. Record the result, any error messages, and who will follow up. Continue using the organization's normal accounting and payment controls.

For a real deployment, the company would also need to decide who can access each document, how long records are kept, how supplier disputes are handled, which policies control approvals, and how data is transferred to its accounting or ERP system. Those are deployment and product-design decisions; they are not all implemented by this project.

## 8. Using the included sample PDFs

The sample documents are under `output/pdf/fincheck-samples/` when that folder has been generated in the workspace. The documents are fictional and are not payment requests.

### Set 1: matching

- Invoice: `01-matching-invoice.pdf`
- PO: `01-matching-purchase-order.pdf`
- Goods receipt: `01-matching-goods-receipt.pdf`
- Expected invoice: `FC-INV-1001`, total USD 220 including USD 20 tax.
- Expected matching: two office printers at USD 100 each appear on the invoice and PO; the receipt records two received.

### Set 2: mismatching

- Invoice: `02-mismatch-invoice.pdf`
- PO: `02-mismatch-purchase-order.pdf`
- Goods receipt: `02-mismatch-goods-receipt.pdf`
- Expected invoice: `FC-INV-2001`, total USD 528 including USD 48 tax.
- Expected issues: the invoice price is USD 120 versus the PO price of USD 100; the invoice and PO show four units, while the receipt shows three. The invoice subtotal also differs from the expected amount calculated by the matching code.

The model may extract a value incorrectly, and processing may fail for reasons unrelated to the PDFs. Compare actual results with the documents instead of assuming that the expected results were achieved. Reusing the same invoice after it has been inserted can trigger duplicate detection.

## 9. Architecture and data flow

```text
Browser: HTML, CSS, JavaScript
    |
    | login, uploads, progress updates, review decisions
    v
FastAPI backend
    |
    +--> Gemini: extracts information from PDF documents
    |
    +--> LangGraph: coordinates checks and pauses for review
    |
    +--> PostgreSQL: stores application records and graph checkpoints
    |
    +--> Local scikit-learn models: optional anomaly signals
```

The browser uploads PDFs to the backend. The backend saves them temporarily, sends the documents to the configured Gemini service for extraction, runs the workflow, and streams progress events to the browser. Extracted invoice and related records, run reports, users, reviewer decisions, and workflow checkpoints are stored in PostgreSQL as implemented. The temporary upload directory is removed at the end of the processing stream.

Important project files:

- `backend/app/main.py`: FastAPI endpoints, authentication routes, upload handling, streamed progress, history, and resume handling.
- `backend/app/agent.py`: LangGraph state, processing stages, routing, and human-review interruption.
- `backend/app/extracter.py` and `backend/app/schemas.py`: Gemini document extraction and structured data definitions.
- `backend/app/validator.py`, `matching.py`, `classify.py`, `risk_analysis.py`, `approval.py`, and `report.py`: core review logic.
- `backend/app/db.py`, `auth_db.py`, and `dbs/risk_db.py`: database access and schema setup.
- `backend/app/anomaly_detection/`: feature preparation, model training, and prediction.
- `frontend/index.html`, `style.css`, and `frontend/js/`: the browser interface and its API interactions.
- `README.md`: project overview and technology stack; setup details should be checked against the current project configuration.

## 10. Current limitations and responsible use

FinCheck is a prototype. A working screen or a successful sample run does not establish that it is accurate, secure, or suitable for real payments.

- **No payment execution or ERP integration:** The application does not automatically send money or post approvals into accounting software.
- **External document processing:** A local PostgreSQL database does not make document extraction fully local. PDFs are sent to the configured Gemini service; a company must assess data handling and permissions before using sensitive invoices.
- **Extraction and matching limits:** Model output may be incomplete or incorrect. Matching relies on exact normalized item descriptions and specific implemented checks, so equivalent wording or unsupported discrepancies can be missed.
- **Prototype implementation issues:** The optional-document path, saved-report and review flows, and database ownership boundaries need further testing and fixes. Earlier browser testing encountered a model-availability error and did not complete an end-to-end invoice run.
- **Anomaly-model limits:** Results depend on available data and models. The code may skip anomaly detection when no model is present, and its output should not be treated as a fraud finding.
- **Limited business controls:** Full enterprise role management, configurable policy workflows, integrations, monitoring, operational recovery, and comprehensive tests are not established by the current implementation.
- **Privacy and security:** Before real use, review authentication, authorization, cross-user data isolation, retention, backups, secrets, and access to documents and reports.
- **No verified accuracy guarantee:** The README describes a small benchmark, but benchmark results should not be treated as a production accuracy guarantee or a substitute for independent testing on representative company documents.

The appropriate present use is learning, demonstration, and controlled evaluation with fictional or authorized data. Any production use requires a separate security review, functional testing, and business approval.

## 11. Glossary

| Term | Meaning |
|---|---|
| Accounts payable (AP) | The business function that checks and manages amounts owed to suppliers. |
| Supplier or vendor | The business that provides goods or services and submits an invoice. |
| Invoice | A request for payment for goods or services. |
| Purchase order (PO) | A buyer's record of an order and its agreed terms. |
| Goods receipt (GR) | A record of goods received against an order. |
| Three-way matching | Comparing an invoice, PO, and receipt for agreement. |
| Duplicate invoice | An invoice that appears to have already been recorded. |
| Anomaly | An unusual pattern that may warrant inspection, not necessarily an error or fraud. |
| Human in the loop | A workflow in which a person reviews and supplies a decision at a defined stage. |
| Audit trail | Records that help reconstruct what was processed and what decisions were made. |
| ERP | Enterprise software used to manage business processes such as purchasing and accounting. |

