# gameforge-rs inventory — consolidation pass 01

## Source

- Repository: `Apeloff1/gameforge-rs`
- Revision inspected: `main` (`README.md`, SHA `e97264174a089058b257bb11271151f0dfbf20ff`)
- Frontier disposition: **SELECTIVE PROMOTION**

## Confirmed capability map

| Source surface | Frontier destination | Disposition | Action |
|---|---|---|---|
| `gf-core` settings/event bus/idempotency | `skeleton/runtime/`, `skeleton/services/` | CHARACTERIZE | Reuse contracts/patterns where stronger than current implementation. |
| `gf-services` tiered cache | `skeleton/kernel/` | PROMOTE | Existing Skeleton TieredCache work is already aligned; reconcile rather than duplicate. |
| `gf-services` connection pool | `skeleton/kernel/` | PROMOTE | Existing HealthPool work is already a direct candidate; verify parity and gaps. |
| adaptive backpressure | `skeleton/kernel/` | PROMOTE | Existing AdaptiveGate/related work; compare semantics and tests. |
| buffer pool | `skeleton/kernel/` | PROMOTE | Existing BufferPool work; reconcile semantics. |
| request coalescing | `skeleton/kernel/` | PROMOTE | Existing Coalesce work; reconcile semantics. |
| traffic shaping | `skeleton/services/` | CHARACTERIZE | Extract deterministic rate-limit policy only. |
| chaos tolerance | `skeleton/services/` | PROMOTE | Existing ChaosGovernor lineage; compare state machine and degradation policy. |
| PBFT quorum | `skeleton/kernel/` | PROMOTE | Existing Court work is the current Python contract candidate; verify behavior against Rust. |
| sagas / event sourcing | `skeleton/runtime/`, `skeleton/services/` | CHARACTERIZE | Extract durable transition semantics and invariants. |
| swarm DAG / legions / governance | `skeleton/intelligence/`, `skeleton/services/` | CHARACTERIZE | Mine contracts only; avoid wholesale framework coupling. |
| cognition | `skeleton/ai/` | CHARACTERIZE | Compare with existing Jeeves/Cortex control plane. |
| media studio | `apps/studio/`, `cockpit/` | DEFER | Keep outside kernel until application contracts stabilize. |
| 68 routes / Axum server | `services/` | REJECT WHOLESALE COPY | Route layer is infrastructure, not canonical domain contract. |
| `gf-ffi` C ABI | `packages/rust/`, adapters | CHARACTERIZE | Consider only after stable cross-language contracts are established. |

## Immediate extraction queue

1. Compare Rust `gf-services` implementations with existing Skeleton `TieredCache`, `HealthPool`, `BackgroundLane`, `AdaptiveGate`, `BufferPool`, and `Coalesce` ports.
2. Compare `quorum::Court` against the existing `skeleton/kernel/court.py` and preserve the stronger behavioral contract.
3. Mine event bus/idempotency invariants from `gf-core` for provider-neutral runtime contracts.
4. Characterize saga/event-sourcing semantics before any application integration.
5. Characterize swarm/governance/cognition as isolated contracts before promotion.

## Guardrails

- Rust remains a source implementation, not an excuse to bypass Frontier layering.
- No MongoDB requirement in kernel contracts.
- No Axum dependency in core/runtime contracts.
- Preserve bounded-memory and fail-closed invariants where tests confirm them.
- Every promoted implementation records source repository, revision, and source path provenance.
- Reconcile with existing Skeleton ports before adding duplicate implementations.
