# AI Orchestration Quality Contract

The intelligence control plane must fail over instead of silently swallowing provider failures, reject answers below an explicit confidence contract, respect request deadlines, expose per-handler health, and bound expensive multi-handler arbitration.

This upgrade adds quality-ranked handler routing, confidence gates, circuit breaking, deadline-aware execution, bounded best-confidence arbitration, result caching, failure provenance, and route/handler telemetry while preserving the existing `register_handler(capability, handler)` and `reason(query, context)` call shapes.

## Operational invariants

- A broken handler cannot permanently block healthy fallbacks.
- Low-confidence output is a soft rejection, not a successful completion.
- Repeated hard failures temporarily open that handler's circuit.
- Expired deadlines stop additional handler work.
- Arbitration can be capped with `max_attempts`.
- Cached answers are keyed by query, context, confidence contract, and selection mode.
- Observability failures never take down the reasoning plane.
