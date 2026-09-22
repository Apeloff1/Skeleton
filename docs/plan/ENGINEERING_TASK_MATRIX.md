# Engineering Task Propagation Matrix

Matrix version: **1.0.0**

Machine contract: [`machine/ai_engineering_task_matrix.json`](../../machine/ai_engineering_task_matrix.json)

Source engineering contract: [`machine/ai_engineering_pass.json`](../../machine/ai_engineering_pass.json)

## Purpose

The systems-engineering pass defines obligations at W00–W30. The atomic build queue is where work actually executes. This matrix closes the gap between those layers by deriving engineering obligations for every AIQ task from its `work_package_refs`.

The inheritance rule is intentionally mechanical:

```text
AIQ task
-> work_package_refs
-> engineering profiles
-> union(required dimensions)
-> union(NFR budget classes)
-> union(failure/recovery obligations)
-> wave proof requirements
-> executable evidence
-> independent verification
-> signed accountability
```

A task cannot silently drop an obligation because its local acceptance list is shorter than the owning work package's engineering contract.

## Completion semantics

Existing AIQ completion/accountability state is preserved. This matrix does **not** retroactively falsify signed historical completion. Instead it separates two claims:

- **task completion** — the atomic queue item reached its existing done/accountability state;
- **engineering-strong promotion** — the owning capability may claim verified, hardened, or production status.

The second claim requires the engineering pass. A completed AIQ item with empty engineering evidence remains valid as historical task completion but cannot be cited as sufficient engineering proof for strong capability promotion.

## Mandatory propagation rules

- Every AIQ task references at least one valid engineering profile.
- Every referenced work package resolves to exactly one master-build wave owner.
- Required dimensions are the exact union of the referenced profiles.
- NFR budget classes, evidence modes, failure modes, recovery requirements, and change-impact triggers are inherited, never hand-curated downward.
- An obligation may be marked not applicable only through a reviewable disposition; omission is not a disposition.
- Planned evidence is not passing evidence.
- Engineering evidence must remain bound to git SHA/config/environment identity and the existing signed-accountability system.

## Task ledger

| Task | Stage | WPs | Waves | Dimensions | Budget classes | Current engineering gate |
| --- | ---: | --- | --- | ---: | --- | --- |
| AIQ-S0-STATE-01 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-STATE-02 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-STATE-03 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-01 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-02 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-03 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-COST-01 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-COST-02 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-COST-03 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-PROV-01 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S0-PROV-02 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S0-PROV-03 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S1-CONV-01 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-CONV-02 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-CONV-03 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-MEM-01 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-MEM-02 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-MEM-03 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-01 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-02 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-03 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S2-CTX-01 | 2 | WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-CTX-02 | 2 | WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-CTX-03 | 2 | WP-W10 | MBW-02 | 15 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-01 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-02 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-03 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S3-VER-01 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S3-VER-02 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S3-VER-03 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-01 | 4 | WP-W11 | MBW-04 | 15 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-02 | 4 | WP-W11 | MBW-04 | 15 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-03 | 4 | WP-W11 | MBW-04 | 15 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-01 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-02 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-03 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-01 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-02 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-03 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-01 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-02 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-03 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |

## Required implementation packet

Before an AIQ task is ready for engineering review, its implementation packet must identify:

1. the exact inherited engineering profile references;
2. every required engineering dimension and its disposition;
3. bound quantitative budgets for applicable budget classes;
4. interface/schema/version and state-authority impacts;
5. principal failure modes and recovery/rollback strategy;
6. executable tests/evals/fault or recovery evidence;
7. observability needed to reconstruct the operation;
8. compatibility/migration/mixed-version behavior;
9. change-impact targets;
10. evidence references and independent-verification/accountability links.

## Fail-closed rules

Validation fails if a task is missing, references an unknown work package, has a wave mismatch, drops a dimension or budget inherited from its profiles, or claims an engineering gate state that is not evidence-pending while its evidence/budget bindings are empty.

This matrix is derived depth. It does not add a new architecture root, work-package family, queue state, or completion authority.
