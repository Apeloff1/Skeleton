# Engineering Task Propagation Matrix

Matrix version: **1.1.0**

Machine contract: [`machine/ai_engineering_task_matrix.json`](../../machine/ai_engineering_task_matrix.json)

Engineering source: [`machine/ai_engineering_pass.json`](../../machine/ai_engineering_pass.json)

Adversarial source: [`machine/ai_adversarial_closure.json`](../../machine/ai_adversarial_closure.json)

## Purpose

The systems-engineering and adversarial closure passes define obligations at W00–W30. The atomic build queue is where work actually executes. This matrix closes the gap between those layers by deriving both engineering and cross-condition obligations for every AIQ task from its `work_package_refs`.

```text
AIQ task
-> work_package_refs
-> engineering profiles
-> adversarial WP coverage
-> union(dimensions + budgets + failure/recovery)
-> union(adversarial axes + compound campaigns)
-> implementation packet
-> executable evidence
-> independent verification
-> signed accountability
```

A task cannot silently drop an obligation because its local acceptance list is shorter than the owning work packages' contracts.

## Completion semantics

Existing AIQ completion/accountability state is preserved. This matrix does not retroactively falsify signed historical completion. It separates task completion from engineering-strong capability promotion.

A completed AIQ item with pending engineering/adversarial evidence remains valid as historical task completion but cannot be cited as sufficient proof for `verified`, `hardened`, or `production` maturity.

## Mandatory propagation rules

- Every AIQ task references at least one valid engineering profile.
- Every referenced work package resolves to exactly one master-build wave owner.
- Engineering dimensions and NFR budget classes are the exact unions of the referenced profiles.
- Adversarial closure axes are the exact union of `work_package_coverage` for the referenced packages.
- Compound campaigns are inherited when any referenced work package participates in the campaign.
- Evidence modes, failure modes, recovery requirements, stop conditions, and change-impact triggers are inherited rather than hand-curated downward.
- An obligation may be marked not applicable only through a reviewable disposition; omission is not a disposition.
- Planned evidence is not passing evidence.
- Strong promotion requires both engineering evidence and ADV-E0..ADV-E5 closure where applicable.

## Task ledger

| Task | Stage | WPs | Waves | Eng. dims | Adv. axes | Campaigns | Budget classes | Gate |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- | --- |
| AIQ-S0-STATE-01 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | 15 | 6 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-STATE-02 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | 15 | 6 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-STATE-03 | 0 | WP-W03, WP-W04 | MBW-01 | 13 | 15 | 6 | durability, recovery_point, recovery_time, storage_growth, transaction_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-01 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | 23 | 7 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-02 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | 23 | 7 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-GOV-03 | 0 | WP-W00, WP-W03, WP-W07, WP-W08, WP-W09 | MBW-00, MBW-01, MBW-02 | 15 | 23 | 7 | change_failure_rate, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, plan_drift, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, validation_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S0-COST-01 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | 16 | 2 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-COST-02 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | 16 | 2 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-COST-03 | 0 | WP-W06, WP-W11 | MBW-02, MBW-04 | 15 | 16 | 2 | context_or_memory_budget, cost, fanout, latency, quality, recovery_time, step_budget, throughput, wall_clock | obligations_bound_evidence_pending |
| AIQ-S0-PROV-01 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | 15 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S0-PROV-02 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | 15 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S0-PROV-03 | 0 | WP-W05, WP-W06 | MBW-02 | 15 | 15 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S1-CONV-01 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | 23 | 9 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-CONV-02 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | 23 | 9 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-CONV-03 | 1 | WP-W03, WP-W04, WP-W10, WP-W11 | MBW-01, MBW-02, MBW-04 | 15 | 23 | 9 | context_or_memory_budget, cost, durability, fanout, latency, quality, recovery_point, recovery_time, step_budget, storage_growth, throughput, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-MEM-01 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | 18 | 3 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-MEM-02 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | 18 | 3 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-MEM-03 | 1 | WP-W07, WP-W08, WP-W09, WP-W10 | MBW-02 | 15 | 18 | 3 | context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, latency, quality, recovery_point, recovery_time, storage_growth, throughput, transaction_latency, verification_latency | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-01 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | 23 | 2 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-02 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | 23 | 2 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S1-TOOL-03 | 1 | WP-W11, WP-W13, WP-W14 | MBW-03, MBW-04 | 15 | 23 | 2 | authorization_latency, cost, fanout, recovery_time, sandbox_resource, side_effect_rate, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S2-CTX-01 | 2 | WP-W10 | MBW-02 | 15 | 16 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-CTX-02 | 2 | WP-W10 | MBW-02 | 15 | 16 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-CTX-03 | 2 | WP-W10 | MBW-02 | 15 | 16 | 2 | context_or_memory_budget, cost, latency, quality, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-01 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | 19 | 2 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-02 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | 19 | 2 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S2-PROTO-03 | 2 | WP-W01, WP-W05 | MBW-00, MBW-02 | 15 | 19 | 2 | compatibility_window, context_or_memory_budget, cost, latency, quality, schema_error_rate, serialization_cost, throughput | obligations_bound_evidence_pending |
| AIQ-S3-VER-01 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | 20 | 3 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S3-VER-02 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | 20 | 3 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S3-VER-03 | 3 | WP-W09, WP-W11, WP-W17 | MBW-02, MBW-03, MBW-04 | 15 | 20 | 3 | cost, evidence_freshness, false_accept_rate, fanout, recovery_time, step_budget, storage_growth, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-01 | 4 | WP-W11 | MBW-04 | 15 | 14 | 1 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-02 | 4 | WP-W11 | MBW-04 | 15 | 14 | 1 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S4-EXEC-03 | 4 | WP-W11 | MBW-04 | 15 | 14 | 1 | cost, fanout, recovery_time, step_budget, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-01 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-02 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S5-ENG-03 | 5 | WP-W02, WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, availability, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, resource_ceiling, startup_shutdown_latency, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-01 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-02 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S6-STREAM-03 | 6 | WP-W04, WP-W11, WP-W22 | MBW-01, MBW-04, MBW-05 | 15 | 23 | 6 | accessibility, cost, durability, fanout, latency, memory_ceiling, reconnect_budget, recovery_point, recovery_time, step_budget, storage_growth, transaction_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-01 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | 24 | 10 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-02 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | 24 | 10 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |
| AIQ-S7-E2E-03 | 7 | WP-W00, WP-W01, WP-W02, WP-W03, WP-W04, WP-W05, WP-W06, WP-W07, WP-W08, WP-W09, WP-W10, WP-W11 | MBW-00, MBW-01, MBW-02, MBW-04 | 15 | 24 | 10 | availability, change_failure_rate, compatibility_window, context_or_memory_budget, cost, durability, evidence_freshness, false_accept_rate, fanout, latency, plan_drift, quality, recovery_point, recovery_time, resource_ceiling, schema_error_rate, serialization_cost, startup_shutdown_latency, step_budget, storage_growth, throughput, transaction_latency, validation_latency, verification_latency, wall_clock | obligations_bound_evidence_pending |

## Required implementation packet

Before an AIQ task is ready for engineering review, its packet must identify inherited engineering profiles, all engineering dimensions and adversarial axes, applicable compound campaigns, bound quantitative budgets, interface/state impacts, failure/recovery behavior, executable tests/evals/fault evidence, observability, migration/compatibility behavior, change-impact targets, and evidence/accountability links.

## Fail-closed rules

Validation fails if a task is missing, references an unknown work package, has a wave mismatch, drops an inherited engineering dimension/budget, drops an adversarial closure axis/campaign, or claims an evidence-complete gate while required evidence bindings are empty.

This matrix is derived depth. It adds no architecture root, work-package family, queue completion state, or alternate authority.
