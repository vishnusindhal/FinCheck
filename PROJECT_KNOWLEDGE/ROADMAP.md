# Roadmap

Nothing here is implemented unless stated. The 2026-11-25 bulk fix completed the former P0–P2 bug/security/debt lists (see KNOWN_ISSUES → Resolved).

## Next (verification & hardening)
1. **Runtime verification (R1):** start against a dev PostgreSQL, confirm auto-migrations, run both sample sets end to end in the browser, record results.
2. Add a DB integration test (disposable Postgres) for `initialize_database()` and the `db.py` functions.
3. Decide on version control for the project (E2).
4. Token storage (S8): httpOnly cookie + CSRF, or keep bearer tokens with shorter expiry + refresh.
5. Retraining strategy at scale (L3): scheduled/batched retrain, per-user model limits.
6. Fuzzy line-item matching (L1): normalized SKU/description similarity with reviewer confirmation.

## Product roadmap (owner's stated plans, from README)
- ERP integrations
- Async workflow execution / job queue
- Parallel classification and anomaly detection
- Expanded evaluation benchmarks (and committing the eval harness)
- Policy engine (configurable thresholds, weights, categories — L4)
- Analytics dashboards
- Multi-user collaboration / roles / multi-step approvals
- Reviewer learning models
- Vendor relationship graphs
- (README previously claimed) a "statistical profiling" anomaly tier for vendors with little history — not implemented
