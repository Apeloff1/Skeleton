# Exotic Systems Depth Layer

Status: **candidate/research depth; breadth-freeze compatible**

Machine mirror: [`machine/ai_exotic_systems_catalog.json`](../../machine/ai_exotic_systems_catalog.json)

This layer adds unusual, high-upside mechanisms to the masterplan **without creating new top-level architecture volumes**. Every candidate maps back to existing Volume 000–420 domains and P0 work packages. Exotic mechanisms are opt-in, bounded, independently disableable, and must preserve the canonical fallback path.

## Promotion doctrine

```text
rare mechanism / research signal
  -> bounded candidate
  -> reproducible baseline comparison
  -> failure + adversarial evaluation
  -> integration contract
  -> kill switch + fallback proof
  -> canary / shadow where safe
  -> independent verification
  -> normal maturity + signed-accountability promotion
```

No exotic mechanism receives production authority because it is novel, fashionable, theoretically elegant, or benchmark-positive in isolation. Promotion requires evidence that survives cost, latency, reliability, security, rollback, compatibility and operational review.

## Mandatory constraints

- No candidate may expand top-level breadth beyond Volume 420.
- No candidate may replace canonical state/authority/policy contracts without an ADR and migration plan.
- No candidate may remove the canonical fallback until production maturity is independently evidenced.
- All experiments must be budgeted, bounded and cancellable.
- Learned or probabilistic components may propose; deterministic authority still decides side effects.
- Hardware-specific candidates require portable semantic/golden-reference tests.
- Distributed candidates must define failure, partition, ordering and replay semantics.
- Adaptive-learning candidates must define drift, rollback and catastrophic-forgetting checks.
- Research candidates expire or revert to watchlist when ownership/evidence is stale.

## Catalogue

### cognitive architecture

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-001 | Active-inference control loop | high | 13, 18, 19, 317 | WP-W11, WP-W12, WP-W18 | Treat perception, action and model selection as bounded belief/goal mismatch minimization rather than a single prompt-response loop. |
| EXO-002 | Predictive-processing hierarchy | medium | 9, 13, 19, 366 | WP-W10, WP-W11, WP-W28 | Maintain layered predictions and residuals so expensive cognition is allocated where model/world mismatch is largest. |
| EXO-003 | Global-workspace arbitration | medium | 13, 16, 17, 300 | WP-W11, WP-W15, WP-W16 | Use a narrow broadcast workspace that admits only high-salience state from specialist processes, with deterministic admission rules. |
| EXO-004 | Blackboard-with-leases reasoning | high | 13, 17, 39, 299 | WP-W11, WP-W16, WP-W04 | Specialists post hypotheses to a shared blackboard while write leases and provenance prevent unbounded overwrite races. |
| EXO-005 | Stigmergic coordination | medium | 17, 334, 378 | WP-W16, WP-W13, WP-W03 | Coordinate agents through constrained artifact/environment traces instead of direct chatter when low-coupling collaboration is preferable. |

### optimization search

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-006 | Monte-Carlo tree search for tool plans | high | 14, 19, 251, 253 | WP-W12, WP-W17 | Search bounded action trees with explicit simulation budgets, deterministic terminal conditions and verifier-backed rollouts. |
| EXO-007 | CMA-ES policy/config search | medium | 27, 35, 405, 416 | WP-W27, WP-W18, WP-W29 | Use covariance-matrix adaptation for non-differentiable routing, scheduler or policy parameters inside sandboxed evaluation. |
| EXO-008 | Quality-diversity MAP-Elites | medium | 27, 35, 415, 416 | WP-W27, WP-W18 | Maintain diverse high-performing candidate behaviors across measurable niches instead of collapsing to one global optimum. |
| EXO-009 | Novelty-search escape hatch | high | 27, 35, 416, 419 | WP-W27, WP-W18 | Reward behavioral novelty only in bounded research runs to escape deceptive local optima, never as a production objective. |
| EXO-010 | Population-based training controller | high | 6, 143, 147, 149 | WP-W27, WP-W28, WP-W30 | Jointly evolve hyperparameters and checkpoints with reproducible lineage, promotion gates and rollback. |
| EXO-011 | Bandit-based strategy allocation | medium | 8, 13, 186, 366 | WP-W06, WP-W11, WP-W18 | Allocate test-time compute among reasoning/retrieval/tool strategies with regret tracking and hard per-operation budgets. |
| EXO-012 | Value-of-information scheduler | medium | 14, 252, 253, 405 | WP-W12, WP-W17, WP-W21 | Estimate whether another retrieval, tool call, simulation or verifier pass is worth its latency and cost. |

### memory knowledge

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-013 | Modern Hopfield associative memory | medium | 10, 12, 361, 363 | WP-W07, WP-W09, WP-W18 | Explore energy-based associative retrieval for compact pattern completion with explicit collision and interference evaluation. |
| EXO-014 | Sparse distributed memory | medium | 10, 136, 361, 363 | WP-W07, WP-W03 | Store high-dimensional sparse patterns for robust approximate recall under corruption, with deterministic fallbacks. |
| EXO-015 | Hyperdimensional / vector-symbolic memory | medium | 10, 12, 13, 350 | WP-W07, WP-W09, WP-W11 | Represent compositional symbols in high-dimensional vectors for cheap binding, superposition and similarity operations. |
| EXO-016 | Bitemporal knowledge ledger | low | 12, 247, 297, 299 | WP-W09, WP-W03 | Track both valid-time and transaction-time so historical truth, corrections and late arrivals remain queryable. |
| EXO-017 | Truth-maintenance contradiction sets | medium | 12, 248, 359, 419 | WP-W09, WP-W17 | Keep alternative claims and dependency justifications rather than forcing eager overwrite when evidence conflicts. |
| EXO-018 | Datalog rule slice | medium | 12, 128, 250, 359 | WP-W09, WP-W01 | Use a bounded declarative rule engine for provenance-preserving recursive relationships that are awkward in prompt logic. |

### model inference

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-019 | Mixture-of-experts sparse routing | high | 6, 7, 8, 381 | WP-W05, WP-W06, WP-W29 | Explore sparse expert activation with load-balancing, expert-capacity limits and explicit fallback to dense paths. |
| EXO-020 | Adaptive-computation early exit | medium | 7, 185, 186, 391 | WP-W05, WP-W21 | Permit early transformer/layer exit when calibrated confidence and verifier checks meet policy, with full-path fallback. |
| EXO-021 | Speculative decoding cascades | medium | 7, 389, 391, 415 | WP-W05, WP-W29 | Use draft models or n-gram/speculator paths to accelerate decoding while the authority model verifies tokens. |
| EXO-022 | Medusa / multi-head token speculation | medium | 7, 389, 391, 416 | WP-W05, WP-W29, WP-W27 | Evaluate multi-token candidate heads for parallel verification under strict compatibility and regression gates. |
| EXO-023 | Recurrent-memory transformer variants | high | 6, 9, 10, 18 | WP-W05, WP-W07, WP-W10 | Evaluate recurrent state or memory-token architectures for long-horizon continuity without assuming infinite context. |
| EXO-024 | State-space sequence models | medium | 6, 7, 20, 31 | WP-W05, WP-W29 | Evaluate selective state-space or hybrid recurrent architectures for long sequences where attention cost dominates. |
| EXO-025 | Energy-based verifier models | medium | 37, 152, 207, 208 | WP-W17, WP-W18 | Score candidate outputs/plans with learned energy functions separated from generator authority. |
| EXO-026 | Test-time compute scaling controller | high | 13, 186, 368, 405 | WP-W11, WP-W21 | Scale sampling, search, verifier depth and deliberation only when predicted quality gain justifies budget. |

### formal methods

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-027 | TLA+ protocol model candidates | low | 29, 30, 127, 200 | WP-W19, WP-W17, WP-W01 | Model critical distributed state machines before implementation and translate invariants into executable tests. |
| EXO-028 | Alloy structural model checks | low | 28, 127, 128, 200 | WP-W14, WP-W17, WP-W01 | Use bounded relational model finding for authority, graph and schema invariants that are easy to violate compositionally. |
| EXO-029 | SMT-backed plan verifier | medium | 14, 200, 303, 370 | WP-W12, WP-W17, WP-W14 | Encode plan preconditions, resource constraints and authority constraints as satisfiability checks for high-impact plans. |
| EXO-030 | Temporal-logic runtime monitors | medium | 18, 127, 183, 317 | WP-W11, WP-W17, WP-W21 | Compile safety/liveness properties into runtime monitors for critical workflows and autonomy state transitions. |
| EXO-031 | Proof-carrying action proposals | high | 15, 28, 37, 378 | WP-W13, WP-W14, WP-W17 | Require selected high-impact tool proposals to include machine-checkable evidence that policy preconditions hold. |

### distributed runtime

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-032 | CRDT research plane | high | 30, 132, 133, 331 | WP-W03, WP-W19, WP-W23 | Use CRDTs only for explicitly commutative collaborative state, never silently for authoritative non-commutative records. |
| EXO-033 | Differential dataflow incrementality | medium | 30, 39, 139, 246 | WP-W04, WP-W09, WP-W21 | Explore incremental fixed-point computation for continuously changing dependency, graph and analytics views. |
| EXO-034 | Optimistic discrete-event simulation | high | 19, 284, 316, 416 | WP-W12, WP-W27 | Use Time-Warp-style speculative simulation only in isolated digital-twin/research environments with rollback logs. |
| EXO-035 | Tuple-space coordination | medium | 17, 30, 39, 398 | WP-W16, WP-W29, WP-W04 | Evaluate Linda-style tuple spaces for decoupled worker/agent coordination under typed schemas and lease expiry. |
| EXO-036 | Gossip membership / failure suspicion | medium | 29, 30, 286, 390 | WP-W19, WP-W29 | Use bounded gossip-style membership for large research worker pools where centralized heartbeats become bottlenecks. |
| EXO-037 | Work-stealing heterogeneous scheduler | medium | 31, 286, 287, 392 | WP-W29, WP-W19 | Allow idle workers to steal compatible tasks while preserving data locality, authority and hardware constraints. |
| EXO-038 | Deterministic replay lane | medium | 29, 295, 296, 299 | WP-W19, WP-W21, WP-W30 | Capture enough inputs, ordering and seeds to replay selected concurrency/inference failures inside a bounded envelope. |

### hardware compute

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-039 | Spiking-neural accelerator research | high | 6, 31, 32, 187 | WP-W05, WP-W29, WP-W27 | Evaluate event-driven spiking models on compatible hardware for ultra-low-power specialist workloads only. |
| EXO-040 | Neuromorphic event pipeline | medium | 20, 31, 153, 187 | WP-W20, WP-W29 | Represent sparse temporal sensor events without densifying them prematurely when hardware/source semantics benefit. |
| EXO-041 | FPGA inference kernels | high | 7, 31, 32, 392 | WP-W05, WP-W29, WP-W30 | Prototype fixed-shape low-latency kernels for narrow hot paths with golden-reference and bit-level validation. |
| EXO-042 | Photonic / optical inference watchlist | reference | 31, 78, 392, 416 | WP-W26, WP-W29 | Track photonic matrix-multiply platforms as research candidates gated by reproducibility, tooling and deployment evidence. |
| EXO-043 | Reversible-computing watchlist | reference | 31, 187, 410, 416 | WP-W26 | Track reversible logic techniques for future energy-constrained compute without assuming near-term production viability. |
| EXO-044 | Approximate-computing kernels | high | 31, 32, 70, 187 | WP-W29, WP-W17, WP-W18 | Permit precision/approximation tradeoffs only where error bounds are explicit and verifier/fallback paths exist. |

### adaptive learning

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-045 | Online conformal calibration | medium | 35, 70, 248, 405 | WP-W18, WP-W21, WP-W28 | Maintain distribution-aware confidence sets/calibration with drift detection instead of treating raw model scores as probabilities. |
| EXO-046 | Reservoir-computing adapters | medium | 6, 20, 40, 416 | WP-W05, WP-W20, WP-W27 | Explore fixed recurrent reservoirs with trained readouts for cheap streaming adaptation on narrow temporal signals. |
| EXO-047 | Liquid time-constant networks | medium | 6, 19, 20, 416 | WP-W05, WP-W20, WP-W27 | Evaluate continuous-time adaptive dynamics for irregular sensor streams and control tasks inside simulation first. |
| EXO-048 | Meta-learning fast adapters | high | 6, 149, 411, 416 | WP-W27, WP-W28 | Explore learned adaptation rules that produce bounded task-specific adapters without directly modifying production base weights. |
| EXO-049 | Continual-learning rehearsal mix | high | 6, 10, 149, 419 | WP-W07, WP-W28, WP-W18 | Use replay, regularization and adapter isolation to reduce catastrophic forgetting during approved incremental learning. |
| EXO-050 | Homeostatic resource controller | medium | 29, 180, 186, 317 | WP-W19, WP-W21 | Apply control-theoretic target bands to queue depth, latency, cost and cognitive effort rather than maximizing any single signal. |

### security resilience

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-051 | Capability-machine style authority tokens | high | 15, 26, 28, 170 | WP-W13, WP-W14, WP-W20 | Represent executable authority as unforgeable scoped capabilities with attenuation rather than ambient privilege. |
| EXO-052 | Information-flow label propagation | high | 26, 27, 28, 354 | WP-W20, WP-W14, WP-W10 | Propagate confidentiality/integrity labels through context, tools, artifacts and model routes with fail-closed joins. |
| EXO-053 | Moving-target sandbox identities | medium | 26, 164, 173, 399 | WP-W20, WP-W13 | Rotate sandbox/process identities and ephemeral credentials for risky tool sessions to reduce persistence after compromise. |
| EXO-054 | N-version verifier diversity | medium | 36, 37, 208, 415 | WP-W17, WP-W18 | For selected high-impact decisions, compare structurally different verifier implementations to reduce correlated failure. |
| EXO-055 | Byzantine-resilient research aggregation | high | 30, 35, 36, 210 | WP-W18, WP-W26, WP-W29 | Use robust statistics or quorum rules when aggregating untrusted/heterogeneous research workers, never naive averaging. |
| EXO-056 | Honeytoken research canaries | medium | 26, 36, 167, 168 | WP-W20, WP-W18 | Seed non-sensitive decoy markers in isolated evaluation environments to detect unexpected exfiltration paths. |

### dataflow storage

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-057 | Content-addressed execution artifacts | low | 5, 38, 136, 275 | WP-W03, WP-W21, WP-W30 | Address immutable build/eval/research artifacts by digest so replay, deduplication and provenance become compositional. |
| EXO-058 | Merkleized state snapshots | medium | 5, 38, 136, 360 | WP-W03, WP-W09 | Use Merkle trees for large immutable snapshots to enable partial verification, deduplication and corruption localization. |
| EXO-059 | Incremental view maintenance | medium | 5, 137, 246, 352 | WP-W03, WP-W08, WP-W09 | Update derived search/analytics/knowledge views from change sets instead of full recomputation where semantics permit. |
| EXO-060 | Erasure-coded cold evidence archive | medium | 5, 29, 38, 395 | WP-W03, WP-W19 | Evaluate erasure coding for large immutable evidence/artifact archives when durability-cost math beats replication. |
| EXO-061 | Log-structured temporal feature store | medium | 5, 39, 139, 297 | WP-W03, WP-W04, WP-W18 | Preserve append-only feature/event history for reproducible model/eval inputs with bounded compaction. |

### multimodal interface

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-062 | Event-camera perception lane | medium | 20, 153, 154, 416 | WP-W20, WP-W27 | Support sparse asynchronous vision-event streams as a specialist modality without forcing frame-centric assumptions. |
| EXO-063 | Spatial-audio scene graph | medium | 20, 156, 159, 250 | WP-W20, WP-W09 | Represent sound-source identity/location over time and fuse it into multimodal evidence rather than flattening to transcript. |
| EXO-064 | Haptic / force-feedback simulator hooks | high | 19, 20, 164, 416 | WP-W20, WP-W27, WP-W13 | Model haptic observations/actions in simulation contracts for robotics-style research without granting real-world actuator authority. |
| EXO-065 | Cross-modal latent agreement checks | medium | 20, 35, 37, 159 | WP-W20, WP-W17, WP-W18 | Use independent modality encoders/verifiers to flag cases where text, image, audio or structured evidence disagree. |

### research methodology

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-066 | Negative-results registry | low | 1, 78, 213, 419 | WP-W26, WP-W18 | Preserve failed exotic experiments, preconditions and counterexamples so the platform does not repeatedly rediscover dead ends. |
| EXO-067 | Ablation-first promotion rule | medium | 35, 78, 214, 415 | WP-W18, WP-W26, WP-W27 | Require exotic candidates to prove which mechanism produces gains, not merely that a large bundle scores better. |
| EXO-068 | Mechanism transfer ledger | low | 1, 38, 263, 419 | WP-W00, WP-W26 | Track when an old/rare technique is reused in a modern subsystem, including changed assumptions and failure modes. |
| EXO-069 | Sunset-by-default experiments | medium | 118, 262, 411, 418 | WP-W26, WP-W27, WP-W30 | Every exotic candidate receives an expiry/review date and is removed unless evidence justifies continued maintenance. |

### deployment product

| ID | Candidate | Risk | Volumes | Work packages | Mechanism |
|---|---|---|---|---|---|
| EXO-070 | Microreboot lifecycle islands | medium | 29, 120, 278 | WP-W02, WP-W19, WP-W30 | Partition runtime services into restartable lifecycle islands so selected faults can be recovered without restarting the whole application. |
| EXO-071 | Semantic resumable streaming | medium | 40, 183, 295 | WP-W22, WP-W04, WP-W21 | Stream durable operation state as resumable snapshot-plus-delta sequences with monotonic cursors and replay-safe client recovery. |
| EXO-072 | Local-first ambient desktop profile | high | 229, 329, 331 | WP-W24, WP-W23, WP-W07 | Keep workspace continuity and selected inference/memory capabilities local-first, synchronizing opportunistically without making cloud reachability a correctness dependency. |
| EXO-073 | Dual-slot atomic installer and updater | high | 193, 276, 277, 278 | WP-W25, WP-W30 | Use A/B installation slots with content verification, health-gated activation and deterministic rollback to the prior bootable application image. |

## Acceptance template for any promoted exotic

Before an item can graduate from `candidate` to an implementation-bearing status, its owning package must add:

1. a concrete requirement and owner;
2. an explicit contract boundary and canonical fallback;
3. a reproducible benchmark/evaluation against the current champion;
4. at least one negative/failure/adversarial test appropriate to the mechanism;
5. resource accounting for latency, memory/VRAM, throughput, cost and energy where relevant;
6. observability sufficient to prove activation and detect degradation;
7. a kill switch tested independently of the candidate;
8. rollback/recovery evidence;
9. compatibility/migration notes;
10. signed implementation and independent verification evidence through the existing accountability system.

The catalogue is intentionally a **depth reservoir**, not a promise that every exotic mechanism should be built.
