# Master Build Sequence

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine contract: [`machine/ai_master_build_sequence.json`](../../machine/ai_master_build_sequence.json)

This is the canonical **middle layer** between the 421-volume master plan and the atomic AI build queue. The master index says what the full system contains; the AIQ queue says what individual implementation tasks exist; this sequence says **in what dependency-safe construction waves the system is assembled, what may overlap, what stops promotion, and what evidence closes a wave**.

## Completion and accountability law

Wave status is an aggregate view only. It creates no alternate completion authority.

A wave is complete only when its underlying completion-bearing work packages, AIQ tasks, vertical slices, and critical/high risk obligations satisfy the existing signed accountability contracts. Every actual completion still requires implementation sign-off, independent verification sign-off, UTC timestamp, full git SHA, evidence references, and the derived checkbox in `machine/ai_build_accountability.json`.

**No manual wave checkbox can substitute for signed evidence.**

## Construction waves

| Wave | Primary packages | Purpose | Hard dependencies |
| --- | --- | --- | --- |
| MBW-00 | W00–W01 | Authority, contracts, serialization, time, identity, provenance | none |
| MBW-01 | W02–W04, W19 | Runtime spine, durable state, events, recovery | MBW-00 |
| MBW-02 | W05–W10 | Model/runtime data plane, memory, retrieval, knowledge, context | MBW-00, MBW-01 |
| MBW-03 | W13, W14, W17, W20 | Privileged action, policy, verification, security | MBW-00, MBW-01 |
| MBW-04 | W11, W12, W15, W16 | Cognition, planning, agents, swarms | MBW-02, MBW-03 |
| MBW-05 | W21–W24 | Observability, API/streaming, product, desktop | MBW-01, MBW-03, MBW-04 |
| MBW-06 | W18, W26–W28 | Evaluation, research, forge, controlled learning | MBW-02, MBW-03, MBW-04 |
| MBW-07 | W25, W29, W30 | Installer, distributed runtime, production hardening | MBW-05, MBW-06 |

## MBW-00 — Authority, Contracts & Semantic Bedrock

Build meaning before fan-out. Exact identity/version semantics, strict serialization, monotonic duration handling, explicit UTC persistence, authority/budget/cancellation contracts, and canonical signable representations are the foundation.

Exit requires executable treatment of duplicate JSON keys, null/absent distinctions, Unicode normalization/confusables, numeric boundaries, canonicalization and compatibility behavior. Stop immediately if human and machine authority diverge or if a contract change has no migration/compatibility rule.

## MBW-01 — Runtime Spine, Durable State & Recovery

Make boot, durable state, events and recovery trustworthy before higher intelligence depends on them. Authoritative state must survive restart; projections must be rebuildable; events must be idempotent and replay-safe.

Exit requires authoritative-first restore, projection rebuild, restart recovery, duplicate/out-of-order handling, transactional outbox/inbox behavior, cancellation propagation and verified recovery drills. A backup without a proven restore is not evidence.

## MBW-02 — Model, Memory, Retrieval, Knowledge & Context

Build provider-neutral inference and the evidence-aware context plane. Memory promotion, retrieval provenance, knowledge scope/time and context trust labels must remain governed across truncation, compression and fallback.

Exit requires explicit defenses for indirect prompt injection, memory/retrieval poisoning, stale evidence, fallback privacy changes and policy loss under context pressure. Provider-native objects may not leak into durable core state.

## MBW-03 — Privileged Action, Policy, Verification & Security

Tools and side effects are privileged transactions, never model privileges. Authorization, schema validation, risk/approval, admission, idempotency, sandboxing, postconditions and durable receipts remain independent deterministic gates.

Exit requires executable filesystem/archive/network/process adversarial coverage, hallucinated-authorization denial, tool-description/result trust isolation, and verification semantics that distinguish block, abstain, repair and qualified results.

## MBW-04 — Cognition, Planning, Agents & Swarms

Only after context and action safety exist do we build bounded cognitive loops, plan DAGs, agent identity, delegated authority, leases/fencing, conflict domains, handoffs and multi-agent execution.

Exit requires bounded retries/search/delegation, crash-safe checkpoint/resume, stale-lease rejection, child-authority subset enforcement and explicit deadlock/livelock/starvation acceptance.

## MBW-05 — Observability, API, Product & Desktop

Expose durable runtime truth without creating a second truth in UI or streaming state. APIs, cursors, reconnect/replay, traces, costs and product status all project from the same operation/execution contracts.

Exit requires ordered/duplicate/out-of-order stream reconciliation, replay-gap resync, slow-client backpressure, cancel/complete finality, accessibility/platform coverage and traceable evidence from user action to durable outcome.

## MBW-06 — Evaluation, Research, Forge & Controlled Learning

Build the evidence factory and controlled evolution plane. Research and generated candidates can challenge production, but cannot mutate it directly.

Exit requires versioned benchmarks, contamination metadata, replication lineage, champion/challenger comparison, canary/rollback evidence, specification-gaming tests and enforceable promotion boundaries.

## MBW-07 — Installer, Distributed Runtime & Production Hardening

Qualify the whole system on clean machines and distributed compute under realistic failure. Installation, update, repair, rollback, placement, backpressure, capacity, SLOs and incident recovery become release requirements.

Exit requires applicable VS-000 through VS-007 evidence, signed dispositions for affected critical/high risks, clean-machine installation/update/rollback proof, distributed failure drills, and a complete release evidence bundle.

## Universal stop conditions

Construction stops instead of papering over the problem when any of the following occurs:

- an implementation attempts to bypass the current runtime authority contract to match the target plan;
- a privileged action can be authorized by model text alone;
- an external side effect has neither idempotency nor explicit compensation;
- a derived store is treated as authoritative;
- retry/replay semantics can duplicate an external effect;
- policy/trust labels can be removed by truncation, compression or tool/retrieval projection;
- an unresolved critical risk is hidden by aggregate status;
- a production promotion lacks independent verification;
- a planned test name is being used as if it were passing evidence;
- rollback, restore or migration behavior is undefined for a changed durable schema.

## Promotion evidence bundle

Every promoted capability should contribute, where applicable:

1. requirement + rationale;
2. architecture owner and canonical contract;
3. implementation paths and config;
4. migration/compatibility behavior;
5. unit/property/contract tests;
6. adversarial/fuzz/fault/recovery tests;
7. security/privacy/authority assessment;
8. observability and cost/latency characterization;
9. evaluation/benchmark evidence;
10. deployment, rollback and operator runbook;
11. machine-manifest updates;
12. implementation + independent verification sign-offs.

## Relationship to AIQ stages

The 42 AIQ tasks remain the atomic implementation queue. MBW waves do not replace their task dependencies or gap-closure rules. They provide the cross-package construction order:

```text
master volumes (000-420)
        ↓
work packages (W00-W30)
        ↓
master build waves (MBW-00..07)
        ↓
AIQ atomic tasks / gap closure
        ↓
vertical-slice evidence
        ↓
signed promotion
```

This gives builders enough structure to move quickly without confusing architectural ambition, task completion, and production evidence.


## Build packet standard

Every implementation packet created from this masterplan must carry the same minimum anatomy. This prevents “context in someone’s head” from becoming a hidden dependency.

- objective and explicit non-goals;
- volume/requirement and W/AIQ references;
- canonical contracts, state owners and exact implementation paths;
- authority, security, privacy and data-classification notes;
- migration/compatibility behavior;
- failure, recovery and rollback behavior;
- test/evaluation plan, including mapped edge obligations;
- observability, cost and performance signals;
- evidence references;
- implementation and independent-verification sign-offs.

A packet may be split for parallel execution, but none of these fields may disappear simply because work was delegated.

## Definition-of-Ready / Definition-of-Done

**Ready** means dependencies are materially usable, contract/state ownership is known, relevant edge obligations are visible, and the builder can name the tests/evidence that will prove the change. “There is a file to edit” is not readiness.

**Done** means the implementation satisfies its contracts, failure behavior is exercised, migration/recovery/rollback is defined where durable state changes, observability exists, evidence is attached, and the signed accountability transition is valid. “Code merged” is not done by itself.

Each MBW wave now carries machine-readable `definition_of_ready`, `definition_of_done`, `handoff_outputs`, `review_questions`, and `gating_vertical_slices`.

## Handoff law

A wave hands downstream **contracts and proven capabilities**, not assumptions. Every handoff must make explicit:

- what is authoritative;
- what is derived/cache/projection state;
- which failure states are expected and recoverable;
- what callers may rely on;
- what remains experimental or unverified;
- which critical/high risks are still open;
- which evidence refs demonstrate the advertised behavior.

Downstream work may prototype against an incomplete upstream wave only when the dependency contract is stable enough and the incomplete behavior is represented as an explicit gap. Prototype success never upgrades the upstream wave’s completion state.
