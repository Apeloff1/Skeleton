# Masterplan Engineering Pass

Engineering pass: **v1.0.0**  
Scope: **depth-only; no new top-level volume beyond VOL-420**  
Machine contract: [`machine/ai_engineering_pass.json`](../../machine/ai_engineering_pass.json)

## Purpose

The masterplan already has broad architecture, build waves, edge-case ownership and signed accountability. This pass converts the remaining systems-engineering ambiguity into explicit proof obligations. The goal is not more architecture surface; it is to make implementation packets rejectable when contracts, budgets, failure semantics or evidence are underspecified.

The canonical closure chain is:

```text
requirement
-> interface
-> authoritative state + invariant
-> authority/trust rule
-> failure model
-> quantitative budget
-> implementation
-> executable test/eval
-> fault/recovery evidence
-> telemetry
-> migration + rollback
-> reproducibility record
-> independent verification
-> signed accountability
```

Skipping a link creates a visible engineering gap. A merged file, passing happy path, benchmark claim or green aggregate workflow cannot substitute for a missing link.

## Mandatory engineering dimensions

| ID | Dimension | Engineering law |
| --- | --- | --- |
| ENG-REQ | Requirement testability | Every requirement must be falsifiable or have an explicit evidence method. |
| ENG-IFACE | Interface ownership | Every cross-component interaction names producer, consumer, schema/version and compatibility policy. |
| ENG-STATE | State authority | Authoritative state, projections, transitions and concurrency semantics must be explicit. |
| ENG-AUTH | Authority and trust | Identity, capability, policy, trust labels and privilege boundaries survive normalization and delegation. |
| ENG-FAIL | Failure containment | Timeout, retry, partial failure, overload and dependency failure behavior is bounded and testable. |
| ENG-REC | Recovery | Checkpoint, replay, rollback, restore, compensation and terminal-state behavior are defined where applicable. |
| ENG-NFR | Quantitative budgets | Applicable latency, throughput, durability, availability, resource, cost and quality budgets have units, environment and measurement method before production promotion. |
| ENG-CAP | Capacity and backpressure | Queues, concurrency, memory/storage growth and fan-out have explicit ceilings and load-shed behavior. |
| ENG-COMPAT | Compatibility and migration | Schema/API/config/storage/model compatibility, migration and rollback windows are declared. |
| ENG-OBS | Observability | Critical transitions, denials, retries, degradation and recovery emit reconstructable telemetry. |
| ENG-TEST | Executable verification | Unit/property/contract/integration/fault/recovery tests cover the declared invariants. |
| ENG-EVAL | Evaluation | Probabilistic capabilities have versioned datasets, baselines, budgets and acceptance thresholds. |
| ENG-REPRO | Reproducibility | Build/test/eval evidence records code, config, dependency, data/model and environment identity. |
| ENG-DEPLOY | Release and rollback | Promotion, canary, rollback and incompatibility stop conditions are explicit. |
| ENG-OWN | Ownership and impact | Code, schema, config, tests, runbooks and change-impact triggers have accountable owners. |

## Quantitative budget law

The masterplan deliberately does **not** invent universal latency, throughput, availability, cost or quality numbers. Those values depend on capability, hardware, workload and risk. Before a package is promoted beyond scaffolded/experimental maturity, every applicable budget class must be bound to a concrete threshold with a unit, workload, environment, measurement method, owner and waiver policy.

A production claim requires measured evidence against the bound threshold. “Fast”, “reliable”, “cheap”, “low latency” or “high quality” without a measurement contract is not an engineering acceptance criterion.

## Compatibility and migration law

Any cross-boundary schema, API, config, storage, model or protocol change must state:

- additive versus breaking semantics;
- reader/writer compatibility;
- mixed-version behavior;
- migration order;
- rollback window;
- restore behavior for one-way data transforms;
- cache/index invalidation;
- evidence that old and new versions cannot silently disagree on authority.

A distributed upgrade must never assume all producers and consumers change atomically.

## Failure and recovery law

Every applicable package must model dependency failure, timeout, duplicate/replay, overload, partial completion, cancellation and restart. Side-effecting packages additionally prove idempotency or compensation. Durable-state packages prove crash recovery and restore. Distributed packages prove stale-worker fencing and partition behavior. Probabilistic packages prove bounded retry/revision and safe degraded modes.

## Work-package engineering ledger

| Work package | Wave | Engineering focus | Required proof |
| --- | --- | --- | --- |
| WP-W00 Architecture authority | MBW-00 | one authority order; no undeclared production root; target/current drift recorded | contract, mutation, architecture fitness |
| WP-W01 Contract primitives | MBW-00 | canonical normalization; stable identity; explicit compatibility | schema, property, compatibility, fuzz |
| WP-W02 Kernel/lifecycle | MBW-01 | terminal-state finality; deterministic lifecycle; bounded shutdown | state-machine, integration, fault injection |
| WP-W03 Durable state | MBW-01 | durable state is authority; atomicity boundaries explicit; read-your-write where promised | transaction, crash recovery, migration, property |
| WP-W04 Events | MBW-01 | idempotent consumption; ordering semantics explicit; replay cannot duplicate effects | property, replay, fault injection, integration |
| WP-W05 Model runtime | MBW-02 | provider objects stop at adapter; cancellation propagates; output validation | contract, integration, cancellation, fault injection |
| WP-W06 Model routing | MBW-02 | routing respects authority/budget; deterministic tie rules; fallback bounded | simulation, policy, load, regression |
| WP-W07 Memory | MBW-02 | writes require policy; provenance retained; deletion/tombstone semantics explicit | policy, lifecycle, adversarial, migration |
| WP-W08 Retrieval | MBW-02 | authorization at query time; provenance on result; stale index detectable | retrieval eval, access-control, migration, fault |
| WP-W09 Knowledge/evidence | MBW-02 | contradictions coexist; temporal/scope qualifiers preserved; source immutable | graph property, provenance, temporal eval |
| WP-W10 Context compiler | MBW-02 | instruction authority preserved; untrusted text cannot self-promote; truncation policy deterministic | adversarial, property, token-budget, regression |
| WP-W11 Cognitive runtime | MBW-04 | all loops bounded; hidden reasoning not required for replay; budgets propagate | simulation, long-horizon, budget, adversarial |
| WP-W12 Planning | MBW-04 | acyclic executable graph; terminal behavior exists; preconditions enforced | static analysis, property, simulation |
| WP-W13 Tools | MBW-03 | schema validation before action; idempotency/compensation; exact resource authorization | sandbox, contract, fault, side-effect replay |
| WP-W14 Policy | MBW-03 | deny-by-default; exact normalized resource check; policy version bound to decision | policy mutation, adversarial, authorization matrix |
| WP-W15 Agent runtime | MBW-04 | child authority subset parent; identity durable; lease ownership checked | property, lease fault, integration, adversarial |
| WP-W16 Swarm | MBW-04 | bounded fan-out; single writer per conflict domain; disagreement evidence-based | simulation, concurrency, chaos, long-horizon |
| WP-W17 Verification | MBW-03 | verification separate from confidence; evidence immutable; high-impact acceptance independent | independent verifier, deterministic checks, adversarial |
| WP-W18 Evaluation | MBW-06 | versioned data/config; contamination tracked; uncertainty reported | benchmark, statistical, contamination, reproducibility |
| WP-W19 Resilience | MBW-01 | retry bounded; jitter/backoff; failure domains isolated | chaos, soak, fault injection, recovery drill |
| WP-W20 Security | MBW-03 | least authority; secrets never become model data by default; tenant boundaries enforced | threat-model tests, fuzz, sandbox, penetration |
| WP-W21 Observability | MBW-05 | operation reconstructable; telemetry bounded; sensitive data classified | telemetry contract, load, redaction, replay reconstruction |
| WP-W22 API/streaming | MBW-05 | terminal finality; replay/resync; slow client bounded | API contract, reconnect, load, race |
| WP-W23 Product | MBW-05 | UI never authoritative; blockers/warnings visible; destructive action confirmed | e2e, accessibility, concurrency, offline/reconnect |
| WP-W24 Desktop | MBW-05 | least local privilege; platform path/process semantics explicit; safe shutdown | platform matrix, lifecycle, upgrade, security |
| WP-W25 Installer | MBW-07 | verified artifacts; atomic update boundary; rollback compatibility proven | clean-machine, upgrade, rollback, supply-chain |
| WP-W26 Research | MBW-06 | source lineage immutable; retractions propagate; research cannot promote itself | replication, provenance, methodology review |
| WP-W27 Forge | MBW-06 | candidate isolation; no direct production mutation; champion baseline fixed | sandbox, comparison, adversarial, reproducibility |
| WP-W28 Learning | MBW-06 | feedback provenance; no silent online authority change; rollback target retained | offline eval, shadow/canary, drift, adversarial |
| WP-W29 Distributed runtime | MBW-07 | fencing tokens; topology/resource budgets; no split-brain writer | distributed fault, partition, load, soak |
| WP-W30 Production hardening | MBW-07 | promotion evidence complete; rollback executable; operational ownership explicit | release rehearsal, DR drill, soak, security review |

## Engineering promotion gates

**E0 — Requirement gate.** Requirements are falsifiable; acceptance method and accountable owner are named.

**E1 — Contract/state gate.** Cross-boundary interfaces, schema/version rules, authoritative state, transitions, concurrency and permission boundaries are explicit.

**E2 — Failure/recovery gate.** Principal failure modes, retry ceilings, partial-failure semantics, recovery/rollback and terminal states are testable.

**E3 — Budget/capacity gate.** Applicable NFR budgets are numerically bound, queues/fan-out/storage growth have ceilings, and overload behavior is intentional.

**E4 — Integration/compatibility gate.** Mixed-version behavior, migrations, rollback, dependency contracts and change-impact triggers are covered.

**E5 — Evidence/observability gate.** Tests/evals/fault runs emit reconstructable evidence tied to git SHA, config, environment and telemetry.

**E6 — Production gate.** Release/canary/rollback/DR evidence exists, high-impact edge obligations are closed or explicitly accepted, and signed independent verification is complete.

Gates are cumulative. A later green gate never erases a failed earlier gate.

## Change-impact triggers

An engineering re-review is mandatory when a change alters any public/cross-boundary schema or config; authoritative state/lifecycle; trust/permission boundary; retry, recovery or idempotency semantics; quantitative budget/SLO assumption; persistent representation; provider/model compatibility; installer/update behavior; or distributed placement/fencing behavior.

The review must identify affected producers, consumers, migrations, tests/evals, runbooks, telemetry and rollback paths before promotion.

## Evidence integrity

Planned tests and planned evaluations remain design intent. They do not count as passing evidence. Evidence must bind at least git SHA, concrete artifact or run reference, configuration identity, environment identity, UTC timestamp, result and verifier/automation identity. Re-running the same generator is not independent verification.

## Engineering stop conditions

Promotion stops when any of the following is true:

- a cross-boundary interface lacks an owner/version/compatibility rule;
- authoritative and projected state are ambiguous;
- a retry/replay can duplicate an external effect;
- cancellation or restart can violate terminal finality;
- a queue, fan-out, memory/store or log stream can grow without an explicit bound;
- a security decision is made on a resource representation different from the executed resource;
- a migration cannot explain mixed-version behavior or rollback/restore;
- a performance/reliability claim has no numeric measurement contract;
- an evaluation cannot be reproduced from code/config/data/model/environment identity;
- an aggregate green workflow hides an unresolved critical/high obligation;
- production promotion lacks executable rollback and independent evidence.

## Relationship to the existing masterplan

This document is a depth overlay for Sections 21–24 of `MASTER_PLAN.md`. It does not change architecture authority, does not supersede `machine/architecture.json`, and does not create a new completion mechanism. Completion remains derived from the signed accountability ledger.

The engineering overlay exists to make “ready to build”, “implemented”, “verified”, “hardened” and “production” increasingly expensive claims, each backed by stronger machine-checkable proof.
