# FLGB-04 — Tools Agents and Long-Horizon Execution

Canonical overlay: Functional LLM + Game Builder 10MB execution atlas
Masterplan relationship: depth-only; VOL-000..420 breadth freeze preserved
Implementation authority: none; this file defines requirements and evidence targets
Implementation signed: false
Independent verification signed: false

## Plane objective
Deliver a production-functional plane for Tools Agents and Long-Horizon Execution that composes with the provider-neutral LLM runtime and the governed AI game builder. Every atom below is non-compensable within its stated scope: unresolved atoms remain explicit gaps and cannot be erased by benchmark gains elsewhere.

## FLGB-04-00001 — tool registry / contract / unit proof
**Objective.** Implement tool registry so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00002 — tool schema / contract / unit proof
**Objective.** Implement tool schema so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00003 — authority subset / contract / unit proof
**Objective.** Implement authority subset so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00004 — sandbox execution / contract / unit proof
**Objective.** Implement sandbox execution so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00005 — idempotent writes / contract / unit proof
**Objective.** Implement idempotent writes so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00006 — compensation / contract / unit proof
**Objective.** Implement compensation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00007 — plan DAG / contract / unit proof
**Objective.** Implement plan DAG so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00008 — worker leases / contract / unit proof
**Objective.** Implement worker leases so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00009 — checkpointing / contract / unit proof
**Objective.** Implement checkpointing so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00010 — handoff / contract / unit proof
**Objective.** Implement handoff so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00011 — multi-agent arbitration / contract / unit proof
**Objective.** Implement multi-agent arbitration so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00012 — long-run recovery / contract / unit proof
**Objective.** Implement long-run recovery so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00013 — tool registry / admission / unit proof
**Objective.** Implement tool registry so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00014 — tool schema / admission / unit proof
**Objective.** Implement tool schema so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00015 — authority subset / admission / unit proof
**Objective.** Implement authority subset so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00016 — sandbox execution / admission / unit proof
**Objective.** Implement sandbox execution so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00017 — idempotent writes / admission / unit proof
**Objective.** Implement idempotent writes so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00018 — compensation / admission / unit proof
**Objective.** Implement compensation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00019 — plan DAG / admission / unit proof
**Objective.** Implement plan DAG so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00020 — worker leases / admission / unit proof
**Objective.** Implement worker leases so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00021 — checkpointing / admission / unit proof
**Objective.** Implement checkpointing so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00022 — handoff / admission / unit proof
**Objective.** Implement handoff so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00023 — multi-agent arbitration / admission / unit proof
**Objective.** Implement multi-agent arbitration so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00024 — long-run recovery / admission / unit proof
**Objective.** Implement long-run recovery so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00025 — tool registry / compile / unit proof
**Objective.** Implement tool registry so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00026 — tool schema / compile / unit proof
**Objective.** Implement tool schema so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00027 — authority subset / compile / unit proof
**Objective.** Implement authority subset so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00028 — sandbox execution / compile / unit proof
**Objective.** Implement sandbox execution so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00029 — idempotent writes / compile / unit proof
**Objective.** Implement idempotent writes so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00030 — compensation / compile / unit proof
**Objective.** Implement compensation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00031 — plan DAG / compile / unit proof
**Objective.** Implement plan DAG so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00032 — worker leases / compile / unit proof
**Objective.** Implement worker leases so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00033 — checkpointing / compile / unit proof
**Objective.** Implement checkpointing so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00034 — handoff / compile / unit proof
**Objective.** Implement handoff so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00035 — multi-agent arbitration / compile / unit proof
**Objective.** Implement multi-agent arbitration so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00036 — long-run recovery / compile / unit proof
**Objective.** Implement long-run recovery so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00037 — tool registry / execute / unit proof
**Objective.** Implement tool registry so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00038 — tool schema / execute / unit proof
**Objective.** Implement tool schema so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00039 — authority subset / execute / unit proof
**Objective.** Implement authority subset so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00040 — sandbox execution / execute / unit proof
**Objective.** Implement sandbox execution so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00041 — idempotent writes / execute / unit proof
**Objective.** Implement idempotent writes so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00042 — compensation / execute / unit proof
**Objective.** Implement compensation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00043 — plan DAG / execute / unit proof
**Objective.** Implement plan DAG so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00044 — worker leases / execute / unit proof
**Objective.** Implement worker leases so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00045 — checkpointing / execute / unit proof
**Objective.** Implement checkpointing so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00046 — handoff / execute / unit proof
**Objective.** Implement handoff so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00047 — multi-agent arbitration / execute / unit proof
**Objective.** Implement multi-agent arbitration so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00048 — long-run recovery / execute / unit proof
**Objective.** Implement long-run recovery so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00049 — tool registry / observe / unit proof
**Objective.** Implement tool registry so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00050 — tool schema / observe / unit proof
**Objective.** Implement tool schema so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00051 — authority subset / observe / unit proof
**Objective.** Implement authority subset so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00052 — sandbox execution / observe / unit proof
**Objective.** Implement sandbox execution so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00053 — idempotent writes / observe / unit proof
**Objective.** Implement idempotent writes so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00054 — compensation / observe / unit proof
**Objective.** Implement compensation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00055 — plan DAG / observe / unit proof
**Objective.** Implement plan DAG so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00056 — worker leases / observe / unit proof
**Objective.** Implement worker leases so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00057 — checkpointing / observe / unit proof
**Objective.** Implement checkpointing so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00058 — handoff / observe / unit proof
**Objective.** Implement handoff so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00059 — multi-agent arbitration / observe / unit proof
**Objective.** Implement multi-agent arbitration so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00060 — long-run recovery / observe / unit proof
**Objective.** Implement long-run recovery so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00061 — tool registry / verify / unit proof
**Objective.** Implement tool registry so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00062 — tool schema / verify / unit proof
**Objective.** Implement tool schema so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00063 — authority subset / verify / unit proof
**Objective.** Implement authority subset so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00064 — sandbox execution / verify / unit proof
**Objective.** Implement sandbox execution so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00065 — idempotent writes / verify / unit proof
**Objective.** Implement idempotent writes so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00066 — compensation / verify / unit proof
**Objective.** Implement compensation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00067 — plan DAG / verify / unit proof
**Objective.** Implement plan DAG so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00068 — worker leases / verify / unit proof
**Objective.** Implement worker leases so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00069 — checkpointing / verify / unit proof
**Objective.** Implement checkpointing so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00070 — handoff / verify / unit proof
**Objective.** Implement handoff so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00071 — multi-agent arbitration / verify / unit proof
**Objective.** Implement multi-agent arbitration so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00072 — long-run recovery / verify / unit proof
**Objective.** Implement long-run recovery so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00073 — tool registry / recover / unit proof
**Objective.** Implement tool registry so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00074 — tool schema / recover / unit proof
**Objective.** Implement tool schema so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00075 — authority subset / recover / unit proof
**Objective.** Implement authority subset so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00076 — sandbox execution / recover / unit proof
**Objective.** Implement sandbox execution so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00077 — idempotent writes / recover / unit proof
**Objective.** Implement idempotent writes so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00078 — compensation / recover / unit proof
**Objective.** Implement compensation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00079 — plan DAG / recover / unit proof
**Objective.** Implement plan DAG so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00080 — worker leases / recover / unit proof
**Objective.** Implement worker leases so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00081 — checkpointing / recover / unit proof
**Objective.** Implement checkpointing so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00082 — handoff / recover / unit proof
**Objective.** Implement handoff so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00083 — multi-agent arbitration / recover / unit proof
**Objective.** Implement multi-agent arbitration so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00084 — long-run recovery / recover / unit proof
**Objective.** Implement long-run recovery so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00085 — tool registry / replay / unit proof
**Objective.** Implement tool registry so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00086 — tool schema / replay / unit proof
**Objective.** Implement tool schema so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00087 — authority subset / replay / unit proof
**Objective.** Implement authority subset so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00088 — sandbox execution / replay / unit proof
**Objective.** Implement sandbox execution so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00089 — idempotent writes / replay / unit proof
**Objective.** Implement idempotent writes so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00090 — compensation / replay / unit proof
**Objective.** Implement compensation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00091 — plan DAG / replay / unit proof
**Objective.** Implement plan DAG so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00092 — worker leases / replay / unit proof
**Objective.** Implement worker leases so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00093 — checkpointing / replay / unit proof
**Objective.** Implement checkpointing so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00094 — handoff / replay / unit proof
**Objective.** Implement handoff so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00095 — multi-agent arbitration / replay / unit proof
**Objective.** Implement multi-agent arbitration so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00096 — long-run recovery / replay / unit proof
**Objective.** Implement long-run recovery so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00097 — tool registry / optimize / unit proof
**Objective.** Implement tool registry so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00098 — tool schema / optimize / unit proof
**Objective.** Implement tool schema so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00099 — authority subset / optimize / unit proof
**Objective.** Implement authority subset so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00100 — sandbox execution / optimize / unit proof
**Objective.** Implement sandbox execution so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00101 — idempotent writes / optimize / unit proof
**Objective.** Implement idempotent writes so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00102 — compensation / optimize / unit proof
**Objective.** Implement compensation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00103 — plan DAG / optimize / unit proof
**Objective.** Implement plan DAG so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00104 — worker leases / optimize / unit proof
**Objective.** Implement worker leases so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00105 — checkpointing / optimize / unit proof
**Objective.** Implement checkpointing so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00106 — handoff / optimize / unit proof
**Objective.** Implement handoff so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00107 — multi-agent arbitration / optimize / unit proof
**Objective.** Implement multi-agent arbitration so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00108 — long-run recovery / optimize / unit proof
**Objective.** Implement long-run recovery so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00109 — tool registry / promote / unit proof
**Objective.** Implement tool registry so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00110 — tool schema / promote / unit proof
**Objective.** Implement tool schema so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00111 — authority subset / promote / unit proof
**Objective.** Implement authority subset so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00112 — sandbox execution / promote / unit proof
**Objective.** Implement sandbox execution so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00113 — idempotent writes / promote / unit proof
**Objective.** Implement idempotent writes so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00114 — compensation / promote / unit proof
**Objective.** Implement compensation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00115 — plan DAG / promote / unit proof
**Objective.** Implement plan DAG so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00116 — worker leases / promote / unit proof
**Objective.** Implement worker leases so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00117 — checkpointing / promote / unit proof
**Objective.** Implement checkpointing so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00118 — handoff / promote / unit proof
**Objective.** Implement handoff so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00119 — multi-agent arbitration / promote / unit proof
**Objective.** Implement multi-agent arbitration so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00120 — long-run recovery / promote / unit proof
**Objective.** Implement long-run recovery so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00121 — tool registry / rollback / unit proof
**Objective.** Implement tool registry so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00122 — tool schema / rollback / unit proof
**Objective.** Implement tool schema so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00123 — authority subset / rollback / unit proof
**Objective.** Implement authority subset so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00124 — sandbox execution / rollback / unit proof
**Objective.** Implement sandbox execution so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00125 — idempotent writes / rollback / unit proof
**Objective.** Implement idempotent writes so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00126 — compensation / rollback / unit proof
**Objective.** Implement compensation so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00127 — plan DAG / rollback / unit proof
**Objective.** Implement plan DAG so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00128 — worker leases / rollback / unit proof
**Objective.** Implement worker leases so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00129 — checkpointing / rollback / unit proof
**Objective.** Implement checkpointing so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00130 — handoff / rollback / unit proof
**Objective.** Implement handoff so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00131 — multi-agent arbitration / rollback / unit proof
**Objective.** Implement multi-agent arbitration so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00132 — long-run recovery / rollback / unit proof
**Objective.** Implement long-run recovery so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00133 — tool registry / retire / unit proof
**Objective.** Implement tool registry so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00134 — tool schema / retire / unit proof
**Objective.** Implement tool schema so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00135 — authority subset / retire / unit proof
**Objective.** Implement authority subset so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00136 — sandbox execution / retire / unit proof
**Objective.** Implement sandbox execution so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00137 — idempotent writes / retire / unit proof
**Objective.** Implement idempotent writes so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00138 — compensation / retire / unit proof
**Objective.** Implement compensation so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00139 — plan DAG / retire / unit proof
**Objective.** Implement plan DAG so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00140 — worker leases / retire / unit proof
**Objective.** Implement worker leases so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00141 — checkpointing / retire / unit proof
**Objective.** Implement checkpointing so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00142 — handoff / retire / unit proof
**Objective.** Implement handoff so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00143 — multi-agent arbitration / retire / unit proof
**Objective.** Implement multi-agent arbitration so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00144 — long-run recovery / retire / unit proof
**Objective.** Implement long-run recovery so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00145 — tool registry / contract / property proof
**Objective.** Implement tool registry so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00146 — tool schema / contract / property proof
**Objective.** Implement tool schema so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00147 — authority subset / contract / property proof
**Objective.** Implement authority subset so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00148 — sandbox execution / contract / property proof
**Objective.** Implement sandbox execution so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00149 — idempotent writes / contract / property proof
**Objective.** Implement idempotent writes so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00150 — compensation / contract / property proof
**Objective.** Implement compensation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00151 — plan DAG / contract / property proof
**Objective.** Implement plan DAG so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00152 — worker leases / contract / property proof
**Objective.** Implement worker leases so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00153 — checkpointing / contract / property proof
**Objective.** Implement checkpointing so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00154 — handoff / contract / property proof
**Objective.** Implement handoff so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00155 — multi-agent arbitration / contract / property proof
**Objective.** Implement multi-agent arbitration so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00156 — long-run recovery / contract / property proof
**Objective.** Implement long-run recovery so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00157 — tool registry / admission / property proof
**Objective.** Implement tool registry so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00158 — tool schema / admission / property proof
**Objective.** Implement tool schema so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00159 — authority subset / admission / property proof
**Objective.** Implement authority subset so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00160 — sandbox execution / admission / property proof
**Objective.** Implement sandbox execution so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00161 — idempotent writes / admission / property proof
**Objective.** Implement idempotent writes so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00162 — compensation / admission / property proof
**Objective.** Implement compensation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00163 — plan DAG / admission / property proof
**Objective.** Implement plan DAG so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00164 — worker leases / admission / property proof
**Objective.** Implement worker leases so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00165 — checkpointing / admission / property proof
**Objective.** Implement checkpointing so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00166 — handoff / admission / property proof
**Objective.** Implement handoff so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00167 — multi-agent arbitration / admission / property proof
**Objective.** Implement multi-agent arbitration so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00168 — long-run recovery / admission / property proof
**Objective.** Implement long-run recovery so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00169 — tool registry / compile / property proof
**Objective.** Implement tool registry so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00170 — tool schema / compile / property proof
**Objective.** Implement tool schema so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00171 — authority subset / compile / property proof
**Objective.** Implement authority subset so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00172 — sandbox execution / compile / property proof
**Objective.** Implement sandbox execution so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00173 — idempotent writes / compile / property proof
**Objective.** Implement idempotent writes so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00174 — compensation / compile / property proof
**Objective.** Implement compensation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00175 — plan DAG / compile / property proof
**Objective.** Implement plan DAG so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00176 — worker leases / compile / property proof
**Objective.** Implement worker leases so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00177 — checkpointing / compile / property proof
**Objective.** Implement checkpointing so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00178 — handoff / compile / property proof
**Objective.** Implement handoff so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00179 — multi-agent arbitration / compile / property proof
**Objective.** Implement multi-agent arbitration so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00180 — long-run recovery / compile / property proof
**Objective.** Implement long-run recovery so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00181 — tool registry / execute / property proof
**Objective.** Implement tool registry so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00182 — tool schema / execute / property proof
**Objective.** Implement tool schema so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00183 — authority subset / execute / property proof
**Objective.** Implement authority subset so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00184 — sandbox execution / execute / property proof
**Objective.** Implement sandbox execution so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00185 — idempotent writes / execute / property proof
**Objective.** Implement idempotent writes so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00186 — compensation / execute / property proof
**Objective.** Implement compensation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00187 — plan DAG / execute / property proof
**Objective.** Implement plan DAG so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00188 — worker leases / execute / property proof
**Objective.** Implement worker leases so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00189 — checkpointing / execute / property proof
**Objective.** Implement checkpointing so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00190 — handoff / execute / property proof
**Objective.** Implement handoff so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00191 — multi-agent arbitration / execute / property proof
**Objective.** Implement multi-agent arbitration so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00192 — long-run recovery / execute / property proof
**Objective.** Implement long-run recovery so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00193 — tool registry / observe / property proof
**Objective.** Implement tool registry so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00194 — tool schema / observe / property proof
**Objective.** Implement tool schema so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00195 — authority subset / observe / property proof
**Objective.** Implement authority subset so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00196 — sandbox execution / observe / property proof
**Objective.** Implement sandbox execution so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00197 — idempotent writes / observe / property proof
**Objective.** Implement idempotent writes so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00198 — compensation / observe / property proof
**Objective.** Implement compensation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00199 — plan DAG / observe / property proof
**Objective.** Implement plan DAG so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00200 — worker leases / observe / property proof
**Objective.** Implement worker leases so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00201 — checkpointing / observe / property proof
**Objective.** Implement checkpointing so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00202 — handoff / observe / property proof
**Objective.** Implement handoff so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00203 — multi-agent arbitration / observe / property proof
**Objective.** Implement multi-agent arbitration so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00204 — long-run recovery / observe / property proof
**Objective.** Implement long-run recovery so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00205 — tool registry / verify / property proof
**Objective.** Implement tool registry so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00206 — tool schema / verify / property proof
**Objective.** Implement tool schema so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00207 — authority subset / verify / property proof
**Objective.** Implement authority subset so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00208 — sandbox execution / verify / property proof
**Objective.** Implement sandbox execution so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00209 — idempotent writes / verify / property proof
**Objective.** Implement idempotent writes so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00210 — compensation / verify / property proof
**Objective.** Implement compensation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00211 — plan DAG / verify / property proof
**Objective.** Implement plan DAG so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00212 — worker leases / verify / property proof
**Objective.** Implement worker leases so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00213 — checkpointing / verify / property proof
**Objective.** Implement checkpointing so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00214 — handoff / verify / property proof
**Objective.** Implement handoff so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00215 — multi-agent arbitration / verify / property proof
**Objective.** Implement multi-agent arbitration so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00216 — long-run recovery / verify / property proof
**Objective.** Implement long-run recovery so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00217 — tool registry / recover / property proof
**Objective.** Implement tool registry so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00218 — tool schema / recover / property proof
**Objective.** Implement tool schema so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00219 — authority subset / recover / property proof
**Objective.** Implement authority subset so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00220 — sandbox execution / recover / property proof
**Objective.** Implement sandbox execution so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00221 — idempotent writes / recover / property proof
**Objective.** Implement idempotent writes so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00222 — compensation / recover / property proof
**Objective.** Implement compensation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00223 — plan DAG / recover / property proof
**Objective.** Implement plan DAG so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00224 — worker leases / recover / property proof
**Objective.** Implement worker leases so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00225 — checkpointing / recover / property proof
**Objective.** Implement checkpointing so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00226 — handoff / recover / property proof
**Objective.** Implement handoff so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00227 — multi-agent arbitration / recover / property proof
**Objective.** Implement multi-agent arbitration so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00228 — long-run recovery / recover / property proof
**Objective.** Implement long-run recovery so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00229 — tool registry / replay / property proof
**Objective.** Implement tool registry so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00230 — tool schema / replay / property proof
**Objective.** Implement tool schema so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00231 — authority subset / replay / property proof
**Objective.** Implement authority subset so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00232 — sandbox execution / replay / property proof
**Objective.** Implement sandbox execution so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00233 — idempotent writes / replay / property proof
**Objective.** Implement idempotent writes so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00234 — compensation / replay / property proof
**Objective.** Implement compensation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00235 — plan DAG / replay / property proof
**Objective.** Implement plan DAG so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00236 — worker leases / replay / property proof
**Objective.** Implement worker leases so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00237 — checkpointing / replay / property proof
**Objective.** Implement checkpointing so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00238 — handoff / replay / property proof
**Objective.** Implement handoff so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00239 — multi-agent arbitration / replay / property proof
**Objective.** Implement multi-agent arbitration so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00240 — long-run recovery / replay / property proof
**Objective.** Implement long-run recovery so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00241 — tool registry / optimize / property proof
**Objective.** Implement tool registry so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00242 — tool schema / optimize / property proof
**Objective.** Implement tool schema so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00243 — authority subset / optimize / property proof
**Objective.** Implement authority subset so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00244 — sandbox execution / optimize / property proof
**Objective.** Implement sandbox execution so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00245 — idempotent writes / optimize / property proof
**Objective.** Implement idempotent writes so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00246 — compensation / optimize / property proof
**Objective.** Implement compensation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00247 — plan DAG / optimize / property proof
**Objective.** Implement plan DAG so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00248 — worker leases / optimize / property proof
**Objective.** Implement worker leases so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00249 — checkpointing / optimize / property proof
**Objective.** Implement checkpointing so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/checkpointing.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00250 — handoff / optimize / property proof
**Objective.** Implement handoff so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/handoff.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00251 — multi-agent arbitration / optimize / property proof
**Objective.** Implement multi-agent arbitration so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/multi_agent_arbitration.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00252 — long-run recovery / optimize / property proof
**Objective.** Implement long-run recovery so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/long_run_recovery.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00253 — tool registry / promote / property proof
**Objective.** Implement tool registry so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_registry.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00254 — tool schema / promote / property proof
**Objective.** Implement tool schema so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/tool_schema.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00255 — authority subset / promote / property proof
**Objective.** Implement authority subset so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/authority_subset.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00256 — sandbox execution / promote / property proof
**Objective.** Implement sandbox execution so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/sandbox_execution.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00257 — idempotent writes / promote / property proof
**Objective.** Implement idempotent writes so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/idempotent_writes.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00258 — compensation / promote / property proof
**Objective.** Implement compensation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/compensation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00259 — plan DAG / promote / property proof
**Objective.** Implement plan DAG so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/plan_dag.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-04-00260 — worker leases / promote / property proof
**Objective.** Implement worker leases so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/agents/worker_leases.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.
