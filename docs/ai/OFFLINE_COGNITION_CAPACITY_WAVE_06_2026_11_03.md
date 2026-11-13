# Offline cognition wave 6/8 — bounded laptop resource admission

Eight resource domains: capacity admission, weighted fair queue,
memory guard, disk guard, token quota, burst control,
preemption hold and actual-output budget reconciliation.

Shared core capacity_guard.py supplies source-/principal-bound resource
requests, short-lived explicit capacity snapshots, atomic multi-resource
previews, in-process CAS token projection, strict non-refund on native
dispatch uncertainty, actual native receipt charge-once accounting, and
weighted fair scheduling previews. A model cannot infer resource
availability, operator rights, credentials or approval from its own text.

It is intentionally *not* the authoritative multi-process
SQLite work-order queue. The separate production work_orders owner must
continue to hold durable capacity leases before any real GGUF generation.
An in-process projection is not crash-safe custody. Model rights,
live Windows/WSL2 observations and device benchmarks are still held.

Validation after completed branch:
    python -m unittest skeleton.testing.test_offline_cognition_capacity_guard -v
    python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q

L00-L02 canonical owner/scope; L03-L05 deterministic admission;
L06-L07 foreign principal, forged telemetry and uncertain native effect
fail closed; L08-L09 bounded cost/risk, memory/disk/slot/tokens and
queue slots; L10 source tests and adversarial profiles; L11-L12
durable restart state remains with canonical work orders; L13
release/comparator/target laptop qualification is withheld.
