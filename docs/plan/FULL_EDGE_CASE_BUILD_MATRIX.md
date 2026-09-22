# Full W00–W30 Edge / Historical Construction Matrix

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine contract: [`machine/ai_full_edge_case_matrix.json`](../../machine/ai_full_edge_case_matrix.json)

Source catalogue: [`EDGE_CASES_HISTORICAL.md`](EDGE_CASES_HISTORICAL.md)

P0 detailed matrix: [`P0_EDGE_CASE_BUILD_MATRIX.md`](P0_EDGE_CASE_BUILD_MATRIX.md)

## Result

All **240** catalog entries now have at least one work-package owner across W00–W30.

- Critical: **36**
- High: **21**
- Medium: **119**
- Historical/reference: **64**
- Orphaned entries after mapping: **0**
- Work packages: **31**

## Hardening law

A work package can be implemented before every mapped failure mode has passing evidence. It cannot be called **hardened/production** while applicable critical/high cases are neither:

1. backed by executable evidence, nor
2. recorded as explicit accepted risks with owner, rationale, compensating controls and review trigger.

## Recommended evidence modes

The catalog now classifies cases into executable modes including property tests, fuzzing, negative/adversarial tests, fault injection, recovery drills, platform tests, E2E, integration, adversarial evals and design review.

## Full package coverage

| WP | Package | Historical | Edge | Obscure | Critical | High | Evidence modes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| WP-W00 | Architecture Authority | 5 | 6 | 5 | 0 | 0 | see P0 detailed matrix |
| WP-W01 | Contract Primitives | 6 | 17 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W02 | Kernel & Lifecycle | 5 | 7 | 4 | 0 | 0 | see P0 detailed matrix |
| WP-W03 | Durable State | 8 | 16 | 5 | 0 | 0 | see P0 detailed matrix |
| WP-W04 | Events & Streaming Ledger | 5 | 9 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W05 | Model Runtime | 5 | 10 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W06 | Model Routing | 4 | 8 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W07 | Memory | 7 | 6 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W08 | Retrieval | 4 | 10 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W09 | Knowledge & Evidence | 5 | 9 | 4 | 0 | 0 | see P0 detailed matrix |
| WP-W10 | Context Compiler | 4 | 9 | 3 | 0 | 0 | see P0 detailed matrix |
| WP-W11 | Cognitive Runtime | 12 | 23 | 7 | 0 | 0 | see P0 detailed matrix |
| WP-W12 | Planning | 22 | 7 | 1 | 0 | 4 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, recovery_drill |
| WP-W13 | Tools | 13 | 34 | 6 | 21 | 4 | design_review, fault_injection, property, adversarial_eval, integration, adversarial, negative_test, fuzz, platform_test, recovery_drill, e2e, regression |
| WP-W14 | Policy | 7 | 21 | 5 | 16 | 1 | design_review, adversarial_eval, integration, adversarial, negative_test, property, fuzz, fault_injection, recovery_drill, regression, e2e |
| WP-W15 | Agent Runtime | 9 | 6 | 1 | 1 | 1 | design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, regression |
| WP-W16 | Swarm | 16 | 11 | 5 | 0 | 4 | design_review, fault_injection, property, adversarial_eval, integration, fuzz, regression, recovery_drill |
| WP-W17 | Verification | 8 | 14 | 8 | 2 | 3 | design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, recovery_drill |
| WP-W18 | Evaluation | 9 | 14 | 4 | 2 | 5 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, adversarial, negative_test, regression, recovery_drill, platform_test |
| WP-W19 | Resilience | 10 | 32 | 10 | 1 | 8 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, regression, recovery_drill, platform_test, adversarial, negative_test, e2e |
| WP-W20 | Security | 7 | 40 | 6 | 36 | 3 | design_review, adversarial_eval, integration, adversarial, negative_test, property, fuzz, fault_injection, recovery_drill, platform_test, e2e, regression |
| WP-W21 | Observability | 4 | 8 | 5 | 1 | 1 | design_review, fault_injection, property, adversarial_eval, integration, adversarial, negative_test, platform_test, fuzz, regression |
| WP-W22 | API & Streaming | 5 | 28 | 3 | 2 | 2 | design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, e2e, regression, platform_test |
| WP-W23 | Product | 3 | 17 | 0 | 1 | 1 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, e2e, adversarial, negative_test, platform_test |
| WP-W24 | Desktop | 3 | 7 | 0 | 3 | 0 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, adversarial, negative_test, platform_test, e2e |
| WP-W25 | Installer | 2 | 8 | 2 | 0 | 7 | property, fuzz, recovery_drill, integration, fault_injection, platform_test, adversarial_eval, design_review, e2e |
| WP-W26 | Research | 42 | 9 | 2 | 1 | 2 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, regression, adversarial, negative_test, platform_test, e2e |
| WP-W27 | Forge | 5 | 11 | 3 | 6 | 3 | design_review, adversarial_eval, integration, adversarial, negative_test, recovery_drill, platform_test, fault_injection, property, regression, e2e, fuzz |
| WP-W28 | Learning | 5 | 6 | 0 | 0 | 1 | design_review, adversarial_eval, integration, fault_injection, property, recovery_drill |
| WP-W29 | Distributed Runtime | 21 | 49 | 12 | 2 | 9 | design_review, adversarial_eval, integration, fault_injection, property, fuzz, e2e, adversarial, negative_test, platform_test, regression, recovery_drill |
| WP-W30 | Production Hardening | 9 | 26 | 11 | 5 | 9 | design_review, adversarial_eval, integration, fault_injection, property, recovery_drill, fuzz, adversarial, negative_test, regression, platform_test, e2e |

## W12–W30 construction overlays

### WP-W12 — Planning

**Objective:** Plan DAGs, preconditions/effects, static analysis, simulation, replanning and stopping policies.

**Paths:** `skeleton/intelligence`, `skeleton/contracts`, `skeleton/planning`, `machine/ai_app_construction.json`

**Mapped cases:** 30 total; 0 critical; 4 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, recovery_drill

**Historical:** `HIST-AI-001`, `HIST-AI-002`, `HIST-AI-004`, `HIST-AI-009`, `HIST-AI-011`, `HIST-AI-012`, `HIST-AI-013`, `HIST-AI-014`, `HIST-AI-018`, `HIST-AI-039`, `HIST-AI-040`, `HIST-SYS-002`, `HIST-SYS-003`, `HIST-AI-017`, `HIST-AI-021`, `HIST-AI-031`, `HIST-AI-036`, `HIST-AI-037`, `HIST-AI-038`, `HIST-SYS-010`, `HIST-SYS-026`, `HIST-SYS-030`

**Edge:** `EDGE-DIST-020`, `EDGE-DIST-021`, `EDGE-AI-028`, `EDGE-AI-036`, `EDGE-AI-020`, `EDGE-AI-027`, `EDGE-DATA-008`

**Obscure:** `OBSCURE-030`


### WP-W13 — Tools

**Objective:** Typed tool manifests, execution receipts, sandboxing, postconditions, idempotency and compensation.

**Paths:** `skeleton/skills`, `backend/services/tool_registry.py`, `skeleton/contracts`

**Mapped cases:** 53 total; 21 critical; 4 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, adversarial, negative_test, fuzz, platform_test, recovery_drill, e2e, regression

**Historical:** `HIST-SYS-009`, `HIST-SYS-010`, `HIST-SYS-023`, `HIST-AI-002`, `HIST-AI-007`, `HIST-AI-019`, `HIST-AI-020`, `HIST-AI-027`, `HIST-SYS-002`, `HIST-SYS-006`, `HIST-SYS-019`, `HIST-SYS-020`, `HIST-SYS-024`

**Edge:** `EDGE-DIST-006`, `EDGE-AI-002`, `EDGE-AI-014`, `EDGE-AI-015`, `EDGE-AI-031`, `EDGE-AI-032`, `EDGE-AI-037`, `EDGE-AI-039`, `EDGE-AI-040`, `EDGE-SEC-002`, `EDGE-SEC-003`, `EDGE-SEC-004`, `EDGE-SEC-005`, `EDGE-SEC-006`, `EDGE-SEC-007`, `EDGE-SEC-008`, `EDGE-SEC-016`, `EDGE-SEC-017`, `EDGE-SEC-018`, `EDGE-SEC-019`, `EDGE-DIST-011`, `EDGE-DIST-021`, `EDGE-DIST-027`, `EDGE-AI-020`, `EDGE-AI-022`, `EDGE-AI-023`, `EDGE-AI-027`, `EDGE-SEC-009`, `EDGE-SEC-011`, `EDGE-SEC-012`, `EDGE-SEC-013`, `EDGE-SEC-014`, `EDGE-HW-002`, `EDGE-HW-009`

**Obscure:** `OBSCURE-004`, `OBSCURE-005`, `OBSCURE-012`, `OBSCURE-013`, `OBSCURE-024`, `OBSCURE-025`


### WP-W14 — Policy

**Objective:** Deterministic authority, approval, risk, scope and policy-version enforcement.

**Paths:** `skeleton/vault`, `skeleton/security`, `skeleton/policy`, `skeleton/intelligence/admission.py`

**Mapped cases:** 33 total; 16 critical; 1 high.

**Evidence modes:** design_review, adversarial_eval, integration, adversarial, negative_test, property, fuzz, fault_injection, recovery_drill, regression, e2e

**Historical:** `HIST-AI-005`, `HIST-AI-007`, `HIST-AI-019`, `HIST-SYS-019`, `HIST-SYS-020`, `HIST-AI-032`, `HIST-SYS-021`

**Edge:** `EDGE-CONTRACT-017`, `EDGE-AI-001`, `EDGE-AI-002`, `EDGE-AI-030`, `EDGE-AI-031`, `EDGE-AI-032`, `EDGE-SEC-001`, `EDGE-SEC-005`, `EDGE-SEC-006`, `EDGE-SEC-007`, `EDGE-SEC-020`, `EDGE-CONTRACT-010`, `EDGE-DIST-010`, `EDGE-DIST-019`, `EDGE-AI-011`, `EDGE-AI-013`, `EDGE-AI-018`, `EDGE-AI-038`, `EDGE-SEC-011`, `EDGE-DATA-010`, `EDGE-UX-009`

**Obscure:** `OBSCURE-012`, `OBSCURE-022`, `OBSCURE-024`, `OBSCURE-018`, `OBSCURE-023`


### WP-W15 — Agent Runtime

**Objective:** Agent identity, bounded lifecycle, handoff, delegation and durable turn state.

**Paths:** `skeleton/agents`, `skeleton/intelligence`, `skeleton/contracts`

**Mapped cases:** 16 total; 1 critical; 1 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, regression

**Historical:** `HIST-AI-006`, `HIST-AI-033`, `HIST-SYS-001`, `HIST-AI-012`, `HIST-AI-013`, `HIST-AI-014`, `HIST-AI-015`, `HIST-SYS-019`, `HIST-SYS-030`

**Edge:** `EDGE-DIST-020`, `EDGE-AI-022`, `EDGE-AI-036`, `EDGE-AI-024`, `EDGE-AI-027`, `EDGE-AI-028`

**Obscure:** `OBSCURE-026`


### WP-W16 — Swarm

**Objective:** Multi-agent leases, fencing, scheduling, conflict domains, consensus and anti-collision.

**Paths:** `skeleton/swarm`, `skeleton/agents`, `skeleton/resilience`

**Mapped cases:** 32 total; 0 critical; 4 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, fuzz, regression, recovery_drill

**Historical:** `HIST-AI-006`, `HIST-AI-011`, `HIST-AI-012`, `HIST-AI-013`, `HIST-AI-014`, `HIST-AI-015`, `HIST-AI-033`, `HIST-AI-034`, `HIST-AI-035`, `HIST-AI-036`, `HIST-AI-040`, `HIST-SYS-001`, `HIST-SYS-004`, `HIST-SYS-014`, `HIST-SYS-015`, `HIST-SYS-016`

**Edge:** `EDGE-DIST-007`, `EDGE-DIST-008`, `EDGE-DIST-020`, `EDGE-AI-023`, `EDGE-AI-024`, `EDGE-AI-025`, `EDGE-DIST-018`, `EDGE-DIST-019`, `EDGE-DIST-021`, `EDGE-DIST-022`, `EDGE-DATA-007`

**Obscure:** `OBSCURE-003`, `OBSCURE-019`, `OBSCURE-026`, `OBSCURE-027`, `OBSCURE-017`


### WP-W17 — Verification

**Objective:** Independent structural/evidence/action verification and postcondition checking.

**Paths:** `skeleton/intelligence/verification_runtime.py`, `skeleton/contracts/verification.py`, `skeleton/testing`

**Mapped cases:** 30 total; 2 critical; 3 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, recovery_drill

**Historical:** `HIST-AI-002`, `HIST-AI-019`, `HIST-AI-038`, `HIST-AI-039`, `HIST-SYS-018`, `HIST-AI-005`, `HIST-AI-025`, `HIST-AI-033`

**Edge:** `EDGE-AI-012`, `EDGE-AI-023`, `EDGE-AI-024`, `EDGE-AI-029`, `EDGE-AI-037`, `EDGE-AI-001`, `EDGE-AI-005`, `EDGE-AI-006`, `EDGE-AI-008`, `EDGE-AI-009`, `EDGE-AI-033`, `EDGE-AI-034`, `EDGE-AI-039`, `EDGE-DATA-005`

**Obscure:** `OBSCURE-012`, `OBSCURE-013`, `OBSCURE-019`, `OBSCURE-020`, `OBSCURE-014`, `OBSCURE-018`, `OBSCURE-023`, `OBSCURE-030`


### WP-W18 — Evaluation

**Objective:** Capability, agent, adversarial, contamination-aware and long-horizon evaluation.

**Paths:** `skeleton/evaluation`, `benchmarks`, `tests`

**Mapped cases:** 27 total; 2 critical; 5 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, adversarial, negative_test, regression, recovery_drill, platform_test

**Historical:** `HIST-AI-018`, `HIST-AI-030`, `HIST-SYS-003`, `HIST-SYS-014`, `HIST-SYS-015`, `HIST-SYS-016`, `HIST-AI-037`, `HIST-AI-038`, `HIST-SYS-025`

**Edge:** `EDGE-CONTRACT-001`, `EDGE-CONTRACT-005`, `EDGE-CONTRACT-009`, `EDGE-DIST-010`, `EDGE-DIST-021`, `EDGE-DIST-024`, `EDGE-AI-015`, `EDGE-AI-025`, `EDGE-AI-026`, `EDGE-AI-027`, `EDGE-AI-028`, `EDGE-AI-035`, `EDGE-AI-018`, `EDGE-HW-006`

**Obscure:** `OBSCURE-001`, `OBSCURE-019`, `OBSCURE-023`, `OBSCURE-030`


### WP-W19 — Resilience

**Objective:** Retry budgets, circuit breakers, bulkheads, chaos, recovery and dead-letter handling.

**Paths:** `skeleton/resilience`, `skeleton/frontier`, `skeleton/persistence`

**Mapped cases:** 52 total; 1 critical; 8 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, regression, recovery_drill, platform_test, adversarial, negative_test, e2e

**Historical:** `HIST-SYS-005`, `HIST-SYS-006`, `HIST-SYS-007`, `HIST-SYS-016`, `HIST-SYS-027`, `HIST-SYS-003`, `HIST-SYS-004`, `HIST-SYS-009`, `HIST-SYS-014`, `HIST-SYS-026`

**Edge:** `EDGE-CONTRACT-016`, `EDGE-CONTRACT-019`, `EDGE-DIST-001`, `EDGE-DIST-002`, `EDGE-DIST-004`, `EDGE-DIST-006`, `EDGE-DIST-008`, `EDGE-DIST-010`, `EDGE-DIST-011`, `EDGE-DIST-012`, `EDGE-DIST-013`, `EDGE-DIST-014`, `EDGE-DIST-015`, `EDGE-DIST-016`, `EDGE-DIST-017`, `EDGE-DIST-020`, `EDGE-DIST-026`, `EDGE-DIST-027`, `EDGE-DIST-028`, `EDGE-DIST-029`, `EDGE-DIST-030`, `EDGE-AI-040`, `EDGE-DATA-003`, `EDGE-DATA-005`, `EDGE-HW-001`, `EDGE-HW-003`, `EDGE-HW-006`, `EDGE-DIST-021`, `EDGE-AI-032`, `EDGE-AI-039`, `EDGE-DATA-010`, `EDGE-UX-003`

**Obscure:** `OBSCURE-001`, `OBSCURE-002`, `OBSCURE-004`, `OBSCURE-005`, `OBSCURE-006`, `OBSCURE-009`, `OBSCURE-014`, `OBSCURE-016`, `OBSCURE-008`, `OBSCURE-015`


### WP-W20 — Security

**Objective:** Identity, authorization, prompt/tool isolation, secrets, sandbox, network and supply-chain security.

**Paths:** `skeleton/vault`, `skeleton/security`, `scripts`, `machine`

**Mapped cases:** 53 total; 36 critical; 3 high.

**Evidence modes:** design_review, adversarial_eval, integration, adversarial, negative_test, property, fuzz, fault_injection, recovery_drill, platform_test, e2e, regression

**Historical:** `HIST-AI-005`, `HIST-AI-007`, `HIST-AI-019`, `HIST-SYS-019`, `HIST-SYS-020`, `HIST-SYS-021`, `HIST-SYS-024`

**Edge:** `EDGE-CONTRACT-009`, `EDGE-CONTRACT-010`, `EDGE-CONTRACT-012`, `EDGE-CONTRACT-017`, `EDGE-CONTRACT-020`, `EDGE-AI-001`, `EDGE-AI-002`, `EDGE-AI-003`, `EDGE-AI-011`, `EDGE-AI-021`, `EDGE-AI-030`, `EDGE-AI-032`, `EDGE-SEC-001`, `EDGE-SEC-002`, `EDGE-SEC-003`, `EDGE-SEC-004`, `EDGE-SEC-005`, `EDGE-SEC-006`, `EDGE-SEC-007`, `EDGE-SEC-008`, `EDGE-SEC-009`, `EDGE-SEC-010`, `EDGE-SEC-011`, `EDGE-SEC-012`, `EDGE-SEC-013`, `EDGE-SEC-014`, `EDGE-SEC-015`, `EDGE-SEC-016`, `EDGE-SEC-017`, `EDGE-SEC-018`, `EDGE-SEC-019`, `EDGE-SEC-020`, `EDGE-DATA-001`, `EDGE-DATA-002`, `EDGE-DATA-009`, `EDGE-DATA-010`, `EDGE-CONTRACT-001`, `EDGE-CONTRACT-011`, `EDGE-AI-013`, `EDGE-HW-006`

**Obscure:** `OBSCURE-010`, `OBSCURE-012`, `OBSCURE-022`, `OBSCURE-024`, `OBSCURE-025`, `OBSCURE-018`


### WP-W21 — Observability

**Objective:** Trace reconstruction, SLOs, metrics cardinality, cost/usage and incident evidence.

**Paths:** `skeleton/observability`, `backend`, `machine`

**Mapped cases:** 17 total; 1 critical; 1 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, adversarial, negative_test, platform_test, fuzz, regression

**Historical:** `HIST-SYS-013`, `HIST-AI-016`, `HIST-AI-035`, `HIST-SYS-009`

**Edge:** `EDGE-DIST-011`, `EDGE-AI-017`, `EDGE-SEC-015`, `EDGE-HW-002`, `EDGE-HW-005`, `EDGE-HW-006`, `EDGE-HW-007`, `EDGE-AI-019`

**Obscure:** `OBSCURE-001`, `OBSCURE-015`, `OBSCURE-016`, `OBSCURE-017`, `OBSCURE-021`


### WP-W22 — API & Streaming

**Objective:** Versioned API/streaming protocols, reconnect, idempotency, errors and client reconstruction.

**Paths:** `skeleton/api`, `backend/routes`, `backend/core/operation_stream_transport.py`, `frontend`

**Mapped cases:** 36 total; 2 critical; 2 high.

**Evidence modes:** design_review, fault_injection, property, adversarial_eval, integration, fuzz, adversarial, negative_test, e2e, regression, platform_test

**Historical:** `HIST-AI-006`, `HIST-AI-033`, `HIST-SYS-001`, `HIST-SYS-002`, `HIST-SYS-028`

**Edge:** `EDGE-CONTRACT-001`, `EDGE-CONTRACT-002`, `EDGE-CONTRACT-003`, `EDGE-CONTRACT-004`, `EDGE-CONTRACT-005`, `EDGE-CONTRACT-006`, `EDGE-CONTRACT-007`, `EDGE-CONTRACT-017`, `EDGE-CONTRACT-018`, `EDGE-DIST-003`, `EDGE-DIST-004`, `EDGE-DIST-005`, `EDGE-DIST-013`, `EDGE-AI-014`, `EDGE-AI-016`, `EDGE-UX-002`, `EDGE-UX-006`, `EDGE-UX-008`, `EDGE-DIST-002`, `EDGE-DIST-007`, `EDGE-DIST-012`, `EDGE-DIST-017`, `EDGE-DIST-023`, `EDGE-DIST-026`, `EDGE-DIST-027`, `EDGE-AI-017`, `EDGE-SEC-009`, `EDGE-UX-007`

**Obscure:** `OBSCURE-009`, `OBSCURE-013`, `OBSCURE-027`


### WP-W23 — Product

**Objective:** Long-running AI UX, human control, accessibility, workspaces and honest status.

**Paths:** `frontend`, `backend/routes`, `docs`

**Mapped cases:** 20 total; 1 critical; 1 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, e2e, adversarial, negative_test, platform_test

**Historical:** `HIST-AI-005`, `HIST-SYS-004`, `HIST-SYS-024`

**Edge:** `EDGE-CONTRACT-008`, `EDGE-CONTRACT-013`, `EDGE-DIST-004`, `EDGE-AI-004`, `EDGE-AI-029`, `EDGE-UX-001`, `EDGE-UX-002`, `EDGE-UX-003`, `EDGE-UX-004`, `EDGE-UX-005`, `EDGE-UX-006`, `EDGE-UX-007`, `EDGE-UX-008`, `EDGE-UX-009`, `EDGE-CONTRACT-007`, `EDGE-CONTRACT-011`, `EDGE-SEC-008`

**Obscure:** none


### WP-W24 — Desktop

**Objective:** Desktop process supervision, suspend/resume, local integration and crash recovery.

**Paths:** `desktop`, `skeleton/app`, `installer`

**Mapped cases:** 10 total; 3 critical; 0 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, adversarial, negative_test, platform_test, e2e

**Historical:** `HIST-AI-022`, `HIST-SYS-005`, `HIST-SYS-013`

**Edge:** `EDGE-CONTRACT-011`, `EDGE-SEC-008`, `EDGE-SEC-018`, `EDGE-HW-009`, `EDGE-UX-003`, `EDGE-SEC-009`, `EDGE-HW-010`

**Obscure:** none


### WP-W25 — Installer

**Objective:** Install/update/repair/uninstall integrity, platform compatibility and rollback.

**Paths:** `installer`, `skeleton/app`, `scripts`, `deploy`

**Mapped cases:** 12 total; 0 critical; 7 high.

**Evidence modes:** property, fuzz, recovery_drill, integration, fault_injection, platform_test, adversarial_eval, design_review, e2e

**Historical:** `HIST-AI-002`, `HIST-SYS-025`

**Edge:** `EDGE-DATA-006`, `EDGE-DATA-007`, `EDGE-HW-009`, `EDGE-HW-010`, `EDGE-DIST-025`, `EDGE-AI-019`, `EDGE-DATA-002`, `EDGE-UX-005`

**Obscure:** `OBSCURE-029`, `OBSCURE-010`


### WP-W26 — Research

**Objective:** Literature ingestion, claim/evidence graphs, replication, statistics and research integrity.

**Paths:** `research`, `skeleton/research`, `benchmarks`, `docs/plan`

**Mapped cases:** 53 total; 1 critical; 2 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, regression, adversarial, negative_test, platform_test, e2e

**Historical:** `HIST-AI-001`, `HIST-AI-002`, `HIST-AI-003`, `HIST-AI-004`, `HIST-AI-005`, `HIST-AI-006`, `HIST-AI-007`, `HIST-AI-008`, `HIST-AI-009`, `HIST-AI-010`, `HIST-AI-011`, `HIST-AI-012`, `HIST-AI-013`, `HIST-AI-014`, `HIST-AI-015`, `HIST-AI-016`, `HIST-AI-017`, `HIST-AI-018`, `HIST-AI-019`, `HIST-AI-020`, `HIST-AI-021`, `HIST-AI-022`, `HIST-AI-023`, `HIST-AI-024`, `HIST-AI-025`, `HIST-AI-026`, `HIST-AI-027`, `HIST-AI-028`, `HIST-AI-029`, `HIST-AI-030`, `HIST-AI-031`, `HIST-AI-032`, `HIST-AI-033`, `HIST-AI-034`, `HIST-AI-035`, `HIST-AI-036`, `HIST-AI-037`, `HIST-AI-038`, `HIST-AI-039`, `HIST-AI-040`, `HIST-SYS-003`, `HIST-SYS-030`

**Edge:** `EDGE-DIST-030`, `EDGE-AI-025`, `EDGE-AI-026`, `EDGE-AI-027`, `EDGE-HW-006`, `EDGE-UX-004`, `EDGE-AI-005`, `EDGE-AI-006`, `EDGE-AI-030`

**Obscure:** `OBSCURE-019`, `OBSCURE-030`


### WP-W27 — Forge

**Objective:** Candidate generation, artifact lineage, competition, champion/challenger and promotion.

**Paths:** `skeleton/forge`, `skeleton/artifact_plane`, `machine`

**Mapped cases:** 19 total; 6 critical; 3 high.

**Evidence modes:** design_review, adversarial_eval, integration, adversarial, negative_test, recovery_drill, platform_test, fault_injection, property, regression, e2e, fuzz

**Historical:** `HIST-AI-007`, `HIST-AI-018`, `HIST-AI-019`, `HIST-AI-036`, `HIST-SYS-019`

**Edge:** `EDGE-AI-035`, `EDGE-SEC-001`, `EDGE-SEC-005`, `EDGE-SEC-006`, `EDGE-SEC-007`, `EDGE-SEC-009`, `EDGE-DATA-002`, `EDGE-DATA-003`, `EDGE-DATA-004`, `EDGE-UX-010`, `EDGE-AI-025`

**Obscure:** `OBSCURE-007`, `OBSCURE-011`, `OBSCURE-029`


### WP-W28 — Learning

**Objective:** Outcome learning, curriculum, routing/retrieval adaptation and controlled self-improvement.

**Paths:** `skeleton/learning`, `skeleton/intelligence`, `benchmarks`

**Mapped cases:** 11 total; 0 critical; 1 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, recovery_drill

**Historical:** `HIST-AI-009`, `HIST-AI-011`, `HIST-AI-018`, `HIST-AI-035`, `HIST-AI-023`

**Edge:** `EDGE-DIST-020`, `EDGE-AI-028`, `EDGE-AI-035`, `EDGE-AI-036`, `EDGE-AI-033`, `EDGE-AI-034`

**Obscure:** none


### WP-W29 — Distributed Runtime

**Objective:** Workers, queues, topology-aware scheduling, distributed inference, leases and resource isolation.

**Paths:** `skeleton/resilience`, `skeleton/agents`, `skeleton/provider_runtime.py`, `deploy`, `infra`

**Mapped cases:** 82 total; 2 critical; 9 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, fuzz, e2e, adversarial, negative_test, platform_test, regression, recovery_drill

**Historical:** `HIST-AI-026`, `HIST-SYS-001`, `HIST-SYS-002`, `HIST-SYS-004`, `HIST-SYS-005`, `HIST-SYS-007`, `HIST-SYS-008`, `HIST-SYS-009`, `HIST-SYS-010`, `HIST-SYS-011`, `HIST-SYS-012`, `HIST-SYS-013`, `HIST-SYS-014`, `HIST-SYS-015`, `HIST-SYS-016`, `HIST-SYS-017`, `HIST-SYS-026`, `HIST-SYS-027`, `HIST-SYS-028`, `HIST-SYS-029`, `HIST-SYS-030`

**Edge:** `EDGE-CONTRACT-007`, `EDGE-CONTRACT-008`, `EDGE-CONTRACT-010`, `EDGE-CONTRACT-011`, `EDGE-CONTRACT-013`, `EDGE-CONTRACT-014`, `EDGE-CONTRACT-015`, `EDGE-CONTRACT-016`, `EDGE-CONTRACT-019`, `EDGE-DIST-001`, `EDGE-DIST-002`, `EDGE-DIST-003`, `EDGE-DIST-004`, `EDGE-DIST-007`, `EDGE-DIST-008`, `EDGE-DIST-009`, `EDGE-DIST-010`, `EDGE-DIST-011`, `EDGE-DIST-012`, `EDGE-DIST-013`, `EDGE-DIST-014`, `EDGE-DIST-015`, `EDGE-DIST-016`, `EDGE-DIST-017`, `EDGE-DIST-018`, `EDGE-DIST-019`, `EDGE-DIST-021`, `EDGE-DIST-022`, `EDGE-DIST-025`, `EDGE-DIST-026`, `EDGE-DIST-027`, `EDGE-DIST-028`, `EDGE-DIST-029`, `EDGE-SEC-008`, `EDGE-HW-001`, `EDGE-HW-002`, `EDGE-HW-003`, `EDGE-HW-004`, `EDGE-HW-006`, `EDGE-HW-007`, `EDGE-HW-008`, `EDGE-HW-009`, `EDGE-HW-010`, `EDGE-UX-009`, `EDGE-DIST-020`, `EDGE-AI-032`, `EDGE-SEC-020`, `EDGE-DATA-007`, `EDGE-UX-003`

**Obscure:** `OBSCURE-001`, `OBSCURE-002`, `OBSCURE-003`, `OBSCURE-008`, `OBSCURE-009`, `OBSCURE-016`, `OBSCURE-017`, `OBSCURE-027`, `OBSCURE-028`, `OBSCURE-005`, `OBSCURE-006`, `OBSCURE-010`


### WP-W30 — Production Hardening

**Objective:** Release qualification, migration, rollback, disaster recovery, SLOs, provenance and operational readiness.

**Paths:** `deploy`, `scripts`, `docs`, `machine`, `.github/workflows`

**Mapped cases:** 46 total; 5 critical; 9 high.

**Evidence modes:** design_review, adversarial_eval, integration, fault_injection, property, recovery_drill, fuzz, adversarial, negative_test, regression, platform_test, e2e

**Historical:** `HIST-AI-022`, `HIST-SYS-005`, `HIST-SYS-006`, `HIST-SYS-013`, `HIST-SYS-018`, `HIST-SYS-025`, `HIST-AI-002`, `HIST-AI-009`, `HIST-AI-023`

**Edge:** `EDGE-CONTRACT-015`, `EDGE-CONTRACT-020`, `EDGE-DIST-011`, `EDGE-AI-012`, `EDGE-AI-013`, `EDGE-AI-018`, `EDGE-AI-019`, `EDGE-AI-020`, `EDGE-AI-021`, `EDGE-AI-022`, `EDGE-AI-035`, `EDGE-AI-038`, `EDGE-SEC-010`, `EDGE-DATA-003`, `EDGE-DATA-004`, `EDGE-DATA-005`, `EDGE-DATA-006`, `EDGE-DATA-007`, `EDGE-DATA-010`, `EDGE-HW-001`, `EDGE-HW-002`, `EDGE-HW-007`, `EDGE-UX-003`, `EDGE-DIST-017`, `EDGE-DIST-028`, `EDGE-DATA-002`

**Obscure:** `OBSCURE-001`, `OBSCURE-006`, `OBSCURE-008`, `OBSCURE-014`, `OBSCURE-015`, `OBSCURE-016`, `OBSCURE-018`, `OBSCURE-021`, `OBSCURE-023`, `OBSCURE-029`, `OBSCURE-030`



## Cross-owner rule

Many failures legitimately belong to more than one package. For example, a timeout with unknown side effects belongs to tool execution, resilience, distributed execution, verification and production hardening. Multiple ownership is intentional; it prevents one layer from assuming another layer solved the problem.

## Catalog-to-evidence lifecycle

```text
catalogued
-> work-package mapped
-> dispositioned
-> test/runbook/ADR planned
-> executable evidence exists
-> evidence passing
-> accepted OR accepted-risk
-> continuously regression-protected
```
