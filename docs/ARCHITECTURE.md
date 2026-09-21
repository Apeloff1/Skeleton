# Skeleton Architecture — The Complete Treatise

This document is the definitive description of the Skeleton codebase: its layers, its
invariants, its data flows, and the reasoning behind every structural decision. It is written
to be read linearly.

---

## 1. Governing Principles

1. **The kernel is pure.** Nothing under `skeleton/kernel/` may import a web framework, a
   database driver, or perform I/O. The kernel defines the vocabulary of the system — events,
   errors, identifiers, capabilities — and everything else speaks it.
2. **Dependencies point inward.** Interface → Application → Domain. The API layer may import
   pipelines; pipelines may import the kernel; nothing may import outward.
3. **Every behaviour is complete.** A module that declares a responsibility implements it in
   full. Degraded fallbacks (e.g. the in-memory RAG store used when ChromaDB is absent) are
   themselves fully implemented, not stubs.
4. **State is explicit.** Long-lived mutable state lives behind service objects with narrow
   interfaces; no module-level mutable globals other than immutable registries.
5. **Failures are typed.** Every error raised inside Skeleton derives from `SkeletonError` and
   carries a machine-readable code, a severity, and a structured context payload.

---

## 2. The Kernel

### 2.1 Errors (`kernel/errors.py`)

A lattice of exception types rooted at `SkeletonError`. Each error carries:

- `code` — a stable, namespaced, machine-readable string (`JEE.RAG.UNAVAILABLE`).
- `severity` — one of `INFO`, `WARNING`, `ERROR`, `CRITICAL`, driving alerting.
- `context` — an arbitrary structured dict, safe to serialise into logs and API responses.

The lattice mirrors the subsystems: `KernelError`, `AgentError` (with `ConsensusError`,
`SchedulingError`), `PipelineError` (with `GenerationError`, `ValidationError`),
`JeevesError` (with `RagUnavailable`), and `ForgeError`. Handlers at the API boundary map
each onto HTTP statuses deterministically.

### 2.2 Events (`kernel/events.py`)

A synchronous, in-process domain event bus with:

- **Topics** as dotted strings (`pipeline.npc.completed`), matched by exact name or by
  prefix wildcard (`pipeline.*`).
- **Correlation ids** threaded through every event so a full pipeline run can be traced.
- **Replayable history** — the bus retains a bounded ring of past events for audit and for
  late-joining subscribers.
- **Isolation of subscriber failure** — one failing handler never prevents the others.

### 2.3 Identifiers (`kernel/ids.py`)

Strongly-typed value objects (`AgentId`, `SessionId`, `PipelineRunId`, …) built on a common
`EntityId` base. They validate on construction, render as prefixed strings (`agent_01HZX…`),
and are hashable/immutable so they can be used as dict keys throughout.

### 2.4 Registry (`kernel/registry.py`)

A capability registry: named, versioned records of what the system can do (pipeline kinds,
forge blueprint kinds, agent specialisations). Registrations are validated for uniqueness and
semver compatibility, health can be recorded per-capability, and the registry emits events on
every mutation so observers (metrics, the API's `/capabilities` endpoint) stay consistent.

---

## 3. The Agent Substrate

### 3.1 Ledger (`agents/ledger.py`)

An append-only, in-memory activity ledger with O(1) append and indexed queries by agent, by
action, and by time window. Every meaningful act in the system — a pipeline stage completing,
an agent winning a quorum, a forge materialisation — appends a `LedgerEntry`. The ledger is
the single source of audit truth and exposes:

- `query(...)` with composable filters,
- `summarise(agent_id)` returning per-agent activity statistics,
- `tail(n)` for the most recent entries (powers the `/agents/activity` endpoint).

### 3.2 Mesh (`agents/mesh.py`)

The agent mesh maintains the live roster of agents, each with specialisations, load metrics,
and a heartbeat. It provides:

- **Discovery & routing** — `route(capability)` selects the least-loaded healthy agent
  advertising a capability, with deterministic tie-breaking.
- **Heartbeat & liveness** — agents that miss their TTL are quarantined, then evicted.
- **Quorum consensus** — `propose(proposal, voters)` runs a simple majority vote with weight
  support; failure raises `ConsensusError` with the full ballot record attached as context.

### 3.3 Scheduler (`agents/scheduler.py`)

A priority-queue swarm scheduler with:

- **Weighted priorities** and FIFO ordering inside a priority class,
- **Backpressure** — a bounded in-flight window; excess submissions queue,
- **Retries with exponential backoff** and a dead-letter sink,
- **Graceful drain** so shutdowns finish in-flight work deterministically.

---

## 4. The Pipelines

Each pipeline is a staged generator. Stages are pure functions from a context object to a
partial artefact; the pipeline engine sequences them, emits events at stage boundaries, and
records each stage in the ledger.

### 4.1 Text-to-NPC (`pipelines/npc.py`)

Stages: `parse_description → build_persona (OCEAN-weighted trait vector) → generate_dialogue
(branching tree with mood gates) → generate_behaviour (utility-scored behaviour graph) →
assemble_npc`. The output `Npc` artefact is fully serialisable and carries provenance: model
seed, stage timings, and the run id.

### 4.2 Text-to-Game-Logic (`pipelines/game_logic.py`)

Synthesises combat (turn-based/real-time), economy (sources/sinks, inflation guards), and
progression (XP curves, unlock graphs) subsystems from a declarative spec, then runs a
**balance simulation** — Monte-Carlo playouts used to tune coefficients before the artefact is
returned.

### 4.3 Text-to-Animation (`pipelines/animation.py`)

Generates a skeleton (bone hierarchy with constraints), keyframe clips (procedurally
interpolated), and an animation state machine with transition guards and blend trees for
locomotion. Output is engine-agnostic JSON consumable by Godot/Unity importers.

---

## 5. Jeeves

### 5.1 Core (`jeeves/core.py`)

The tutor brain. Holds the **System Laws** — the three canonical pedagogical instruction
blurbs — and orchestrates tutoring sessions: opening assessment, Socratic loop, co-coding
mode, and session close-out with mastery deltas. Session state is a first-class object,
serialisable and resumable.

### 5.2 Matrices (`jeeves/matrices.py`)

Full implementations of the three self-learning matrices:

- **SAM** — Skill Acquisition Matrix: per-skill mastery in [0,1], updated by spaced evidence,
  with decay for stale skills and ZPD (zone of proximal development) computation.
- **CLOM** — Cognitive Load Optimisation Matrix: estimates intrinsic/extraneous/germane load
  per activity and recommends pacing.
- **KREM** — Knowledge Retention & Elasticity Matrix: forgetting curves per concept, driving
  the spaced-repetition schedule.

### 5.3 RAG (`jeeves/rag.py`)

Retrieval-augmented memory. Uses ChromaDB when available; otherwise a fully implemented
in-memory store with TF-IDF-weighted cosine retrieval, chunking, and metadata filters. Both
backends share one interface (`MemoryStore`), so the tutor never knows the difference.

---

## 6. The Universal Forge

`forge/universal.py` implements composable **blueprints**: declarative descriptions of game
systems (mechanics, economies, narratives) with slot types, constraints, and composition
rules. The forge validates a blueprint against the registry, resolves its dependency graph
with cycle detection, materialises it into concrete artefacts, and scores the result against
quality gates. Materialisation is deterministic given a seed.

---

## 7. The API Layer

`api/server.py` exposes `create_app()`: a FastAPI application factory wiring every subsystem,
installing the error→HTTP mapping, request-id middleware, and lifespan-managed resources.
`api/routes.py` declares the REST surface — health, capabilities, pipelines, jeeves sessions,
agent activity, forge operations — each endpoint thin: validate → call service → serialise.

---

## 8. Testing Doctrine

The `tests/` tree mirrors the package. Tests are hermetic: no network, no real database — the
in-memory RAG backend and the in-process event bus make every subsystem testable in isolation.
Integration tests compose subsystems through the real wiring used by `create_app()`.

---

## 9. Cortex organism

Jeeves neocortex is the model in training. Slots are ModelPorts:

- **pfc** — small 1-layer LM (boilerplate + DRAFT)
- **midbrain** — medium 1-layer coordinator LM
- **left** — analytic LM (TTK / mix / oracle)
- **right** — gestalt LM (era / soul / bias)
- **neo** — stacked Pre-LN GELU, tied unembed, BPE ids
- **neo_rms** — stacked RMSNorm + SwiGLU

`acquire` copies weights via `absorb_mouth`. `surpass` answers from neo decode.
Callosum `fuse_tracts` binds hemisphere hiddens. Zaibatsu elects the speaking mouth.
Hive `bundle`/`pull`/`consensus` interchange both neos and both LoRA banks.
Sleep replay SGD both neos. Dodecahedron seal has twelve faces; `number == 12` is complete.
Birth is closed-world. HuggingFace and Kimi bind as teachers (`bind_hf`, `bind_kimi`);
neo distills their text. No import-time download.

---

## 10. Scientific evidence and architecture evolution

Skeleton separates **knowledge absorption**, **research evaluation**, and **production
promotion**. Papers, preprints, benchmarks, model reports, and external implementations are
evidence inputs; none are production authority by themselves.

The canonical research path is:

```text
source -> versioned evidence -> claim/provenance graph -> local experiment
       -> benchmark + ablation + challenge -> architecture decision
       -> shadow -> canary -> promoted version -> monitoring / rollback
```

Serving continues to consume only promoted state. Research workers, ingestion workers,
challenger policies, and training jobs cannot directly mutate serving-visible knowledge,
deployed weights, privileged tool policy, or runtime authority.

The model substrate is intentionally replaceable. Dense Transformer, sparse, state-space,
hybrid, mixture-of-experts, adapters, and future model families must sit behind stable model
and runtime contracts rather than leak family-specific assumptions into the kernel.

Reasoning is also a budgeted runtime policy. Direct generation, self-consistency,
decomposition, search, verifier-guided reasoning, and tool-assisted investigation are modes
selected by task difficulty, uncertainty, consequence, latency, cost, and measured marginal
benefit. No reasoning mode receives unbounded compute.

Memory is split conceptually into working, episodic, semantic, and procedural classes, each
with different write/promotion semantics. Retrieved or remembered content retains provenance
and trust metadata and cannot elevate its own instruction authority.

Tool side effects follow the canonical sequence:

```text
ToolIntent -> capability/policy checks -> validation -> approval/risk gate
           -> ValidatedToolCall -> execution -> ToolExecutionReceipt
           -> observation -> verification
```

Verification is plural: deterministic checks, tests, properties, fuzzing, source validation,
learned critics, process/outcome verifiers, and formal techniques may all contribute. No
single learned judge is treated as truth.

Canonical navigation for this layer:

- [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md) — master human index and authority order;
- [BUILD_PLAN.md](BUILD_PLAN.md) — Tracks Q–AC construction sequence;
- [architecture/research-evidence-evolution.md](architecture/research-evidence-evolution.md) — scientific evidence, experiment, and promotion contract;
- [architecture/research-source-catalog.md](architecture/research-source-catalog.md) — historical/frontier research canon and anti-canon;
- [architecture/sota-absorb-engine.md](architecture/sota-absorb-engine.md) — durable evidence/knowledge absorption;
- [architecture/adaptive-absorption-fabric.md](architecture/adaptive-absorption-fabric.md) — challenge, champion/challenger evolution, and snapshot promotion;
- [architecture/masterplan-gap-audit.md](architecture/masterplan-gap-audit.md) — hostile cross-cutting gap audit, P0 production-readiness blockers, and combined fault campaigns;
- [architecture/exotic-architecture-lab.md](architecture/exotic-architecture-lab.md) — quarantined architecture-changing experiments, falsification batteries, state-containment and graduation rules.

The machine-readable counterpart is `skeleton/architecture_index.py`, which must index every
numbered architecture round. A future architecture round that is not indexed is incomplete.


### Adversarial production-readiness layer

The scientific/optimizer plan is subordinate to the frontier hardening invariants.

A subsystem may be a useful research prototype while an applicable P0 hostile-audit gap is open, but it cannot claim production-grade status. Production claims require representation identity, data lineage, unified artifact identity, state-compatible rollback, eval isolation, authenticated principals, execution containment, supply-chain verification, declared storage semantics, stale-writer rejection, secret containment, verified recovery, protected control-plane capacity, immutable config identity, safe unknown-outcome reconciliation, deletion propagation, poisoning resistance, safe artifact loading, tamper-evident authority history, and a tested safe mode.

This rule exists to prevent capability work from outrunning the substrate required to operate it safely and reproducibly.


### Exotic architecture laboratory

Track AC is a quarantined research plane for architecture families that challenge current assumptions rather than merely optimize them.

Current candidate classes include test-time neural memory, dynamic byte-latent modeling, diffusion/non-autoregressive generation, recurrent latent depth, fixed-point/equilibrium computation, conditional depth, differential attention, native ternary weights, fully sparse activations, cross-layer shared sparse routing, latent multimodal modeling, reversible blocks, fast weights, generated adapters, world-model planning, graph-native computation, event-driven/neuromorphic substrates and bounded architecture synthesis.

This plane does not weaken authority boundaries:

- mutable inference-time neural state is not durable trusted memory;
- tentative diffusion/revision/speculative generations are not committed outputs;
- exotic candidates cannot execute privileged side effects from uncommitted states;
- architecture-search results cannot self-promote;
- compound architectures require component ablation;
- Track AB P0 invariants remain binding;
- a candidate must graduate through the Track AA full-stack promotion path before production consideration.
