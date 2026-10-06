# FLGB-01 — LLM Session and Inference Runtime

Canonical overlay: Functional LLM + Game Builder 10MB execution atlas
Masterplan relationship: depth-only; VOL-000..420 breadth freeze preserved
Implementation authority: none; this file defines requirements and evidence targets
Implementation signed: false
Independent verification signed: false

## Plane objective
Deliver a production-functional plane for LLM Session and Inference Runtime that composes with the provider-neutral LLM runtime and the governed AI game builder. Every atom below is non-compensable within its stated scope: unresolved atoms remain explicit gaps and cannot be erased by benchmark gains elsewhere.

## FLGB-01-00001 — operation envelope / contract / unit proof
**Objective.** Implement operation envelope so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00002 — conversation state / contract / unit proof
**Objective.** Implement conversation state so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00003 — provider-neutral request / contract / unit proof
**Objective.** Implement provider-neutral request so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00004 — stream decoder / contract / unit proof
**Objective.** Implement stream decoder so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00005 — structured output / contract / unit proof
**Objective.** Implement structured output so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00006 — tool-call proposal / contract / unit proof
**Objective.** Implement tool-call proposal so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00007 — cancellation / contract / unit proof
**Objective.** Implement cancellation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00008 — deadline / contract / unit proof
**Objective.** Implement deadline so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00009 — usage accounting / contract / unit proof
**Objective.** Implement usage accounting so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00010 — terminal commit / contract / unit proof
**Objective.** Implement terminal commit so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00011 — replay receipt / contract / unit proof
**Objective.** Implement replay receipt so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00012 — provider failover / contract / unit proof
**Objective.** Implement provider failover so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00013 — operation envelope / admission / unit proof
**Objective.** Implement operation envelope so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00014 — conversation state / admission / unit proof
**Objective.** Implement conversation state so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00015 — provider-neutral request / admission / unit proof
**Objective.** Implement provider-neutral request so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00016 — stream decoder / admission / unit proof
**Objective.** Implement stream decoder so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00017 — structured output / admission / unit proof
**Objective.** Implement structured output so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00018 — tool-call proposal / admission / unit proof
**Objective.** Implement tool-call proposal so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00019 — cancellation / admission / unit proof
**Objective.** Implement cancellation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00020 — deadline / admission / unit proof
**Objective.** Implement deadline so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00021 — usage accounting / admission / unit proof
**Objective.** Implement usage accounting so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00022 — terminal commit / admission / unit proof
**Objective.** Implement terminal commit so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00023 — replay receipt / admission / unit proof
**Objective.** Implement replay receipt so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00024 — provider failover / admission / unit proof
**Objective.** Implement provider failover so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00025 — operation envelope / compile / unit proof
**Objective.** Implement operation envelope so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00026 — conversation state / compile / unit proof
**Objective.** Implement conversation state so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00027 — provider-neutral request / compile / unit proof
**Objective.** Implement provider-neutral request so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00028 — stream decoder / compile / unit proof
**Objective.** Implement stream decoder so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00029 — structured output / compile / unit proof
**Objective.** Implement structured output so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00030 — tool-call proposal / compile / unit proof
**Objective.** Implement tool-call proposal so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00031 — cancellation / compile / unit proof
**Objective.** Implement cancellation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00032 — deadline / compile / unit proof
**Objective.** Implement deadline so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00033 — usage accounting / compile / unit proof
**Objective.** Implement usage accounting so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00034 — terminal commit / compile / unit proof
**Objective.** Implement terminal commit so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00035 — replay receipt / compile / unit proof
**Objective.** Implement replay receipt so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00036 — provider failover / compile / unit proof
**Objective.** Implement provider failover so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00037 — operation envelope / execute / unit proof
**Objective.** Implement operation envelope so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00038 — conversation state / execute / unit proof
**Objective.** Implement conversation state so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00039 — provider-neutral request / execute / unit proof
**Objective.** Implement provider-neutral request so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00040 — stream decoder / execute / unit proof
**Objective.** Implement stream decoder so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00041 — structured output / execute / unit proof
**Objective.** Implement structured output so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00042 — tool-call proposal / execute / unit proof
**Objective.** Implement tool-call proposal so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00043 — cancellation / execute / unit proof
**Objective.** Implement cancellation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00044 — deadline / execute / unit proof
**Objective.** Implement deadline so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00045 — usage accounting / execute / unit proof
**Objective.** Implement usage accounting so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00046 — terminal commit / execute / unit proof
**Objective.** Implement terminal commit so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00047 — replay receipt / execute / unit proof
**Objective.** Implement replay receipt so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00048 — provider failover / execute / unit proof
**Objective.** Implement provider failover so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00049 — operation envelope / observe / unit proof
**Objective.** Implement operation envelope so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00050 — conversation state / observe / unit proof
**Objective.** Implement conversation state so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00051 — provider-neutral request / observe / unit proof
**Objective.** Implement provider-neutral request so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00052 — stream decoder / observe / unit proof
**Objective.** Implement stream decoder so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00053 — structured output / observe / unit proof
**Objective.** Implement structured output so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00054 — tool-call proposal / observe / unit proof
**Objective.** Implement tool-call proposal so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00055 — cancellation / observe / unit proof
**Objective.** Implement cancellation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00056 — deadline / observe / unit proof
**Objective.** Implement deadline so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00057 — usage accounting / observe / unit proof
**Objective.** Implement usage accounting so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00058 — terminal commit / observe / unit proof
**Objective.** Implement terminal commit so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00059 — replay receipt / observe / unit proof
**Objective.** Implement replay receipt so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00060 — provider failover / observe / unit proof
**Objective.** Implement provider failover so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00061 — operation envelope / verify / unit proof
**Objective.** Implement operation envelope so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00062 — conversation state / verify / unit proof
**Objective.** Implement conversation state so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00063 — provider-neutral request / verify / unit proof
**Objective.** Implement provider-neutral request so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00064 — stream decoder / verify / unit proof
**Objective.** Implement stream decoder so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00065 — structured output / verify / unit proof
**Objective.** Implement structured output so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00066 — tool-call proposal / verify / unit proof
**Objective.** Implement tool-call proposal so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00067 — cancellation / verify / unit proof
**Objective.** Implement cancellation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00068 — deadline / verify / unit proof
**Objective.** Implement deadline so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00069 — usage accounting / verify / unit proof
**Objective.** Implement usage accounting so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00070 — terminal commit / verify / unit proof
**Objective.** Implement terminal commit so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00071 — replay receipt / verify / unit proof
**Objective.** Implement replay receipt so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00072 — provider failover / verify / unit proof
**Objective.** Implement provider failover so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00073 — operation envelope / recover / unit proof
**Objective.** Implement operation envelope so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00074 — conversation state / recover / unit proof
**Objective.** Implement conversation state so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00075 — provider-neutral request / recover / unit proof
**Objective.** Implement provider-neutral request so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00076 — stream decoder / recover / unit proof
**Objective.** Implement stream decoder so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00077 — structured output / recover / unit proof
**Objective.** Implement structured output so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00078 — tool-call proposal / recover / unit proof
**Objective.** Implement tool-call proposal so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00079 — cancellation / recover / unit proof
**Objective.** Implement cancellation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00080 — deadline / recover / unit proof
**Objective.** Implement deadline so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00081 — usage accounting / recover / unit proof
**Objective.** Implement usage accounting so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00082 — terminal commit / recover / unit proof
**Objective.** Implement terminal commit so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00083 — replay receipt / recover / unit proof
**Objective.** Implement replay receipt so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00084 — provider failover / recover / unit proof
**Objective.** Implement provider failover so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00085 — operation envelope / replay / unit proof
**Objective.** Implement operation envelope so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00086 — conversation state / replay / unit proof
**Objective.** Implement conversation state so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00087 — provider-neutral request / replay / unit proof
**Objective.** Implement provider-neutral request so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00088 — stream decoder / replay / unit proof
**Objective.** Implement stream decoder so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00089 — structured output / replay / unit proof
**Objective.** Implement structured output so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00090 — tool-call proposal / replay / unit proof
**Objective.** Implement tool-call proposal so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00091 — cancellation / replay / unit proof
**Objective.** Implement cancellation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00092 — deadline / replay / unit proof
**Objective.** Implement deadline so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00093 — usage accounting / replay / unit proof
**Objective.** Implement usage accounting so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00094 — terminal commit / replay / unit proof
**Objective.** Implement terminal commit so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00095 — replay receipt / replay / unit proof
**Objective.** Implement replay receipt so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00096 — provider failover / replay / unit proof
**Objective.** Implement provider failover so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00097 — operation envelope / optimize / unit proof
**Objective.** Implement operation envelope so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00098 — conversation state / optimize / unit proof
**Objective.** Implement conversation state so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00099 — provider-neutral request / optimize / unit proof
**Objective.** Implement provider-neutral request so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00100 — stream decoder / optimize / unit proof
**Objective.** Implement stream decoder so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00101 — structured output / optimize / unit proof
**Objective.** Implement structured output so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00102 — tool-call proposal / optimize / unit proof
**Objective.** Implement tool-call proposal so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00103 — cancellation / optimize / unit proof
**Objective.** Implement cancellation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00104 — deadline / optimize / unit proof
**Objective.** Implement deadline so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00105 — usage accounting / optimize / unit proof
**Objective.** Implement usage accounting so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00106 — terminal commit / optimize / unit proof
**Objective.** Implement terminal commit so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00107 — replay receipt / optimize / unit proof
**Objective.** Implement replay receipt so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00108 — provider failover / optimize / unit proof
**Objective.** Implement provider failover so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00109 — operation envelope / promote / unit proof
**Objective.** Implement operation envelope so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00110 — conversation state / promote / unit proof
**Objective.** Implement conversation state so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00111 — provider-neutral request / promote / unit proof
**Objective.** Implement provider-neutral request so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00112 — stream decoder / promote / unit proof
**Objective.** Implement stream decoder so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00113 — structured output / promote / unit proof
**Objective.** Implement structured output so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00114 — tool-call proposal / promote / unit proof
**Objective.** Implement tool-call proposal so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00115 — cancellation / promote / unit proof
**Objective.** Implement cancellation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00116 — deadline / promote / unit proof
**Objective.** Implement deadline so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00117 — usage accounting / promote / unit proof
**Objective.** Implement usage accounting so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00118 — terminal commit / promote / unit proof
**Objective.** Implement terminal commit so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00119 — replay receipt / promote / unit proof
**Objective.** Implement replay receipt so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00120 — provider failover / promote / unit proof
**Objective.** Implement provider failover so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00121 — operation envelope / rollback / unit proof
**Objective.** Implement operation envelope so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00122 — conversation state / rollback / unit proof
**Objective.** Implement conversation state so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00123 — provider-neutral request / rollback / unit proof
**Objective.** Implement provider-neutral request so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00124 — stream decoder / rollback / unit proof
**Objective.** Implement stream decoder so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00125 — structured output / rollback / unit proof
**Objective.** Implement structured output so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00126 — tool-call proposal / rollback / unit proof
**Objective.** Implement tool-call proposal so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00127 — cancellation / rollback / unit proof
**Objective.** Implement cancellation so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00128 — deadline / rollback / unit proof
**Objective.** Implement deadline so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00129 — usage accounting / rollback / unit proof
**Objective.** Implement usage accounting so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00130 — terminal commit / rollback / unit proof
**Objective.** Implement terminal commit so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00131 — replay receipt / rollback / unit proof
**Objective.** Implement replay receipt so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00132 — provider failover / rollback / unit proof
**Objective.** Implement provider failover so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00133 — operation envelope / retire / unit proof
**Objective.** Implement operation envelope so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00134 — conversation state / retire / unit proof
**Objective.** Implement conversation state so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00135 — provider-neutral request / retire / unit proof
**Objective.** Implement provider-neutral request so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00136 — stream decoder / retire / unit proof
**Objective.** Implement stream decoder so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00137 — structured output / retire / unit proof
**Objective.** Implement structured output so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00138 — tool-call proposal / retire / unit proof
**Objective.** Implement tool-call proposal so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00139 — cancellation / retire / unit proof
**Objective.** Implement cancellation so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00140 — deadline / retire / unit proof
**Objective.** Implement deadline so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00141 — usage accounting / retire / unit proof
**Objective.** Implement usage accounting so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00142 — terminal commit / retire / unit proof
**Objective.** Implement terminal commit so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00143 — replay receipt / retire / unit proof
**Objective.** Implement replay receipt so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00144 — provider failover / retire / unit proof
**Objective.** Implement provider failover so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00145 — operation envelope / contract / property proof
**Objective.** Implement operation envelope so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00146 — conversation state / contract / property proof
**Objective.** Implement conversation state so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00147 — provider-neutral request / contract / property proof
**Objective.** Implement provider-neutral request so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00148 — stream decoder / contract / property proof
**Objective.** Implement stream decoder so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00149 — structured output / contract / property proof
**Objective.** Implement structured output so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00150 — tool-call proposal / contract / property proof
**Objective.** Implement tool-call proposal so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00151 — cancellation / contract / property proof
**Objective.** Implement cancellation so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00152 — deadline / contract / property proof
**Objective.** Implement deadline so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00153 — usage accounting / contract / property proof
**Objective.** Implement usage accounting so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00154 — terminal commit / contract / property proof
**Objective.** Implement terminal commit so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00155 — replay receipt / contract / property proof
**Objective.** Implement replay receipt so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00156 — provider failover / contract / property proof
**Objective.** Implement provider failover so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00157 — operation envelope / admission / property proof
**Objective.** Implement operation envelope so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00158 — conversation state / admission / property proof
**Objective.** Implement conversation state so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00159 — provider-neutral request / admission / property proof
**Objective.** Implement provider-neutral request so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00160 — stream decoder / admission / property proof
**Objective.** Implement stream decoder so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00161 — structured output / admission / property proof
**Objective.** Implement structured output so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00162 — tool-call proposal / admission / property proof
**Objective.** Implement tool-call proposal so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00163 — cancellation / admission / property proof
**Objective.** Implement cancellation so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00164 — deadline / admission / property proof
**Objective.** Implement deadline so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00165 — usage accounting / admission / property proof
**Objective.** Implement usage accounting so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00166 — terminal commit / admission / property proof
**Objective.** Implement terminal commit so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00167 — replay receipt / admission / property proof
**Objective.** Implement replay receipt so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00168 — provider failover / admission / property proof
**Objective.** Implement provider failover so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00169 — operation envelope / compile / property proof
**Objective.** Implement operation envelope so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00170 — conversation state / compile / property proof
**Objective.** Implement conversation state so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00171 — provider-neutral request / compile / property proof
**Objective.** Implement provider-neutral request so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00172 — stream decoder / compile / property proof
**Objective.** Implement stream decoder so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00173 — structured output / compile / property proof
**Objective.** Implement structured output so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00174 — tool-call proposal / compile / property proof
**Objective.** Implement tool-call proposal so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00175 — cancellation / compile / property proof
**Objective.** Implement cancellation so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00176 — deadline / compile / property proof
**Objective.** Implement deadline so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00177 — usage accounting / compile / property proof
**Objective.** Implement usage accounting so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00178 — terminal commit / compile / property proof
**Objective.** Implement terminal commit so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00179 — replay receipt / compile / property proof
**Objective.** Implement replay receipt so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00180 — provider failover / compile / property proof
**Objective.** Implement provider failover so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00181 — operation envelope / execute / property proof
**Objective.** Implement operation envelope so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00182 — conversation state / execute / property proof
**Objective.** Implement conversation state so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00183 — provider-neutral request / execute / property proof
**Objective.** Implement provider-neutral request so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00184 — stream decoder / execute / property proof
**Objective.** Implement stream decoder so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00185 — structured output / execute / property proof
**Objective.** Implement structured output so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00186 — tool-call proposal / execute / property proof
**Objective.** Implement tool-call proposal so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00187 — cancellation / execute / property proof
**Objective.** Implement cancellation so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00188 — deadline / execute / property proof
**Objective.** Implement deadline so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00189 — usage accounting / execute / property proof
**Objective.** Implement usage accounting so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00190 — terminal commit / execute / property proof
**Objective.** Implement terminal commit so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00191 — replay receipt / execute / property proof
**Objective.** Implement replay receipt so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00192 — provider failover / execute / property proof
**Objective.** Implement provider failover so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00193 — operation envelope / observe / property proof
**Objective.** Implement operation envelope so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00194 — conversation state / observe / property proof
**Objective.** Implement conversation state so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00195 — provider-neutral request / observe / property proof
**Objective.** Implement provider-neutral request so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00196 — stream decoder / observe / property proof
**Objective.** Implement stream decoder so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00197 — structured output / observe / property proof
**Objective.** Implement structured output so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00198 — tool-call proposal / observe / property proof
**Objective.** Implement tool-call proposal so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00199 — cancellation / observe / property proof
**Objective.** Implement cancellation so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00200 — deadline / observe / property proof
**Objective.** Implement deadline so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00201 — usage accounting / observe / property proof
**Objective.** Implement usage accounting so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00202 — terminal commit / observe / property proof
**Objective.** Implement terminal commit so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00203 — replay receipt / observe / property proof
**Objective.** Implement replay receipt so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00204 — provider failover / observe / property proof
**Objective.** Implement provider failover so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00205 — operation envelope / verify / property proof
**Objective.** Implement operation envelope so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00206 — conversation state / verify / property proof
**Objective.** Implement conversation state so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00207 — provider-neutral request / verify / property proof
**Objective.** Implement provider-neutral request so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00208 — stream decoder / verify / property proof
**Objective.** Implement stream decoder so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00209 — structured output / verify / property proof
**Objective.** Implement structured output so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00210 — tool-call proposal / verify / property proof
**Objective.** Implement tool-call proposal so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00211 — cancellation / verify / property proof
**Objective.** Implement cancellation so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00212 — deadline / verify / property proof
**Objective.** Implement deadline so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00213 — usage accounting / verify / property proof
**Objective.** Implement usage accounting so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00214 — terminal commit / verify / property proof
**Objective.** Implement terminal commit so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00215 — replay receipt / verify / property proof
**Objective.** Implement replay receipt so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00216 — provider failover / verify / property proof
**Objective.** Implement provider failover so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00217 — operation envelope / recover / property proof
**Objective.** Implement operation envelope so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00218 — conversation state / recover / property proof
**Objective.** Implement conversation state so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00219 — provider-neutral request / recover / property proof
**Objective.** Implement provider-neutral request so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00220 — stream decoder / recover / property proof
**Objective.** Implement stream decoder so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00221 — structured output / recover / property proof
**Objective.** Implement structured output so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00222 — tool-call proposal / recover / property proof
**Objective.** Implement tool-call proposal so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00223 — cancellation / recover / property proof
**Objective.** Implement cancellation so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00224 — deadline / recover / property proof
**Objective.** Implement deadline so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00225 — usage accounting / recover / property proof
**Objective.** Implement usage accounting so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00226 — terminal commit / recover / property proof
**Objective.** Implement terminal commit so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00227 — replay receipt / recover / property proof
**Objective.** Implement replay receipt so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00228 — provider failover / recover / property proof
**Objective.** Implement provider failover so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00229 — operation envelope / replay / property proof
**Objective.** Implement operation envelope so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00230 — conversation state / replay / property proof
**Objective.** Implement conversation state so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00231 — provider-neutral request / replay / property proof
**Objective.** Implement provider-neutral request so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00232 — stream decoder / replay / property proof
**Objective.** Implement stream decoder so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00233 — structured output / replay / property proof
**Objective.** Implement structured output so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00234 — tool-call proposal / replay / property proof
**Objective.** Implement tool-call proposal so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00235 — cancellation / replay / property proof
**Objective.** Implement cancellation so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00236 — deadline / replay / property proof
**Objective.** Implement deadline so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00237 — usage accounting / replay / property proof
**Objective.** Implement usage accounting so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00238 — terminal commit / replay / property proof
**Objective.** Implement terminal commit so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00239 — replay receipt / replay / property proof
**Objective.** Implement replay receipt so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00240 — provider failover / replay / property proof
**Objective.** Implement provider failover so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00241 — operation envelope / optimize / property proof
**Objective.** Implement operation envelope so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00242 — conversation state / optimize / property proof
**Objective.** Implement conversation state so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00243 — provider-neutral request / optimize / property proof
**Objective.** Implement provider-neutral request so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00244 — stream decoder / optimize / property proof
**Objective.** Implement stream decoder so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00245 — structured output / optimize / property proof
**Objective.** Implement structured output so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00246 — tool-call proposal / optimize / property proof
**Objective.** Implement tool-call proposal so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00247 — cancellation / optimize / property proof
**Objective.** Implement cancellation so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00248 — deadline / optimize / property proof
**Objective.** Implement deadline so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/deadline.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00249 — usage accounting / optimize / property proof
**Objective.** Implement usage accounting so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/usage_accounting.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00250 — terminal commit / optimize / property proof
**Objective.** Implement terminal commit so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/terminal_commit.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00251 — replay receipt / optimize / property proof
**Objective.** Implement replay receipt so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/replay_receipt.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00252 — provider failover / optimize / property proof
**Objective.** Implement provider failover so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_failover.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00253 — operation envelope / promote / property proof
**Objective.** Implement operation envelope so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/operation_envelope.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00254 — conversation state / promote / property proof
**Objective.** Implement conversation state so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/conversation_state.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00255 — provider-neutral request / promote / property proof
**Objective.** Implement provider-neutral request so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/provider_neutral_request.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00256 — stream decoder / promote / property proof
**Objective.** Implement stream decoder so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/stream_decoder.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00257 — structured output / promote / property proof
**Objective.** Implement structured output so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/structured_output.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00258 — tool-call proposal / promote / property proof
**Objective.** Implement tool-call proposal so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/tool_call_proposal.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-01-00259 — cancellation / promote / property proof
**Objective.** Implement cancellation so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/inference/cancellation.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

