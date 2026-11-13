# Ordered AI ecosystem: executable, opt-in source slice

This directory contains implementation work for MBW-00..MBW-07. It is deliberately
**not** a replacement for the existing Jeeves application, engine or provider
authority. Composition requires explicit operator configuration; no implicit
credential loading, network calls, model downloads, or production activation.

* MBW-00 contracts and deterministic budgets.
* MBW-01 authoritative local SQLite custody and crash/replay recovery.
* MBW-02 owned-document bounded retrieval and context assembly.
* MBW-03 independent policy/tool verification and receipts.
* MBW-04 deterministic planner, workflow leases and execution admission.
* MBW-05 app-facing read/submit/status API and event reconcilers.
* MBW-06 offline evaluation, contamination and challenger gating.
* MBW-07 artifact integrity, source inventory and qualification holds.

The canonical master build sequence remains machine/ai_master_build_sequence.json.
Complete integration, security review, actual model acceptance, exact-head CI and
release signoff remain independent requirements.
