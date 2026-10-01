# Runtime Supervision Contract

<!-- machine-git-blob: machine/runtime_supervision.json@db9727f441ee287c7024f532b209a92796c230e9 -->

Machine authority: `machine/runtime_supervision.json`

This control implements the two explicit P2 gaps in VOL-004: unified backend/engine supervision semantics and broader cancellation propagation.

The contract cross-checks the assembled runtime manifest against concrete code symbols for backend lifespan/readiness/shutdown, backend→engine cancel delegation, engine recovery/shutdown, durable cancellation persistence, operation deadlines, and durable-operation dispatcher shutdown.

It deliberately validates both sides of cancellation: application code must delegate cancellation to the engine endpoint, and engine code must persist the cancellation request without reopening terminal work.

The contract is structural/runtime-binding evidence. It does not claim every connector is already hardened or promote VOL-004 maturity.
