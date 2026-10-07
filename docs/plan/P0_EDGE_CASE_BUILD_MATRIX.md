# P0 W00–W11 Edge-Case Construction Matrix

Architecture lane: `PR #1904 / integration/architecture-map-v1`

Machine contract: [`machine/ai_p0_edge_case_matrix.json`](../../machine/ai_p0_edge_case_matrix.json)

Source catalogue: [`EDGE_CASES_HISTORICAL.md`](EDGE_CASES_HISTORICAL.md)

## Purpose

This matrix converts the historical/obscure/edge-case catalogue into **construction obligations for WP-W00 through WP-W11**. It is an acceptance overlay, not a replacement for `machine/ai_build_queue.json` or the functional-AI dependency graph.

A work package cannot claim edge-case closure merely because its happy-path implementation exists. Relevant cases below must be either:

- covered by executable tests/evidence;
- intentionally deferred with an explicit gap/risk owner; or
- proven inapplicable with rationale.

## Package summary

| WP | Name | Historical | Edge cases | Obscure | Exact-path bindings | Test targets |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| WP-W00 | Architecture Authority | 5 | 6 | 5 | 12 | 4 |
| WP-W01 | Contract Primitives | 6 | 17 | 3 | 6 | 6 |
| WP-W02 | Kernel & Lifecycle | 5 | 7 | 4 | 7 | 6 |
| WP-W03 | Durable State | 8 | 16 | 5 | 6 | 7 |
| WP-W04 | Events & Streaming Ledger | 5 | 9 | 3 | 8 | 8 |
| WP-W05 | Model Runtime | 5 | 10 | 3 | 7 | 8 |
| WP-W06 | Model Routing | 4 | 8 | 3 | 5 | 8 |
| WP-W07 | Memory | 7 | 6 | 3 | 6 | 7 |
| WP-W08 | Retrieval | 4 | 10 | 3 | 4 | 8 |
| WP-W09 | Knowledge & Evidence | 5 | 9 | 4 | 4 | 6 |
| WP-W10 | Context Compiler | 4 | 9 | 3 | 5 | 6 |
| WP-W11 | Cognitive Runtime | 12 | 23 | 7 | 7 | 10 |

## Construction rule

```text
catalog case
  -> mapped P0 work package
  -> invariant
  -> exact owner/path
  -> executable regression/property/fuzz/fault test
  -> acceptance evidence
```

A `planned:` test target is an explicit construction deliverable, not evidence that the test already exists.

## WP-W00 — Architecture Authority

**Objective:** Make the human/machine architecture, breadth freeze, traceability and drift rules authoritative and fail-closed.

**Exact target paths**

- `docs/plan/MASTER_INDEX.md`
- `docs/plan/MASTER_PLAN.md`
- `docs/plan/EDGE_CASES_HISTORICAL.md`
- `machine/ai_master_plan.json`
- `machine/ai_edge_case_catalog.json`
- `machine/architecture.json`
- `scripts/check_ai_master_plan.py`
- `scripts/check_ai_edge_case_catalog.py`
- `scripts/check_architecture_map.py`
- `skeleton/testing/test_ai_master_plan.py`
- `skeleton/testing/test_ai_edge_case_catalog.py`
- `skeleton/testing/test_architecture_map.py`

**Historical mechanisms:** `HIST-SYS-018`, `HIST-SYS-019`, `HIST-SYS-022`, `HIST-SYS-023`, `HIST-SYS-025`

**Edge cases:** `EDGE-CONTRACT-008`, `EDGE-CONTRACT-009`, `EDGE-CONTRACT-010`, `EDGE-CONTRACT-019`, `EDGE-CONTRACT-020`, `EDGE-DATA-004`

**Obscure lessons:** `OBSCURE-011`, `OBSCURE-022`, `OBSCURE-023`, `OBSCURE-029`, `OBSCURE-030`

**Required invariants**

- Every target-plan artifact has one canonical identity and version.
- Human and machine planning artifacts cannot silently disagree on breadth-freeze or volume identity.
- Architecture documentation never upgrades implementation_status without executable evidence.
- Provider/runtime truth remains owned by existing fail-closed runtime contracts when target plan is ahead of implementation.
- Top-level volume creation after VOL-420 requires an explicit ADR.

**Test targets**

- `skeleton/testing/test_ai_master_plan.py::test_master_plan_machine_contract_is_complete`
- `skeleton/testing/test_ai_edge_case_catalog.py::test_edge_case_catalog_passes_validator`
- `planned:skeleton/testing/test_ai_plan_traceability.py::test_human_machine_plan_cross_links_are_bidirectional`
- `planned:skeleton/testing/test_ai_plan_traceability.py::test_no_implementation_status_without_evidence`

**Acceptance**

- 421 contiguous volumes remain addressable
- all cross-cutting catalog references resolve
- breadth freeze cannot be bypassed by undocumented top-level plans
- architecture drift is detected before runtime/build tests

## WP-W01 — Contract Primitives

**Objective:** Define stable IDs, versions, errors, budgets, authority, deadlines, cancellation, provenance and serialization semantics.

**Exact target paths**

- `skeleton/contracts/operation.py`
- `skeleton/contracts/conversation.py`
- `skeleton/contracts/context.py`
- `skeleton/contracts`
- `machine/ai_runtime_schemas.json`
- `machine/capability_interfaces.json`

**Historical mechanisms:** `HIST-AI-002`, `HIST-AI-008`, `HIST-SYS-003`, `HIST-SYS-011`, `HIST-SYS-012`, `HIST-SYS-019`

**Edge cases:** `EDGE-CONTRACT-001`, `EDGE-CONTRACT-002`, `EDGE-CONTRACT-003`, `EDGE-CONTRACT-004`, `EDGE-CONTRACT-005`, `EDGE-CONTRACT-006`, `EDGE-CONTRACT-007`, `EDGE-CONTRACT-008`, `EDGE-CONTRACT-009`, `EDGE-CONTRACT-010`, `EDGE-CONTRACT-013`, `EDGE-CONTRACT-014`, `EDGE-CONTRACT-015`, `EDGE-CONTRACT-016`, `EDGE-CONTRACT-018`, `EDGE-CONTRACT-019`, `EDGE-CONTRACT-020`

**Obscure lessons:** `OBSCURE-004`, `OBSCURE-011`, `OBSCURE-028`

**Required invariants**

- Identifiers are opaque; semantic meaning is never inferred from identifier text.
- Absent and explicit-null semantics are defined per field and preserved across serialization.
- Security-sensitive JSON rejects duplicate object keys and non-finite numbers.
- Durations use monotonic time; persisted timestamps use explicit UTC/offset semantics.
- Schema evolution has explicit compatibility policy and unknown values cannot silently become privileged defaults.
- Signing/hashing uses a canonical representation with declared algorithm/version.

**Test targets**

- `planned:skeleton/testing/test_contract_serialization_edges.py::test_duplicate_json_keys_fail_closed`
- `planned:skeleton/testing/test_contract_serialization_edges.py::test_null_and_absent_are_not_conflated`
- `planned:skeleton/testing/test_contract_serialization_edges.py::test_large_integer_round_trip_across_json_client_boundary`
- `planned:skeleton/testing/test_contract_unicode_edges.py::test_identifier_normalization_and_confusables_policy`
- `planned:skeleton/testing/test_contract_time_edges.py::test_deadline_duration_uses_monotonic_clock`
- `planned:skeleton/testing/test_contract_compatibility.py::test_unknown_enum_value_is_not_privilege_escalation`

**Acceptance**

- cross-runtime round trips preserve identity and semantics
- malformed/ambiguous encodings fail deterministically
- time and numeric boundary behavior is platform-independent
- compatibility behavior is tested rather than assumed

## WP-W02 — Kernel & Lifecycle

**Objective:** Provide deterministic bootstrap, readiness, shutdown, service ownership, cancellation propagation and runtime identity.

**Exact target paths**

- `skeleton/app/assembly.py`
- `skeleton/app/health.py`
- `skeleton/app/cli.py`
- `skeleton/__main__.py`
- `skeleton/provider_contract.py`
- `machine/manifest.json`
- `skeleton/testing/test_app_assembly.py`

**Historical mechanisms:** `HIST-SYS-001`, `HIST-SYS-002`, `HIST-SYS-005`, `HIST-SYS-018`, `HIST-SYS-022`

**Edge cases:** `EDGE-DIST-011`, `EDGE-DIST-030`, `EDGE-SEC-015`, `EDGE-SEC-016`, `EDGE-SEC-020`, `EDGE-HW-009`, `EDGE-HW-010`

**Obscure lessons:** `OBSCURE-001`, `OBSCURE-004`, `OBSCURE-015`, `OBSCURE-028`

**Required invariants**

- LIVE and READY are distinct states.
- Bootstrap fails closed when mandatory contracts/configuration are unavailable or incompatible.
- Shutdown stops admission before draining/cancelling work and closing dependencies.
- Cancellation is propagated as a protocol and never rewrites already committed side effects.
- Child processes receive only explicitly required environment/secret material.
- Suspend/resume or transient provider/network loss can transition runtime to degraded/recovering without corrupting authority state.

**Test targets**

- `skeleton/testing/test_app_assembly.py`
- `planned:skeleton/testing/test_kernel_lifecycle_edges.py::test_live_not_ready_during_partial_boot`
- `planned:skeleton/testing/test_kernel_lifecycle_edges.py::test_shutdown_orders_admission_drain_checkpoint_flush`
- `planned:skeleton/testing/test_kernel_lifecycle_edges.py::test_cancel_race_resolves_one_terminal_state`
- `planned:skeleton/testing/test_kernel_lifecycle_edges.py::test_child_process_secret_environment_is_minimal`
- `planned:skeleton/testing/test_kernel_lifecycle_edges.py::test_suspend_resume_reprobes_health`

**Acceptance**

- boot and shutdown are deterministic
- readiness reflects mandatory dependency truth
- cancellation and shutdown are race-safe
- secrets do not spread through ambient process state

## WP-W03 — Durable State

**Objective:** Make canonical mutable state transactional, recoverable, migration-safe and separable from derived indexes/caches.

**Exact target paths**

- `skeleton/persistence/operation_store.py`
- `skeleton/persistence/conversation_repository.py`
- `skeleton/persistence`
- `backend/services/database.py`
- `machine/state_topology.json`
- `docker-compose.yml`

**Historical mechanisms:** `HIST-SYS-007`, `HIST-SYS-008`, `HIST-SYS-009`, `HIST-SYS-011`, `HIST-SYS-012`, `HIST-SYS-027`, `HIST-SYS-028`, `HIST-SYS-029`

**Edge cases:** `EDGE-DIST-001`, `EDGE-DIST-006`, `EDGE-DIST-009`, `EDGE-DIST-010`, `EDGE-DIST-022`, `EDGE-DIST-023`, `EDGE-DIST-024`, `EDGE-DIST-025`, `EDGE-DATA-001`, `EDGE-DATA-002`, `EDGE-DATA-003`, `EDGE-DATA-005`, `EDGE-DATA-006`, `EDGE-DATA-007`, `EDGE-HW-001`, `EDGE-HW-002`

**Obscure lessons:** `OBSCURE-002`, `OBSCURE-006`, `OBSCURE-010`, `OBSCURE-014`, `OBSCURE-029`

**Required invariants**

- Acknowledged canonical writes survive restart according to their durability contract.
- Derived stores can be destroyed and rebuilt without inventing canonical state.
- Duplicate/replayed writes cannot multiply canonical side effects.
- Optimistic/MVCC concurrency checks protect global invariants from write skew where required.
- Migration completion is published only after post-migration validation.
- Rollback compatibility is proven before release when old code may read new state.
- Backup success is not recovery evidence until restoration is validated.

**Test targets**

- `skeleton/testing/test_operation_store.py`
- `skeleton/testing/test_conversation_repository.py`
- `planned:skeleton/testing/test_persistence_fault_windows.py::test_commit_ack_loss_replay_is_idempotent`
- `planned:skeleton/testing/test_persistence_fault_windows.py::test_partial_multi_store_failure_preserves_authoritative_source`
- `planned:skeleton/testing/test_persistence_concurrency.py::test_write_skew_invariant_is_guarded`
- `planned:skeleton/testing/test_persistence_migrations.py::test_partial_migration_does_not_publish_new_schema_version`
- `planned:skeleton/testing/test_persistence_restore.py::test_restore_then_rebuild_derived_indexes`

**Acceptance**

- canonical restore succeeds from tested backup
- derived loss is recoverable from authority
- concurrent writes preserve declared invariants
- migration/rollback behavior is executable evidence

## WP-W04 — Events & Streaming Ledger

**Objective:** Bind state transitions to durable ordered events with outbox/inbox semantics, replay, reconnect and terminal fencing.

**Exact target paths**

- `skeleton/frontier/operation_stream.py`
- `skeleton/frontier/operation_stream_store.py`
- `backend/core/operation_stream_transport.py`
- `backend/routes/operation_stream.py`
- `skeleton/testing/test_operation_stream.py`
- `skeleton/testing/test_operation_stream_store.py`
- `backend/tests/test_operation_stream_transport.py`
- `backend/tests/test_operation_stream_route.py`

**Historical mechanisms:** `HIST-SYS-001`, `HIST-SYS-002`, `HIST-SYS-011`, `HIST-SYS-012`, `HIST-SYS-013`

**Edge cases:** `EDGE-DIST-002`, `EDGE-DIST-003`, `EDGE-DIST-004`, `EDGE-DIST-005`, `EDGE-DIST-013`, `EDGE-DIST-026`, `EDGE-DIST-027`, `EDGE-DIST-028`, `EDGE-DIST-030`

**Obscure lessons:** `OBSCURE-002`, `OBSCURE-027`, `OBSCURE-028`

**Required invariants**

- Per-operation event sequence is monotonic and replayable.
- Duplicate delivery is safe; consumers are idempotent.
- Reconnect resumes from a durable cursor and detects unrecoverable gaps.
- A completed terminal event cannot precede the durable terminal result it represents.
- Outbox publication resumes after crash without losing committed events.
- Cancellation and completion races produce exactly one authoritative terminal state.

**Test targets**

- `skeleton/testing/test_operation_stream.py`
- `skeleton/testing/test_operation_stream_store.py`
- `backend/tests/test_operation_stream_transport.py`
- `backend/tests/test_operation_stream_route.py`
- `planned:skeleton/testing/test_operation_stream_faults.py::test_duplicate_and_out_of_order_delivery`
- `planned:skeleton/testing/test_operation_stream_faults.py::test_reconnect_gap_replays_from_cursor`
- `planned:skeleton/testing/test_operation_stream_faults.py::test_outbox_commit_then_publisher_crash`
- `planned:skeleton/testing/test_operation_stream_faults.py::test_terminal_event_requires_committed_result`

**Acceptance**

- replay reconstructs the same operation projection
- transport loss does not become state loss
- duplicates/order anomalies cannot corrupt state
- terminal semantics are transactionally fenced

## WP-W05 — Model Runtime

**Objective:** Normalize provider execution, structured output/tool proposals, usage, errors, cancellation and model identity behind one boundary.

**Exact target paths**

- `skeleton/provider_runtime.py`
- `skeleton/provider_contract.py`
- `backend/core/ai_provider.py`
- `backend/tests/test_ai_provider_adapter.py`
- `backend/tests/test_ai_provider_request_validation.py`
- `backend/tests/test_ai_provider_media.py`
- `skeleton/testing/test_provider_contract.py`

**Historical mechanisms:** `HIST-AI-023`, `HIST-AI-024`, `HIST-AI-025`, `HIST-AI-026`, `HIST-AI-027`

**Edge cases:** `EDGE-AI-014`, `EDGE-AI-015`, `EDGE-AI-016`, `EDGE-AI-017`, `EDGE-AI-018`, `EDGE-AI-019`, `EDGE-AI-038`, `EDGE-HW-003`, `EDGE-HW-004`, `EDGE-HW-010`

**Obscure lessons:** `OBSCURE-005`, `OBSCURE-021`, `OBSCURE-023`

**Required invariants**

- Provider-native request/result/tool objects never cross the provider boundary.
- Unknown/duplicate provider tool-call identities fail closed.
- Structured output is not committed before terminal schema validation.
- Missing provider usage is represented as unknown, never zero.
- Every result binds immutable provider/model/deployment identity when available.
- Timeout/cancellation does not falsely assert that remote execution never happened.
- GPU/runtime failure cannot reuse corrupted inference state without reinitialization.

**Test targets**

- `skeleton/testing/test_provider_contract.py`
- `backend/tests/test_ai_provider_adapter.py`
- `backend/tests/test_ai_provider_request_validation.py`
- `planned:skeleton/testing/test_provider_normalization_edges.py::test_duplicate_tool_call_ids_rejected`
- `planned:skeleton/testing/test_provider_normalization_edges.py::test_partial_structured_stream_not_committed`
- `planned:skeleton/testing/test_provider_usage_edges.py::test_missing_usage_is_unknown`
- `planned:skeleton/testing/test_provider_identity.py::test_alias_resolution_records_concrete_model_identity`
- `planned:skeleton/testing/test_provider_recovery.py::test_timeout_outcome_is_ambiguous_not_false_failure`

**Acceptance**

- provider substitution does not alter core contracts
- usage/error/refusal semantics are normalized
- reproduction evidence includes model identity
- provider failure cannot create duplicate downstream actions

## WP-W06 — Model Routing

**Objective:** Select models only after hard capability/privacy/context/reliability/budget checks, then optimize measured quality/cost/latency.

**Exact target paths**

- `skeleton/frontier/model_routing.py`
- `backend/tests/test_model_router.py`
- `skeleton/intelligence/admission.py`
- `skeleton/intelligence/admission_runtime.py`
- `skeleton/intelligence/quota.py`

**Historical mechanisms:** `HIST-AI-004`, `HIST-AI-026`, `HIST-AI-034`, `HIST-AI-040`

**Edge cases:** `EDGE-AI-018`, `EDGE-AI-019`, `EDGE-AI-020`, `EDGE-AI-021`, `EDGE-AI-023`, `EDGE-AI-024`, `EDGE-AI-025`, `EDGE-AI-026`

**Obscure lessons:** `OBSCURE-019`, `OBSCURE-021`, `OBSCURE-023`

**Required invariants**

- Fallback re-evaluates all hard constraints instead of inheriting eligibility from the failed route.
- Privacy/data-transfer constraints are hard constraints and cannot be traded for latency or cost.
- Model aliases resolve to concrete version/deployment evidence for routing and eval records.
- Correlated model agreement is not treated as independent verification evidence.
- Budget admission occurs before expensive provider allocation and consumed budget is monotonic.

**Test targets**

- `backend/tests/test_model_router.py`
- `skeleton/testing/test_cost_admission.py`
- `skeleton/testing/test_admission_runtime.py`
- `skeleton/testing/test_tenant_quota.py`
- `planned:skeleton/testing/test_model_routing_edges.py::test_fallback_rechecks_modality_and_tool_support`
- `planned:skeleton/testing/test_model_routing_edges.py::test_fallback_cannot_cross_privacy_ceiling`
- `planned:skeleton/testing/test_model_routing_edges.py::test_alias_revision_is_part_of_route_receipt`
- `planned:skeleton/testing/test_model_routing_edges.py::test_correlated_ensemble_not_counted_as_independent_verification`

**Acceptance**

- no route bypasses hard constraints
- fallback remains policy-equivalent or fails explicitly
- routing decisions are reproducible and auditable
- budget/privacy violations are denied pre-I/O

## WP-W07 — Memory

**Objective:** Make durable memory governed, scoped, provenance-bearing, versioned and resistant to poisoning/staleness/self-reinforcement.

**Exact target paths**

- `skeleton/memory`
- `skeleton/contracts/memory_record.py`
- `skeleton/persistence/memory_repository.py`
- `skeleton/memory/policy.py`
- `skeleton/memory/writeback.py`
- `skeleton/vault/data_governance.py`

**Historical mechanisms:** `HIST-AI-008`, `HIST-AI-010`, `HIST-AI-017`, `HIST-AI-020`, `HIST-AI-027`, `HIST-AI-028`, `HIST-AI-029`

**Edge cases:** `EDGE-AI-003`, `EDGE-AI-004`, `EDGE-AI-033`, `EDGE-DATA-001`, `EDGE-DATA-009`, `EDGE-DATA-010`

**Obscure lessons:** `OBSCURE-007`, `OBSCURE-018`, `OBSCURE-020`

**Required invariants**

- Model output alone cannot authorize durable memory.
- Memory records retain source/provenance, scope, confidence/authority source, retention and version.
- New evidence may reinforce/update/contradict/supersede but does not silently overwrite history.
- Deleted/expired memory cannot remain discoverable through derived indexes.
- Memory-derived evidence cannot recursively self-validate without independent source lineage.
- Current explicit user/project intent outranks stale inferred memory where policies conflict.

**Test targets**

- `skeleton/testing/test_data_governance.py`
- `planned:skeleton/testing/test_memory_writeback.py::test_model_text_alone_cannot_persist`
- `planned:skeleton/testing/test_memory_writeback.py::test_poisoned_unverified_candidate_not_promoted`
- `planned:skeleton/testing/test_memory_reconciliation.py::test_stale_memory_does_not_override_current_intent`
- `planned:skeleton/testing/test_memory_reconciliation.py::test_contradiction_preserves_both_versions`
- `planned:skeleton/testing/test_memory_deletion.py::test_delete_propagates_to_vector_projection`
- `planned:skeleton/testing/test_memory_feedback_loop.py::test_generated_memory_cannot_self_corroborate`

**Acceptance**

- memory survives restart only through canonical repository
- poisoning/staleness is represented and testable
- deletion/retention propagates to projections
- memory improves tasks without becoming self-referential evidence authority

## WP-W08 — Retrieval

**Objective:** Provide authorized hybrid retrieval with provenance, freshness, dedupe, index lifecycle and robust source projection.

**Exact target paths**

- `skeleton/retrieval`
- `backend/services/rag_service.py`
- `skeleton/context/sources`
- `machine/state_topology.json`

**Historical mechanisms:** `HIST-AI-030`, `HIST-AI-031`, `HIST-AI-032`, `HIST-AI-027`

**Edge cases:** `EDGE-AI-005`, `EDGE-AI-006`, `EDGE-AI-007`, `EDGE-AI-008`, `EDGE-AI-009`, `EDGE-AI-010`, `EDGE-AI-011`, `EDGE-AI-034`, `EDGE-DATA-008`, `EDGE-DATA-009`

**Obscure lessons:** `OBSCURE-006`, `OBSCURE-010`, `OBSCURE-018`

**Required invariants**

- Authorization is enforced at retrieval time, not only at ingestion.
- Evidence keeps source, scope, time and independent-origin lineage.
- Near-duplicate copies cannot inflate corroboration counts.
- Chunking preserves enough neighborhood/provenance to recover qualifiers and limitations.
- Embedding/index version mismatch is detected rather than silently queried.
- Deleted source content cannot remain active in derived indexes.
- Generated summaries are labeled derived and cannot masquerade as independent sources.

**Test targets**

- `tests/test_retrieval_pipeline_internals.py`
- `tests/test_quad_retrieval_internals.py`
- `skeleton/testing/test_retrieval_hot_path.py`
- `planned:skeleton/testing/test_retrieval_edge_cases.py::test_duplicate_sources_do_not_inflate_independence`
- `planned:skeleton/testing/test_retrieval_edge_cases.py::test_chunk_preserves_qualifier_context`
- `planned:skeleton/testing/test_retrieval_edge_cases.py::test_embedding_version_mismatch_fails_closed`
- `planned:skeleton/testing/test_retrieval_edge_cases.py::test_deleted_source_disappears_from_derived_index`
- `planned:skeleton/testing/test_retrieval_edge_cases.py::test_generated_summary_is_not_independent_evidence`

**Acceptance**

- hybrid baseline includes sparse retrieval rather than assuming dense superiority
- source deletion/freshness/versioning are explicit
- evidence lineage survives ranking/reranking
- retrieval cannot launder untrusted/generated content into authority

## WP-W09 — Knowledge & Evidence

**Objective:** Represent claims, evidence, contradictions, scope, temporality and hypotheses without silently collapsing uncertainty.

**Exact target paths**

- `skeleton/knowledge`
- `skeleton/retrieval`
- `skeleton/vault`
- `machine/ai_capabilities.json`

**Historical mechanisms:** `HIST-AI-005`, `HIST-AI-008`, `HIST-AI-016`, `HIST-AI-032`, `HIST-AI-040`

**Edge cases:** `EDGE-AI-005`, `EDGE-AI-006`, `EDGE-AI-008`, `EDGE-AI-009`, `EDGE-AI-023`, `EDGE-AI-024`, `EDGE-AI-025`, `EDGE-AI-033`, `EDGE-AI-034`

**Obscure lessons:** `OBSCURE-011`, `OBSCURE-019`, `OBSCURE-020`, `OBSCURE-030`

**Required invariants**

- A claim is not VERIFIED solely because a model emitted it.
- Evidence carries temporal/population/environment scope and source lineage.
- Contradictory claims remain representable simultaneously.
- Multiple citations with one originating source count as correlated evidence.
- Hypotheses remain distinct from facts and list predicted observations/experiments.
- Abstention/contested/unknown are valid knowledge outcomes.

**Test targets**

- `planned:skeleton/testing/test_claim_evidence_graph.py::test_correlated_sources_not_counted_as_independent`
- `planned:skeleton/testing/test_claim_evidence_graph.py::test_temporal_scope_prevents_historical_fact_as_current`
- `planned:skeleton/testing/test_claim_evidence_graph.py::test_population_scope_prevents_invalid_generalization`
- `planned:skeleton/testing/test_claim_evidence_graph.py::test_contradictory_claims_coexist`
- `planned:skeleton/testing/test_claim_evidence_graph.py::test_model_generated_memory_cannot_self_verify_claim`
- `planned:skeleton/testing/test_claim_evidence_graph.py::test_unknown_and_contested_are_terminal_valid_states`

**Acceptance**

- claim state is evidence-derived
- scope and time are first-class
- contradictions do not corrupt prior state
- knowledge graph can explain source lineage and uncertainty

## WP-W10 — Context Compiler

**Objective:** Build deterministic, trust-aware, budgeted provider context without losing authority/provenance through compression or truncation.

**Exact target paths**

- `skeleton/contracts/context.py`
- `skeleton/context/compiler.py`
- `skeleton/context/policy.py`
- `skeleton/context/sources`
- `skeleton/testing/test_context_compiler.py`

**Historical mechanisms:** `HIST-AI-003`, `HIST-AI-024`, `HIST-AI-027`, `HIST-SYS-018`

**Edge cases:** `EDGE-AI-001`, `EDGE-AI-002`, `EDGE-AI-007`, `EDGE-AI-012`, `EDGE-AI-013`, `EDGE-AI-037`, `EDGE-CONTRACT-008`, `EDGE-CONTRACT-009`, `EDGE-CONTRACT-010`

**Obscure lessons:** `OBSCURE-018`, `OBSCURE-024`, `OBSCURE-025`

**Required invariants**

- Trust is metadata carried through context assembly, not inferred from position in the prompt.
- Untrusted external/retrieved/tool/generated content cannot promote itself to system/developer authority.
- Mandatory policy/authority/operation identity are outside optional trimming.
- Compression preserves source references and cannot silently merge trusted instruction with untrusted evidence.
- Oversized tool/retrieval results are stored/referenced or bounded, not blindly injected.
- Unicode/control-character normalization policy is applied before security-sensitive instruction boundary checks.

**Test targets**

- `skeleton/testing/test_context_compiler.py`
- `planned:skeleton/testing/test_context_security_edges.py::test_retrieved_prompt_injection_remains_untrusted`
- `planned:skeleton/testing/test_context_security_edges.py::test_tool_output_instructions_cannot_gain_authority`
- `planned:skeleton/testing/test_context_budget_edges.py::test_mandatory_policy_never_trimmed`
- `planned:skeleton/testing/test_context_budget_edges.py::test_compression_retains_exception_and_provenance`
- `planned:skeleton/testing/test_context_budget_edges.py::test_oversized_tool_result_becomes_reference`

**Acceptance**

- same governed state produces deterministic context ordering under same budget/policy
- trust classes survive compilation
- truncation cannot remove mandatory controls
- context artifacts explain omissions/compression actions

## WP-W11 — Cognitive Runtime

**Objective:** Execute the bounded observe-context-route-infer-plan-act-observe-verify-finalize loop with durable turn lineage and stagnation/approval/recovery semantics.

**Exact target paths**

- `skeleton/intelligence`
- `skeleton/contracts/operation.py`
- `skeleton/provider_runtime.py`
- `skeleton/skills`
- `skeleton/persistence`
- `backend/core/operation_stream_transport.py`
- `frontend/src/product`

**Historical mechanisms:** `HIST-AI-001`, `HIST-AI-002`, `HIST-AI-009`, `HIST-AI-011`, `HIST-AI-013`, `HIST-AI-014`, `HIST-AI-037`, `HIST-AI-038`, `HIST-AI-039`, `HIST-AI-040`, `HIST-SYS-003`, `HIST-SYS-010`

**Edge cases:** `EDGE-AI-022`, `EDGE-AI-023`, `EDGE-AI-024`, `EDGE-AI-025`, `EDGE-AI-026`, `EDGE-AI-027`, `EDGE-AI-028`, `EDGE-AI-029`, `EDGE-AI-030`, `EDGE-AI-031`, `EDGE-AI-032`, `EDGE-AI-035`, `EDGE-AI-036`, `EDGE-AI-039`, `EDGE-AI-040`, `EDGE-DIST-006`, `EDGE-DIST-020`, `EDGE-DIST-021`, `EDGE-DIST-030`, `EDGE-UX-001`, `EDGE-UX-002`, `EDGE-UX-004`, `EDGE-UX-010`

**Obscure lessons:** `OBSCURE-004`, `OBSCURE-005`, `OBSCURE-012`, `OBSCURE-013`, `OBSCURE-019`, `OBSCURE-020`, `OBSCURE-026`

**Required invariants**

- Every action traces to operation objective and current plan step or an explicit bounded exception path.
- Model-generated authorization/approval text has no authority.
- Identical failure/proposal cycles trigger stagnation handling before budgets can run indefinitely.
- Verifier independence is measured by evidence/process diversity rather than model count.
- Approval binds exact arguments/tool/risk/version and is invalidated by material change or expiry.
- External timeout/unknown outcome is reconciled before retry.
- Cancellation, completion and crash recovery converge on one durable terminal result.
- Browser/stream loss cannot lose operation truth; clients reconstruct from durable state.
- Goal drift/specification gaming are explicit evaluation failures.

**Test targets**

- `planned:skeleton/testing/test_cognitive_execution_loop.py::test_prompt_only_completion`
- `planned:skeleton/testing/test_cognitive_execution_loop.py::test_single_and_multi_tool_turns`
- `planned:skeleton/testing/test_cognitive_stagnation.py::test_identical_failed_tool_cycle_stops`
- `planned:skeleton/testing/test_cognitive_approval.py::test_approval_invalid_after_argument_change`
- `planned:skeleton/testing/test_cognitive_approval.py::test_expired_approval_revalidates`
- `planned:skeleton/testing/test_cognitive_recovery.py::test_side_effect_before_receipt_is_reconciled_not_blindly_replayed`
- `planned:skeleton/testing/test_cognitive_recovery.py::test_cancel_complete_race_has_one_terminal_state`
- `planned:skeleton/testing/test_cognitive_verification.py::test_correlated_verifier_not_treated_as_independent`
- `planned:skeleton/testing/test_cognitive_goal_drift.py::test_plan_actions_remain_traceable_to_objective`
- `planned:backend/tests/test_ai_operation_reconnect.py::test_browser_refresh_reconstructs_running_and_terminal_state`

**Acceptance**

- bounded loop cannot spin indefinitely
- tool/approval authority remains external to generated text
- durable turn/checkpoint lineage survives crash/restart
- terminal result binds route/provider/tool/verification/usage/memory/artifact/stream evidence
- VS-001 edge-case families are executable


## P0 promotion law

For W00–W11, edge-case status progresses independently from implementation status:

```text
CATALOGUED
-> MAPPED
-> TEST_PLANNED
-> TEST_IMPLEMENTED
-> EVIDENCE_PASSING
-> ACCEPTED
```

A package may be implemented while edge coverage remains incomplete. It may not be described as fully hardened until required high-impact cases reach `EVIDENCE_PASSING` or are dispositioned as explicit accepted risks.

## Current mapping statistics

- Work packages: **12**
- Unique catalogue entries referenced: **173**
- Historical references: **48**
- Edge-case references: **100**
- Obscure references: **25**

This is deliberately not all 240 entries: W00–W11 cover the P0 foundation/cognitive path. The remaining catalog entries bind later to W12–W30, vertical slices, installer/release, distributed runtime, research/training, product and operations packages.
