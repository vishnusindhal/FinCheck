# AI System

Three AI components: (1) a fixed LangGraph orchestration graph, (2) Gemini LLM calls for extraction and explanation, (3) scikit-learn Isolation Forest anomaly models. No autonomous tool-using agents.

## 1. LangGraph orchestration — [agent.py](../backend/app/agent.py)

- `StateGraph(PipelineState)` (TypedDict, `total=False`) compiled with `PostgresSaver` in production, `MemorySaver` in tests.
- Fan-out: `dispatch_extraction` returns `Send(...)` only for uploaded documents. Fan-in: static edges into `validation`; `merge_optional` reducer on `invoice`, `po`, `gr`, `invoice_confidences`.
- Conditional routing: `route_after_validation`, `route_after_duplicate` → node or `END`.
- Nodes return **only changed keys**.
- Human-in-the-loop: `interrupt({"message", "approval"})` in `approval_node`; resumed with `Command(resume={"decision","note"})`. The node re-runs from the top on resume, so code before `interrupt()` must remain side-effect-free.
- State keys written by persistence: `invoice_id`, `po_db_id`, `gr_db_id` (used for cleanup and run linkage).
- `create_graph(nodes, paths, checkpointer)` is generic; the fan-out target list is `EXTRACTION_NODES`.

## 2. LLM usage (Gemini via `langchain-google-genai`)

| Use | Entry point | File |
|---|---|---|
| Structured extraction (Invoice, PO, GR) | `extract_document(path, prompt, schema)` → `_structured(schema).invoke(...)` | [extracter.py](../backend/app/extracter.py) |
| One-sentence risk explanation  | `explanation(context)` | [anomaly_exp.py](../backend/app/anomaly_exp.py) |

- One lazily created, cached client: `extracter.get_llm()` (`MODEL_NAME`, default `gemini-2.5-flash`; `API_KEY`). Nothing is constructed at import time.
- PDFs sent inline as base64 `{"type":"media","mime_type":"application/pdf"}` + text prompt.
- Extraction retries (3 attempts, 2 s / 4 s backoff) **only for transient errors** (`google.genai.errors.ServerError`, HTTP 429/5xx, "unavailable"/"resource exhausted"). Auth/model/validation errors fail fast → SSE `error` (and cleanup).
- Explanation: 3 attempts on any error, then `"Flagged due to multiple risk indicators."`; handles list-style content blocks; truncated to 250 chars. Called when risk score > 0 — for final reports and for provisional reports of paused runs.

### Prompts — [system_prompt.py](../backend/app/system_prompt.py)
- `INVOICE_EXTRACTION_PROMPT`: header fields + line items; amounts as plain numbers; ISO 4217 currency; **explicit instructions to fill `confidence` with 0.0–1.0** for every header field and line item; null for missing values.
- `PO_EXTRACTION_PROMPT`, `GR_EXTRACTION_PROMPT`: numeric quantities/prices, ISO dates.
- Explanation `SYSTEM_PROMPT` (`anomaly_exp.py`): one sentence < 35 words, only provided context; few-shot examples use the real context shape `{risk_level, signals[]}`.
- Context builder `helper.process_context(report)` → `{invoice_number, vendor_name, risk_level, risk_score, signals[]}`; signals = validation errors + readable descriptions of every matching issue format (`helper._describe_issue`) + risk reasons + warnings.

### Schemas & post-processing
- `schemas.Invoice`: header fields are `ConfidentField{value, confidence}`; `invoice_date` normalized by a model validator.
- After extraction: `unwrap_confident_fields` → `normalize_invoice` (amounts/quantities to float via `to_number`, currency symbol → ISO, ids to str). `extract_confidences` keeps header confidences for non-null fields.
- GR: `normalize_goods_receipt` (ISO `received_date` or None, numeric quantities).

## 3. Rule-based logic

| Step | Logic | File |
|---|---|---|
| Validation | invoice present; required fields; total > 0; tax ≥ 0 (numbers); date in 6 formats; ISO currency | `validator.py` |
| Matching | items keyed by normalized description; GR vs PO qty; invoice price > +2 % → critical, < −2 % → warning (`price_low`); invoice qty > received → critical; subtotal vs Σ po_price × min(inv_qty, gr_qty) within 2 % | `matching.py` |
| Classification | keyword rules, 6 categories | `classify.py` |
| Risk | +40 critical match issue; +15 total > 1.5× user's vendor average (excluding this invoice); +15 any confidence < 0.6; +10 new vendor for this user; +25 ML anomaly; −15 / +20 from **this user's** past decisions (≥ 3, ≥ 80 % / ≤ 20 % approval). Tier ≥ 50 high, ≥ 20 medium | `risk_analysis.py` |
| Approval | high tier or unmatched → AP Manager review; low + matched + total < `AUTO_APPROVE_LIMIT` → auto; total ≥ `DIRECTOR_REVIEW_LIMIT` → Finance Director; else AP Team | `approval.py` |

## 4. ML anomaly detection — [anomaly_detection/](../backend/app/anomaly_detection/)

- Features (`FEATURES`): invoice_total, tax_percent, line_item_count, avg_unit_price, vendor_avg_invoice_total, vendor_std_invoice_total, vendor_avg_line_items, vendor_invoice_frequency, days_since_last_vendor_invoice, invoice_total_ratio, line_item_count_ratio.
- Model: `StandardScaler` → `IsolationForest(n_estimators=200, contamination=0.05, random_state=42)`.
- Training (`train.train_all`): per `(user_id, vendor_name, currency)` with ≥ 5 invoices + global model when ≥ 5 total; saved to `MODELS_DIR` (default `<project root>/models`).
- Lifecycle: `retrain_from_db()` at startup and after each completed run / human decision, in a daemon thread guarded by a lock; results published with `predict.set_models()`.
- Inference (`predict.detect_anomaly`): model = vendor → global → skip. Features computed by `_feature_row`, which appends the current invoice to the user's stored invoices for that vendor (excluding the current row) and runs the same `build_features` as training — no more training/serving skew. Errors never fail the pipeline (`model_used: "error"`).

## 5. Evaluation
README cites a 15-invoice benchmark; its data/notebooks are not in the repo. Offline tests (`tests/`) cover the deterministic logic, not model quality.

## Cost / data handling
- Per run: 1–3 extraction calls + up to 1 explanation call (another at resume time if risk > 0).
- Documents are sent to Google (see FINCHECK_PROJECT_GUIDE.md §10).
