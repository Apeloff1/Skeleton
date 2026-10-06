# FLGB-05 — Security Safety Policy and Privacy

Canonical overlay: Functional LLM + Game Builder 10MB execution atlas
Masterplan relationship: depth-only; VOL-000..420 breadth freeze preserved
Implementation authority: none; this file defines requirements and evidence targets
Implementation signed: false
Independent verification signed: false

## Plane objective
Deliver a production-functional plane for Security Safety Policy and Privacy that composes with the provider-neutral LLM runtime and the governed AI game builder. Every atom below is non-compensable within its stated scope: unresolved atoms remain explicit gaps and cannot be erased by benchmark gains elsewhere.

## FLGB-05-00001 — policy evaluation / contract / unit proof
**Objective.** Implement policy evaluation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00002 — prompt injection resistance / contract / unit proof
**Objective.** Implement prompt injection resistance so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00003 — secret isolation / contract / unit proof
**Objective.** Implement secret isolation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00004 — tenant isolation / contract / unit proof
**Objective.** Implement tenant isolation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00005 — PII handling / contract / unit proof
**Objective.** Implement PII handling so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00006 — data classification / contract / unit proof
**Objective.** Implement data classification so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00007 — authorization / contract / unit proof
**Objective.** Implement authorization so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00008 — approval gates / contract / unit proof
**Objective.** Implement approval gates so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00009 — sandbox boundary / contract / unit proof
**Objective.** Implement sandbox boundary so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00010 — supply-chain trust / contract / unit proof
**Objective.** Implement supply-chain trust so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00011 — audit evidence / contract / unit proof
**Objective.** Implement audit evidence so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00012 — incident fail-closed / contract / unit proof
**Objective.** Implement incident fail-closed so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00013 — policy evaluation / admission / unit proof
**Objective.** Implement policy evaluation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00014 — prompt injection resistance / admission / unit proof
**Objective.** Implement prompt injection resistance so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00015 — secret isolation / admission / unit proof
**Objective.** Implement secret isolation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00016 — tenant isolation / admission / unit proof
**Objective.** Implement tenant isolation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00017 — PII handling / admission / unit proof
**Objective.** Implement PII handling so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00018 — data classification / admission / unit proof
**Objective.** Implement data classification so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00019 — authorization / admission / unit proof
**Objective.** Implement authorization so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00020 — approval gates / admission / unit proof
**Objective.** Implement approval gates so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00021 — sandbox boundary / admission / unit proof
**Objective.** Implement sandbox boundary so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00022 — supply-chain trust / admission / unit proof
**Objective.** Implement supply-chain trust so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00023 — audit evidence / admission / unit proof
**Objective.** Implement audit evidence so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00024 — incident fail-closed / admission / unit proof
**Objective.** Implement incident fail-closed so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00025 — policy evaluation / compile / unit proof
**Objective.** Implement policy evaluation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00026 — prompt injection resistance / compile / unit proof
**Objective.** Implement prompt injection resistance so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00027 — secret isolation / compile / unit proof
**Objective.** Implement secret isolation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00028 — tenant isolation / compile / unit proof
**Objective.** Implement tenant isolation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00029 — PII handling / compile / unit proof
**Objective.** Implement PII handling so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00030 — data classification / compile / unit proof
**Objective.** Implement data classification so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00031 — authorization / compile / unit proof
**Objective.** Implement authorization so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00032 — approval gates / compile / unit proof
**Objective.** Implement approval gates so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00033 — sandbox boundary / compile / unit proof
**Objective.** Implement sandbox boundary so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00034 — supply-chain trust / compile / unit proof
**Objective.** Implement supply-chain trust so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00035 — audit evidence / compile / unit proof
**Objective.** Implement audit evidence so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00036 — incident fail-closed / compile / unit proof
**Objective.** Implement incident fail-closed so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00037 — policy evaluation / execute / unit proof
**Objective.** Implement policy evaluation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00038 — prompt injection resistance / execute / unit proof
**Objective.** Implement prompt injection resistance so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00039 — secret isolation / execute / unit proof
**Objective.** Implement secret isolation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00040 — tenant isolation / execute / unit proof
**Objective.** Implement tenant isolation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00041 — PII handling / execute / unit proof
**Objective.** Implement PII handling so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00042 — data classification / execute / unit proof
**Objective.** Implement data classification so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00043 — authorization / execute / unit proof
**Objective.** Implement authorization so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00044 — approval gates / execute / unit proof
**Objective.** Implement approval gates so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00045 — sandbox boundary / execute / unit proof
**Objective.** Implement sandbox boundary so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00046 — supply-chain trust / execute / unit proof
**Objective.** Implement supply-chain trust so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00047 — audit evidence / execute / unit proof
**Objective.** Implement audit evidence so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00048 — incident fail-closed / execute / unit proof
**Objective.** Implement incident fail-closed so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00049 — policy evaluation / observe / unit proof
**Objective.** Implement policy evaluation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00050 — prompt injection resistance / observe / unit proof
**Objective.** Implement prompt injection resistance so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00051 — secret isolation / observe / unit proof
**Objective.** Implement secret isolation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00052 — tenant isolation / observe / unit proof
**Objective.** Implement tenant isolation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00053 — PII handling / observe / unit proof
**Objective.** Implement PII handling so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00054 — data classification / observe / unit proof
**Objective.** Implement data classification so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00055 — authorization / observe / unit proof
**Objective.** Implement authorization so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00056 — approval gates / observe / unit proof
**Objective.** Implement approval gates so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00057 — sandbox boundary / observe / unit proof
**Objective.** Implement sandbox boundary so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00058 — supply-chain trust / observe / unit proof
**Objective.** Implement supply-chain trust so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00059 — audit evidence / observe / unit proof
**Objective.** Implement audit evidence so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00060 — incident fail-closed / observe / unit proof
**Objective.** Implement incident fail-closed so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00061 — policy evaluation / verify / unit proof
**Objective.** Implement policy evaluation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00062 — prompt injection resistance / verify / unit proof
**Objective.** Implement prompt injection resistance so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00063 — secret isolation / verify / unit proof
**Objective.** Implement secret isolation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00064 — tenant isolation / verify / unit proof
**Objective.** Implement tenant isolation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00065 — PII handling / verify / unit proof
**Objective.** Implement PII handling so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00066 — data classification / verify / unit proof
**Objective.** Implement data classification so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00067 — authorization / verify / unit proof
**Objective.** Implement authorization so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00068 — approval gates / verify / unit proof
**Objective.** Implement approval gates so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00069 — sandbox boundary / verify / unit proof
**Objective.** Implement sandbox boundary so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00070 — supply-chain trust / verify / unit proof
**Objective.** Implement supply-chain trust so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00071 — audit evidence / verify / unit proof
**Objective.** Implement audit evidence so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00072 — incident fail-closed / verify / unit proof
**Objective.** Implement incident fail-closed so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00073 — policy evaluation / recover / unit proof
**Objective.** Implement policy evaluation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00074 — prompt injection resistance / recover / unit proof
**Objective.** Implement prompt injection resistance so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00075 — secret isolation / recover / unit proof
**Objective.** Implement secret isolation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00076 — tenant isolation / recover / unit proof
**Objective.** Implement tenant isolation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00077 — PII handling / recover / unit proof
**Objective.** Implement PII handling so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00078 — data classification / recover / unit proof
**Objective.** Implement data classification so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00079 — authorization / recover / unit proof
**Objective.** Implement authorization so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00080 — approval gates / recover / unit proof
**Objective.** Implement approval gates so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00081 — sandbox boundary / recover / unit proof
**Objective.** Implement sandbox boundary so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00082 — supply-chain trust / recover / unit proof
**Objective.** Implement supply-chain trust so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00083 — audit evidence / recover / unit proof
**Objective.** Implement audit evidence so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00084 — incident fail-closed / recover / unit proof
**Objective.** Implement incident fail-closed so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00085 — policy evaluation / replay / unit proof
**Objective.** Implement policy evaluation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00086 — prompt injection resistance / replay / unit proof
**Objective.** Implement prompt injection resistance so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00087 — secret isolation / replay / unit proof
**Objective.** Implement secret isolation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00088 — tenant isolation / replay / unit proof
**Objective.** Implement tenant isolation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00089 — PII handling / replay / unit proof
**Objective.** Implement PII handling so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00090 — data classification / replay / unit proof
**Objective.** Implement data classification so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00091 — authorization / replay / unit proof
**Objective.** Implement authorization so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00092 — approval gates / replay / unit proof
**Objective.** Implement approval gates so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00093 — sandbox boundary / replay / unit proof
**Objective.** Implement sandbox boundary so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00094 — supply-chain trust / replay / unit proof
**Objective.** Implement supply-chain trust so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00095 — audit evidence / replay / unit proof
**Objective.** Implement audit evidence so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00096 — incident fail-closed / replay / unit proof
**Objective.** Implement incident fail-closed so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00097 — policy evaluation / optimize / unit proof
**Objective.** Implement policy evaluation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00098 — prompt injection resistance / optimize / unit proof
**Objective.** Implement prompt injection resistance so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00099 — secret isolation / optimize / unit proof
**Objective.** Implement secret isolation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00100 — tenant isolation / optimize / unit proof
**Objective.** Implement tenant isolation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00101 — PII handling / optimize / unit proof
**Objective.** Implement PII handling so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00102 — data classification / optimize / unit proof
**Objective.** Implement data classification so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00103 — authorization / optimize / unit proof
**Objective.** Implement authorization so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00104 — approval gates / optimize / unit proof
**Objective.** Implement approval gates so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00105 — sandbox boundary / optimize / unit proof
**Objective.** Implement sandbox boundary so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00106 — supply-chain trust / optimize / unit proof
**Objective.** Implement supply-chain trust so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00107 — audit evidence / optimize / unit proof
**Objective.** Implement audit evidence so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00108 — incident fail-closed / optimize / unit proof
**Objective.** Implement incident fail-closed so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00109 — policy evaluation / promote / unit proof
**Objective.** Implement policy evaluation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00110 — prompt injection resistance / promote / unit proof
**Objective.** Implement prompt injection resistance so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00111 — secret isolation / promote / unit proof
**Objective.** Implement secret isolation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00112 — tenant isolation / promote / unit proof
**Objective.** Implement tenant isolation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00113 — PII handling / promote / unit proof
**Objective.** Implement PII handling so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00114 — data classification / promote / unit proof
**Objective.** Implement data classification so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00115 — authorization / promote / unit proof
**Objective.** Implement authorization so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00116 — approval gates / promote / unit proof
**Objective.** Implement approval gates so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00117 — sandbox boundary / promote / unit proof
**Objective.** Implement sandbox boundary so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00118 — supply-chain trust / promote / unit proof
**Objective.** Implement supply-chain trust so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00119 — audit evidence / promote / unit proof
**Objective.** Implement audit evidence so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00120 — incident fail-closed / promote / unit proof
**Objective.** Implement incident fail-closed so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00121 — policy evaluation / rollback / unit proof
**Objective.** Implement policy evaluation so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00122 — prompt injection resistance / rollback / unit proof
**Objective.** Implement prompt injection resistance so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00123 — secret isolation / rollback / unit proof
**Objective.** Implement secret isolation so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00124 — tenant isolation / rollback / unit proof
**Objective.** Implement tenant isolation so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00125 — PII handling / rollback / unit proof
**Objective.** Implement PII handling so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00126 — data classification / rollback / unit proof
**Objective.** Implement data classification so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00127 — authorization / rollback / unit proof
**Objective.** Implement authorization so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00128 — approval gates / rollback / unit proof
**Objective.** Implement approval gates so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00129 — sandbox boundary / rollback / unit proof
**Objective.** Implement sandbox boundary so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00130 — supply-chain trust / rollback / unit proof
**Objective.** Implement supply-chain trust so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00131 — audit evidence / rollback / unit proof
**Objective.** Implement audit evidence so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00132 — incident fail-closed / rollback / unit proof
**Objective.** Implement incident fail-closed so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00133 — policy evaluation / retire / unit proof
**Objective.** Implement policy evaluation so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00134 — prompt injection resistance / retire / unit proof
**Objective.** Implement prompt injection resistance so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00135 — secret isolation / retire / unit proof
**Objective.** Implement secret isolation so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00136 — tenant isolation / retire / unit proof
**Objective.** Implement tenant isolation so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00137 — PII handling / retire / unit proof
**Objective.** Implement PII handling so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00138 — data classification / retire / unit proof
**Objective.** Implement data classification so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00139 — authorization / retire / unit proof
**Objective.** Implement authorization so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00140 — approval gates / retire / unit proof
**Objective.** Implement approval gates so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00141 — sandbox boundary / retire / unit proof
**Objective.** Implement sandbox boundary so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00142 — supply-chain trust / retire / unit proof
**Objective.** Implement supply-chain trust so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00143 — audit evidence / retire / unit proof
**Objective.** Implement audit evidence so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00144 — incident fail-closed / retire / unit proof
**Objective.** Implement incident fail-closed so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00145 — policy evaluation / contract / property proof
**Objective.** Implement policy evaluation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00146 — prompt injection resistance / contract / property proof
**Objective.** Implement prompt injection resistance so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00147 — secret isolation / contract / property proof
**Objective.** Implement secret isolation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00148 — tenant isolation / contract / property proof
**Objective.** Implement tenant isolation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00149 — PII handling / contract / property proof
**Objective.** Implement PII handling so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00150 — data classification / contract / property proof
**Objective.** Implement data classification so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00151 — authorization / contract / property proof
**Objective.** Implement authorization so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00152 — approval gates / contract / property proof
**Objective.** Implement approval gates so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00153 — sandbox boundary / contract / property proof
**Objective.** Implement sandbox boundary so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00154 — supply-chain trust / contract / property proof
**Objective.** Implement supply-chain trust so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00155 — audit evidence / contract / property proof
**Objective.** Implement audit evidence so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00156 — incident fail-closed / contract / property proof
**Objective.** Implement incident fail-closed so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00157 — policy evaluation / admission / property proof
**Objective.** Implement policy evaluation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00158 — prompt injection resistance / admission / property proof
**Objective.** Implement prompt injection resistance so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00159 — secret isolation / admission / property proof
**Objective.** Implement secret isolation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00160 — tenant isolation / admission / property proof
**Objective.** Implement tenant isolation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00161 — PII handling / admission / property proof
**Objective.** Implement PII handling so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00162 — data classification / admission / property proof
**Objective.** Implement data classification so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00163 — authorization / admission / property proof
**Objective.** Implement authorization so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00164 — approval gates / admission / property proof
**Objective.** Implement approval gates so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00165 — sandbox boundary / admission / property proof
**Objective.** Implement sandbox boundary so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00166 — supply-chain trust / admission / property proof
**Objective.** Implement supply-chain trust so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00167 — audit evidence / admission / property proof
**Objective.** Implement audit evidence so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00168 — incident fail-closed / admission / property proof
**Objective.** Implement incident fail-closed so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00169 — policy evaluation / compile / property proof
**Objective.** Implement policy evaluation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00170 — prompt injection resistance / compile / property proof
**Objective.** Implement prompt injection resistance so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00171 — secret isolation / compile / property proof
**Objective.** Implement secret isolation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00172 — tenant isolation / compile / property proof
**Objective.** Implement tenant isolation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00173 — PII handling / compile / property proof
**Objective.** Implement PII handling so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00174 — data classification / compile / property proof
**Objective.** Implement data classification so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00175 — authorization / compile / property proof
**Objective.** Implement authorization so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00176 — approval gates / compile / property proof
**Objective.** Implement approval gates so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00177 — sandbox boundary / compile / property proof
**Objective.** Implement sandbox boundary so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00178 — supply-chain trust / compile / property proof
**Objective.** Implement supply-chain trust so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00179 — audit evidence / compile / property proof
**Objective.** Implement audit evidence so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00180 — incident fail-closed / compile / property proof
**Objective.** Implement incident fail-closed so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00181 — policy evaluation / execute / property proof
**Objective.** Implement policy evaluation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00182 — prompt injection resistance / execute / property proof
**Objective.** Implement prompt injection resistance so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00183 — secret isolation / execute / property proof
**Objective.** Implement secret isolation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00184 — tenant isolation / execute / property proof
**Objective.** Implement tenant isolation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00185 — PII handling / execute / property proof
**Objective.** Implement PII handling so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00186 — data classification / execute / property proof
**Objective.** Implement data classification so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00187 — authorization / execute / property proof
**Objective.** Implement authorization so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00188 — approval gates / execute / property proof
**Objective.** Implement approval gates so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00189 — sandbox boundary / execute / property proof
**Objective.** Implement sandbox boundary so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00190 — supply-chain trust / execute / property proof
**Objective.** Implement supply-chain trust so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00191 — audit evidence / execute / property proof
**Objective.** Implement audit evidence so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00192 — incident fail-closed / execute / property proof
**Objective.** Implement incident fail-closed so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00193 — policy evaluation / observe / property proof
**Objective.** Implement policy evaluation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00194 — prompt injection resistance / observe / property proof
**Objective.** Implement prompt injection resistance so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00195 — secret isolation / observe / property proof
**Objective.** Implement secret isolation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00196 — tenant isolation / observe / property proof
**Objective.** Implement tenant isolation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00197 — PII handling / observe / property proof
**Objective.** Implement PII handling so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00198 — data classification / observe / property proof
**Objective.** Implement data classification so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00199 — authorization / observe / property proof
**Objective.** Implement authorization so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00200 — approval gates / observe / property proof
**Objective.** Implement approval gates so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00201 — sandbox boundary / observe / property proof
**Objective.** Implement sandbox boundary so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00202 — supply-chain trust / observe / property proof
**Objective.** Implement supply-chain trust so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00203 — audit evidence / observe / property proof
**Objective.** Implement audit evidence so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00204 — incident fail-closed / observe / property proof
**Objective.** Implement incident fail-closed so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00205 — policy evaluation / verify / property proof
**Objective.** Implement policy evaluation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00206 — prompt injection resistance / verify / property proof
**Objective.** Implement prompt injection resistance so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00207 — secret isolation / verify / property proof
**Objective.** Implement secret isolation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00208 — tenant isolation / verify / property proof
**Objective.** Implement tenant isolation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00209 — PII handling / verify / property proof
**Objective.** Implement PII handling so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00210 — data classification / verify / property proof
**Objective.** Implement data classification so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00211 — authorization / verify / property proof
**Objective.** Implement authorization so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00212 — approval gates / verify / property proof
**Objective.** Implement approval gates so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00213 — sandbox boundary / verify / property proof
**Objective.** Implement sandbox boundary so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00214 — supply-chain trust / verify / property proof
**Objective.** Implement supply-chain trust so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00215 — audit evidence / verify / property proof
**Objective.** Implement audit evidence so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00216 — incident fail-closed / verify / property proof
**Objective.** Implement incident fail-closed so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00217 — policy evaluation / recover / property proof
**Objective.** Implement policy evaluation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00218 — prompt injection resistance / recover / property proof
**Objective.** Implement prompt injection resistance so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00219 — secret isolation / recover / property proof
**Objective.** Implement secret isolation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00220 — tenant isolation / recover / property proof
**Objective.** Implement tenant isolation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00221 — PII handling / recover / property proof
**Objective.** Implement PII handling so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00222 — data classification / recover / property proof
**Objective.** Implement data classification so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00223 — authorization / recover / property proof
**Objective.** Implement authorization so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00224 — approval gates / recover / property proof
**Objective.** Implement approval gates so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00225 — sandbox boundary / recover / property proof
**Objective.** Implement sandbox boundary so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00226 — supply-chain trust / recover / property proof
**Objective.** Implement supply-chain trust so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00227 — audit evidence / recover / property proof
**Objective.** Implement audit evidence so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00228 — incident fail-closed / recover / property proof
**Objective.** Implement incident fail-closed so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00229 — policy evaluation / replay / property proof
**Objective.** Implement policy evaluation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00230 — prompt injection resistance / replay / property proof
**Objective.** Implement prompt injection resistance so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00231 — secret isolation / replay / property proof
**Objective.** Implement secret isolation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00232 — tenant isolation / replay / property proof
**Objective.** Implement tenant isolation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00233 — PII handling / replay / property proof
**Objective.** Implement PII handling so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00234 — data classification / replay / property proof
**Objective.** Implement data classification so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00235 — authorization / replay / property proof
**Objective.** Implement authorization so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00236 — approval gates / replay / property proof
**Objective.** Implement approval gates so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00237 — sandbox boundary / replay / property proof
**Objective.** Implement sandbox boundary so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00238 — supply-chain trust / replay / property proof
**Objective.** Implement supply-chain trust so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00239 — audit evidence / replay / property proof
**Objective.** Implement audit evidence so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00240 — incident fail-closed / replay / property proof
**Objective.** Implement incident fail-closed so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00241 — policy evaluation / optimize / property proof
**Objective.** Implement policy evaluation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00242 — prompt injection resistance / optimize / property proof
**Objective.** Implement prompt injection resistance so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00243 — secret isolation / optimize / property proof
**Objective.** Implement secret isolation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00244 — tenant isolation / optimize / property proof
**Objective.** Implement tenant isolation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00245 — PII handling / optimize / property proof
**Objective.** Implement PII handling so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00246 — data classification / optimize / property proof
**Objective.** Implement data classification so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00247 — authorization / optimize / property proof
**Objective.** Implement authorization so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00248 — approval gates / optimize / property proof
**Objective.** Implement approval gates so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/approval_gates.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00249 — sandbox boundary / optimize / property proof
**Objective.** Implement sandbox boundary so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/sandbox_boundary.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00250 — supply-chain trust / optimize / property proof
**Objective.** Implement supply-chain trust so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/supply_chain_trust.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00251 — audit evidence / optimize / property proof
**Objective.** Implement audit evidence so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/audit_evidence.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00252 — incident fail-closed / optimize / property proof
**Objective.** Implement incident fail-closed so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/incident_fail_closed.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00253 — policy evaluation / promote / property proof
**Objective.** Implement policy evaluation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/policy_evaluation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00254 — prompt injection resistance / promote / property proof
**Objective.** Implement prompt injection resistance so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/prompt_injection_resistance.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00255 — secret isolation / promote / property proof
**Objective.** Implement secret isolation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/secret_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00256 — tenant isolation / promote / property proof
**Objective.** Implement tenant isolation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/tenant_isolation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00257 — PII handling / promote / property proof
**Objective.** Implement PII handling so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/pii_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00258 — data classification / promote / property proof
**Objective.** Implement data classification so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/data_classification.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-05-00259 — authorization / promote / property proof
**Objective.** Implement authorization so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/security/authorization.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.


## Coverage Closure Matrix

This matrix closes dimensional coverage that cannot be inferred from atom count. Every listed subsystem is mandatory; omission is a specification failure, not a deferred enhancement.

**Required lifecycle set:** `contract`, `admission`, `compile`, `execute`, `observe`, `verify`, `recover`, `replay`, `optimize`, `promote`, `rollback`, `retire`.

**Required evidence set:** `unit proof`, `property proof`, `integration proof`, `fault injection`, `determinism proof`, `security proof`, `performance proof`, `recovery proof`, `provenance proof`, `compatibility proof`.

**Required stress set:** `cold start`, `warm path`, `partial failure`, `dependency timeout`, `cancellation race`, `stale state`, `concurrent mutation`, `resource pressure`, `malformed input`, `version skew`, `reconnect replay`, `cross-platform run`.

**Cross-product law.** Every subsystem must have executable acceptance evidence in every lifecycle stage. Every subsystem must exercise every evidence class across its implementation and release qualification. Every stress scenario must be represented in the plane’s regression suite; security, rights, recovery, cancellation, replay, and persistent-state mutations require explicit negative-path coverage. Risk-based reduction may reduce redundant test instances, but it may not remove a named dimension or leave any subsystem without coverage.

### COV-FLGB-05-01 — policy evaluation

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-02 — prompt injection resistance

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-03 — secret isolation

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-04 — tenant isolation

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-05 — PII handling

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-06 — data classification

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-07 — authorization

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-08 — approval gates

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-09 — sandbox boundary

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-10 — supply-chain trust

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-11 — audit evidence

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

### COV-FLGB-05-12 — incident fail-closed

- **Lifecycle closure:** contract → admission → compile → execute → observe → verify → recover → replay → optimize → promote → rollback → retire.
- **Evidence closure:** unit proof; property proof; integration proof; fault injection; determinism proof; security proof; performance proof; recovery proof; provenance proof; compatibility proof.
- **Stress closure:** cold start; warm path; partial failure; dependency timeout; cancellation race; stale state; concurrent mutation; resource pressure; malformed input; version skew; reconnect replay; cross-platform run.
- **Durability invariant:** identity, schema version, authority, budget, deadline, cancellation, provenance, replay state, rollback state, and terminal outcome remain explicit across failures and restarts.
- **LLM/game-builder invariant:** model output remains a candidate until deterministic policy/verification authorizes promotion; project state cannot be mutated through conversational text alone.
- **Closure rule:** implementation and independent verification remain unsigned until exact-head executable evidence names this coverage ID and the concrete implementation identity.

