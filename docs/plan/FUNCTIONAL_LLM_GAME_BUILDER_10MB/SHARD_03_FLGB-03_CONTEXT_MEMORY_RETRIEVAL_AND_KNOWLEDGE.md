# FLGB-03 — Context Memory Retrieval and Knowledge

Canonical overlay: Functional LLM + Game Builder 10MB execution atlas
Masterplan relationship: depth-only; VOL-000..420 breadth freeze preserved
Implementation authority: none; this file defines requirements and evidence targets
Implementation signed: false
Independent verification signed: false

## Plane objective
Deliver a production-functional plane for Context Memory Retrieval and Knowledge that composes with the provider-neutral LLM runtime and the governed AI game builder. Every atom below is non-compensable within its stated scope: unresolved atoms remain explicit gaps and cannot be erased by benchmark gains elsewhere.

## FLGB-03-00001 — context compiler / contract / unit proof
**Objective.** Implement context compiler so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00002 — working memory / contract / unit proof
**Objective.** Implement working memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00003 — episodic memory / contract / unit proof
**Objective.** Implement episodic memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00004 — semantic memory / contract / unit proof
**Objective.** Implement semantic memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00005 — project memory / contract / unit proof
**Objective.** Implement project memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00006 — hybrid retrieval / contract / unit proof
**Objective.** Implement hybrid retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00007 — code retrieval / contract / unit proof
**Objective.** Implement code retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00008 — graph retrieval / contract / unit proof
**Objective.** Implement graph retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00009 — temporal retrieval / contract / unit proof
**Objective.** Implement temporal retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00010 — claim evidence graph / contract / unit proof
**Objective.** Implement claim evidence graph so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00011 — contradiction handling / contract / unit proof
**Objective.** Implement contradiction handling so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00012 — context compression / contract / unit proof
**Objective.** Implement context compression so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00013 — context compiler / admission / unit proof
**Objective.** Implement context compiler so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00014 — working memory / admission / unit proof
**Objective.** Implement working memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00015 — episodic memory / admission / unit proof
**Objective.** Implement episodic memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00016 — semantic memory / admission / unit proof
**Objective.** Implement semantic memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00017 — project memory / admission / unit proof
**Objective.** Implement project memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00018 — hybrid retrieval / admission / unit proof
**Objective.** Implement hybrid retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00019 — code retrieval / admission / unit proof
**Objective.** Implement code retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00020 — graph retrieval / admission / unit proof
**Objective.** Implement graph retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00021 — temporal retrieval / admission / unit proof
**Objective.** Implement temporal retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00022 — claim evidence graph / admission / unit proof
**Objective.** Implement claim evidence graph so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00023 — contradiction handling / admission / unit proof
**Objective.** Implement contradiction handling so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00024 — context compression / admission / unit proof
**Objective.** Implement context compression so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00025 — context compiler / compile / unit proof
**Objective.** Implement context compiler so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00026 — working memory / compile / unit proof
**Objective.** Implement working memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00027 — episodic memory / compile / unit proof
**Objective.** Implement episodic memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00028 — semantic memory / compile / unit proof
**Objective.** Implement semantic memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00029 — project memory / compile / unit proof
**Objective.** Implement project memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00030 — hybrid retrieval / compile / unit proof
**Objective.** Implement hybrid retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00031 — code retrieval / compile / unit proof
**Objective.** Implement code retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00032 — graph retrieval / compile / unit proof
**Objective.** Implement graph retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00033 — temporal retrieval / compile / unit proof
**Objective.** Implement temporal retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00034 — claim evidence graph / compile / unit proof
**Objective.** Implement claim evidence graph so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00035 — contradiction handling / compile / unit proof
**Objective.** Implement contradiction handling so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00036 — context compression / compile / unit proof
**Objective.** Implement context compression so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00037 — context compiler / execute / unit proof
**Objective.** Implement context compiler so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00038 — working memory / execute / unit proof
**Objective.** Implement working memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00039 — episodic memory / execute / unit proof
**Objective.** Implement episodic memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00040 — semantic memory / execute / unit proof
**Objective.** Implement semantic memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00041 — project memory / execute / unit proof
**Objective.** Implement project memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00042 — hybrid retrieval / execute / unit proof
**Objective.** Implement hybrid retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00043 — code retrieval / execute / unit proof
**Objective.** Implement code retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00044 — graph retrieval / execute / unit proof
**Objective.** Implement graph retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00045 — temporal retrieval / execute / unit proof
**Objective.** Implement temporal retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00046 — claim evidence graph / execute / unit proof
**Objective.** Implement claim evidence graph so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00047 — contradiction handling / execute / unit proof
**Objective.** Implement contradiction handling so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00048 — context compression / execute / unit proof
**Objective.** Implement context compression so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00049 — context compiler / observe / unit proof
**Objective.** Implement context compiler so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00050 — working memory / observe / unit proof
**Objective.** Implement working memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00051 — episodic memory / observe / unit proof
**Objective.** Implement episodic memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00052 — semantic memory / observe / unit proof
**Objective.** Implement semantic memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00053 — project memory / observe / unit proof
**Objective.** Implement project memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00054 — hybrid retrieval / observe / unit proof
**Objective.** Implement hybrid retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00055 — code retrieval / observe / unit proof
**Objective.** Implement code retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00056 — graph retrieval / observe / unit proof
**Objective.** Implement graph retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00057 — temporal retrieval / observe / unit proof
**Objective.** Implement temporal retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00058 — claim evidence graph / observe / unit proof
**Objective.** Implement claim evidence graph so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00059 — contradiction handling / observe / unit proof
**Objective.** Implement contradiction handling so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00060 — context compression / observe / unit proof
**Objective.** Implement context compression so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00061 — context compiler / verify / unit proof
**Objective.** Implement context compiler so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00062 — working memory / verify / unit proof
**Objective.** Implement working memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00063 — episodic memory / verify / unit proof
**Objective.** Implement episodic memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00064 — semantic memory / verify / unit proof
**Objective.** Implement semantic memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00065 — project memory / verify / unit proof
**Objective.** Implement project memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00066 — hybrid retrieval / verify / unit proof
**Objective.** Implement hybrid retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00067 — code retrieval / verify / unit proof
**Objective.** Implement code retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00068 — graph retrieval / verify / unit proof
**Objective.** Implement graph retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00069 — temporal retrieval / verify / unit proof
**Objective.** Implement temporal retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00070 — claim evidence graph / verify / unit proof
**Objective.** Implement claim evidence graph so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00071 — contradiction handling / verify / unit proof
**Objective.** Implement contradiction handling so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00072 — context compression / verify / unit proof
**Objective.** Implement context compression so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00073 — context compiler / recover / unit proof
**Objective.** Implement context compiler so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00074 — working memory / recover / unit proof
**Objective.** Implement working memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00075 — episodic memory / recover / unit proof
**Objective.** Implement episodic memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00076 — semantic memory / recover / unit proof
**Objective.** Implement semantic memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00077 — project memory / recover / unit proof
**Objective.** Implement project memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00078 — hybrid retrieval / recover / unit proof
**Objective.** Implement hybrid retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00079 — code retrieval / recover / unit proof
**Objective.** Implement code retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00080 — graph retrieval / recover / unit proof
**Objective.** Implement graph retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00081 — temporal retrieval / recover / unit proof
**Objective.** Implement temporal retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00082 — claim evidence graph / recover / unit proof
**Objective.** Implement claim evidence graph so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00083 — contradiction handling / recover / unit proof
**Objective.** Implement contradiction handling so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00084 — context compression / recover / unit proof
**Objective.** Implement context compression so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00085 — context compiler / replay / unit proof
**Objective.** Implement context compiler so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00086 — working memory / replay / unit proof
**Objective.** Implement working memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00087 — episodic memory / replay / unit proof
**Objective.** Implement episodic memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00088 — semantic memory / replay / unit proof
**Objective.** Implement semantic memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00089 — project memory / replay / unit proof
**Objective.** Implement project memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00090 — hybrid retrieval / replay / unit proof
**Objective.** Implement hybrid retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00091 — code retrieval / replay / unit proof
**Objective.** Implement code retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00092 — graph retrieval / replay / unit proof
**Objective.** Implement graph retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00093 — temporal retrieval / replay / unit proof
**Objective.** Implement temporal retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00094 — claim evidence graph / replay / unit proof
**Objective.** Implement claim evidence graph so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00095 — contradiction handling / replay / unit proof
**Objective.** Implement contradiction handling so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00096 — context compression / replay / unit proof
**Objective.** Implement context compression so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00097 — context compiler / optimize / unit proof
**Objective.** Implement context compiler so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00098 — working memory / optimize / unit proof
**Objective.** Implement working memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00099 — episodic memory / optimize / unit proof
**Objective.** Implement episodic memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00100 — semantic memory / optimize / unit proof
**Objective.** Implement semantic memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00101 — project memory / optimize / unit proof
**Objective.** Implement project memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00102 — hybrid retrieval / optimize / unit proof
**Objective.** Implement hybrid retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00103 — code retrieval / optimize / unit proof
**Objective.** Implement code retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00104 — graph retrieval / optimize / unit proof
**Objective.** Implement graph retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00105 — temporal retrieval / optimize / unit proof
**Objective.** Implement temporal retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00106 — claim evidence graph / optimize / unit proof
**Objective.** Implement claim evidence graph so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00107 — contradiction handling / optimize / unit proof
**Objective.** Implement contradiction handling so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00108 — context compression / optimize / unit proof
**Objective.** Implement context compression so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00109 — context compiler / promote / unit proof
**Objective.** Implement context compiler so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00110 — working memory / promote / unit proof
**Objective.** Implement working memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00111 — episodic memory / promote / unit proof
**Objective.** Implement episodic memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00112 — semantic memory / promote / unit proof
**Objective.** Implement semantic memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00113 — project memory / promote / unit proof
**Objective.** Implement project memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00114 — hybrid retrieval / promote / unit proof
**Objective.** Implement hybrid retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00115 — code retrieval / promote / unit proof
**Objective.** Implement code retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00116 — graph retrieval / promote / unit proof
**Objective.** Implement graph retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00117 — temporal retrieval / promote / unit proof
**Objective.** Implement temporal retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00118 — claim evidence graph / promote / unit proof
**Objective.** Implement claim evidence graph so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00119 — contradiction handling / promote / unit proof
**Objective.** Implement contradiction handling so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00120 — context compression / promote / unit proof
**Objective.** Implement context compression so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00121 — context compiler / rollback / unit proof
**Objective.** Implement context compiler so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00122 — working memory / rollback / unit proof
**Objective.** Implement working memory so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00123 — episodic memory / rollback / unit proof
**Objective.** Implement episodic memory so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00124 — semantic memory / rollback / unit proof
**Objective.** Implement semantic memory so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00125 — project memory / rollback / unit proof
**Objective.** Implement project memory so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00126 — hybrid retrieval / rollback / unit proof
**Objective.** Implement hybrid retrieval so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00127 — code retrieval / rollback / unit proof
**Objective.** Implement code retrieval so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00128 — graph retrieval / rollback / unit proof
**Objective.** Implement graph retrieval so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00129 — temporal retrieval / rollback / unit proof
**Objective.** Implement temporal retrieval so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00130 — claim evidence graph / rollback / unit proof
**Objective.** Implement claim evidence graph so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00131 — contradiction handling / rollback / unit proof
**Objective.** Implement contradiction handling so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00132 — context compression / rollback / unit proof
**Objective.** Implement context compression so the rollback stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00133 — context compiler / retire / unit proof
**Objective.** Implement context compiler so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00134 — working memory / retire / unit proof
**Objective.** Implement working memory so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00135 — episodic memory / retire / unit proof
**Objective.** Implement episodic memory so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00136 — semantic memory / retire / unit proof
**Objective.** Implement semantic memory so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00137 — project memory / retire / unit proof
**Objective.** Implement project memory so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00138 — hybrid retrieval / retire / unit proof
**Objective.** Implement hybrid retrieval so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00139 — code retrieval / retire / unit proof
**Objective.** Implement code retrieval so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00140 — graph retrieval / retire / unit proof
**Objective.** Implement graph retrieval so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00141 — temporal retrieval / retire / unit proof
**Objective.** Implement temporal retrieval so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00142 — claim evidence graph / retire / unit proof
**Objective.** Implement claim evidence graph so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00143 — contradiction handling / retire / unit proof
**Objective.** Implement contradiction handling so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00144 — context compression / retire / unit proof
**Objective.** Implement context compression so the retire stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require unit proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00145 — context compiler / contract / property proof
**Objective.** Implement context compiler so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00146 — working memory / contract / property proof
**Objective.** Implement working memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00147 — episodic memory / contract / property proof
**Objective.** Implement episodic memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00148 — semantic memory / contract / property proof
**Objective.** Implement semantic memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00149 — project memory / contract / property proof
**Objective.** Implement project memory so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00150 — hybrid retrieval / contract / property proof
**Objective.** Implement hybrid retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00151 — code retrieval / contract / property proof
**Objective.** Implement code retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00152 — graph retrieval / contract / property proof
**Objective.** Implement graph retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00153 — temporal retrieval / contract / property proof
**Objective.** Implement temporal retrieval so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00154 — claim evidence graph / contract / property proof
**Objective.** Implement claim evidence graph so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00155 — contradiction handling / contract / property proof
**Objective.** Implement contradiction handling so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00156 — context compression / contract / property proof
**Objective.** Implement context compression so the contract stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00157 — context compiler / admission / property proof
**Objective.** Implement context compiler so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00158 — working memory / admission / property proof
**Objective.** Implement working memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00159 — episodic memory / admission / property proof
**Objective.** Implement episodic memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00160 — semantic memory / admission / property proof
**Objective.** Implement semantic memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00161 — project memory / admission / property proof
**Objective.** Implement project memory so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00162 — hybrid retrieval / admission / property proof
**Objective.** Implement hybrid retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00163 — code retrieval / admission / property proof
**Objective.** Implement code retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00164 — graph retrieval / admission / property proof
**Objective.** Implement graph retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00165 — temporal retrieval / admission / property proof
**Objective.** Implement temporal retrieval so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00166 — claim evidence graph / admission / property proof
**Objective.** Implement claim evidence graph so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00167 — contradiction handling / admission / property proof
**Objective.** Implement contradiction handling so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00168 — context compression / admission / property proof
**Objective.** Implement context compression so the admission stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00169 — context compiler / compile / property proof
**Objective.** Implement context compiler so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00170 — working memory / compile / property proof
**Objective.** Implement working memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00171 — episodic memory / compile / property proof
**Objective.** Implement episodic memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00172 — semantic memory / compile / property proof
**Objective.** Implement semantic memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00173 — project memory / compile / property proof
**Objective.** Implement project memory so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00174 — hybrid retrieval / compile / property proof
**Objective.** Implement hybrid retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00175 — code retrieval / compile / property proof
**Objective.** Implement code retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00176 — graph retrieval / compile / property proof
**Objective.** Implement graph retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00177 — temporal retrieval / compile / property proof
**Objective.** Implement temporal retrieval so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00178 — claim evidence graph / compile / property proof
**Objective.** Implement claim evidence graph so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00179 — contradiction handling / compile / property proof
**Objective.** Implement contradiction handling so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00180 — context compression / compile / property proof
**Objective.** Implement context compression so the compile stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00181 — context compiler / execute / property proof
**Objective.** Implement context compiler so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00182 — working memory / execute / property proof
**Objective.** Implement working memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00183 — episodic memory / execute / property proof
**Objective.** Implement episodic memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00184 — semantic memory / execute / property proof
**Objective.** Implement semantic memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00185 — project memory / execute / property proof
**Objective.** Implement project memory so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00186 — hybrid retrieval / execute / property proof
**Objective.** Implement hybrid retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00187 — code retrieval / execute / property proof
**Objective.** Implement code retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00188 — graph retrieval / execute / property proof
**Objective.** Implement graph retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00189 — temporal retrieval / execute / property proof
**Objective.** Implement temporal retrieval so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00190 — claim evidence graph / execute / property proof
**Objective.** Implement claim evidence graph so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00191 — contradiction handling / execute / property proof
**Objective.** Implement contradiction handling so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00192 — context compression / execute / property proof
**Objective.** Implement context compression so the execute stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00193 — context compiler / observe / property proof
**Objective.** Implement context compiler so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00194 — working memory / observe / property proof
**Objective.** Implement working memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00195 — episodic memory / observe / property proof
**Objective.** Implement episodic memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00196 — semantic memory / observe / property proof
**Objective.** Implement semantic memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00197 — project memory / observe / property proof
**Objective.** Implement project memory so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00198 — hybrid retrieval / observe / property proof
**Objective.** Implement hybrid retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00199 — code retrieval / observe / property proof
**Objective.** Implement code retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00200 — graph retrieval / observe / property proof
**Objective.** Implement graph retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00201 — temporal retrieval / observe / property proof
**Objective.** Implement temporal retrieval so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00202 — claim evidence graph / observe / property proof
**Objective.** Implement claim evidence graph so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00203 — contradiction handling / observe / property proof
**Objective.** Implement contradiction handling so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00204 — context compression / observe / property proof
**Objective.** Implement context compression so the observe stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00205 — context compiler / verify / property proof
**Objective.** Implement context compiler so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00206 — working memory / verify / property proof
**Objective.** Implement working memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00207 — episodic memory / verify / property proof
**Objective.** Implement episodic memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00208 — semantic memory / verify / property proof
**Objective.** Implement semantic memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00209 — project memory / verify / property proof
**Objective.** Implement project memory so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00210 — hybrid retrieval / verify / property proof
**Objective.** Implement hybrid retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00211 — code retrieval / verify / property proof
**Objective.** Implement code retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00212 — graph retrieval / verify / property proof
**Objective.** Implement graph retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00213 — temporal retrieval / verify / property proof
**Objective.** Implement temporal retrieval so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00214 — claim evidence graph / verify / property proof
**Objective.** Implement claim evidence graph so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00215 — contradiction handling / verify / property proof
**Objective.** Implement contradiction handling so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00216 — context compression / verify / property proof
**Objective.** Implement context compression so the verify stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00217 — context compiler / recover / property proof
**Objective.** Implement context compiler so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00218 — working memory / recover / property proof
**Objective.** Implement working memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00219 — episodic memory / recover / property proof
**Objective.** Implement episodic memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00220 — semantic memory / recover / property proof
**Objective.** Implement semantic memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00221 — project memory / recover / property proof
**Objective.** Implement project memory so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00222 — hybrid retrieval / recover / property proof
**Objective.** Implement hybrid retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00223 — code retrieval / recover / property proof
**Objective.** Implement code retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00224 — graph retrieval / recover / property proof
**Objective.** Implement graph retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00225 — temporal retrieval / recover / property proof
**Objective.** Implement temporal retrieval so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00226 — claim evidence graph / recover / property proof
**Objective.** Implement claim evidence graph so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00227 — contradiction handling / recover / property proof
**Objective.** Implement contradiction handling so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00228 — context compression / recover / property proof
**Objective.** Implement context compression so the recover stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00229 — context compiler / replay / property proof
**Objective.** Implement context compiler so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00230 — working memory / replay / property proof
**Objective.** Implement working memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00231 — episodic memory / replay / property proof
**Objective.** Implement episodic memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00232 — semantic memory / replay / property proof
**Objective.** Implement semantic memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00233 — project memory / replay / property proof
**Objective.** Implement project memory so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00234 — hybrid retrieval / replay / property proof
**Objective.** Implement hybrid retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00235 — code retrieval / replay / property proof
**Objective.** Implement code retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00236 — graph retrieval / replay / property proof
**Objective.** Implement graph retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00237 — temporal retrieval / replay / property proof
**Objective.** Implement temporal retrieval so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00238 — claim evidence graph / replay / property proof
**Objective.** Implement claim evidence graph so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00239 — contradiction handling / replay / property proof
**Objective.** Implement contradiction handling so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00240 — context compression / replay / property proof
**Objective.** Implement context compression so the replay stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00241 — context compiler / optimize / property proof
**Objective.** Implement context compiler so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00242 — working memory / optimize / property proof
**Objective.** Implement working memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00243 — episodic memory / optimize / property proof
**Objective.** Implement episodic memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00244 — semantic memory / optimize / property proof
**Objective.** Implement semantic memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00245 — project memory / optimize / property proof
**Objective.** Implement project memory so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00246 — hybrid retrieval / optimize / property proof
**Objective.** Implement hybrid retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00247 — code retrieval / optimize / property proof
**Objective.** Implement code retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00248 — graph retrieval / optimize / property proof
**Objective.** Implement graph retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/graph_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00249 — temporal retrieval / optimize / property proof
**Objective.** Implement temporal retrieval so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/temporal_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00250 — claim evidence graph / optimize / property proof
**Objective.** Implement claim evidence graph so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/claim_evidence_graph.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00251 — contradiction handling / optimize / property proof
**Objective.** Implement contradiction handling so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/contradiction_handling.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00252 — context compression / optimize / property proof
**Objective.** Implement context compression so the optimize stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compression.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00253 — context compiler / promote / property proof
**Objective.** Implement context compiler so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/context_compiler.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00254 — working memory / promote / property proof
**Objective.** Implement working memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/working_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00255 — episodic memory / promote / property proof
**Objective.** Implement episodic memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/episodic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00256 — semantic memory / promote / property proof
**Objective.** Implement semantic memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/semantic_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00257 — project memory / promote / property proof
**Objective.** Implement project memory so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/project_memory.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00258 — hybrid retrieval / promote / property proof
**Objective.** Implement hybrid retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/hybrid_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.

## FLGB-03-00259 — code retrieval / promote / property proof
**Objective.** Implement code retrieval so the promote stage remains bounded, deterministic at its contract boundary, cancellation-aware, and usable by both conversational LLM operations and game-building operations during cold start.

**Runtime target.** Primary target `skeleton/ai/context/code_retrieval.py`; bind through canonical OperationEnvelope/ExecutionContext semantics rather than provider-native objects. Persist durable identity, objective, scope, authority, budget, deadline, cancellation state, provenance and terminal outcome. Model output may propose work but never grants execution authority.

**Functional contract.** Inputs are schema-versioned and reject unknown privilege-bearing fields. Execution is finite and idempotent or explicitly compensating. Outputs separate result data, verification state, confidence, usage, artifacts and failure records. Reconnect/retry reuses operation identity and cannot double-commit side effects.

**Game-builder binding.** The same atom must operate on project/scene/asset/script/narrative/build objects without bypassing rights, canon, world-state or editor transaction rules. Long-form project continuity is read from governed project state, never inferred from chat text alone.

**Acceptance evidence.** Require property proof covering the normal path plus cold start; include one negative assertion proving fail-closed behavior, one replay assertion proving stable durable outcome, one cancellation assertion, and one provenance assertion binding evidence to exact code/config/model identities.

**Failure containment.** On malformed state, stale lease, dependency drift, model refusal, unavailable provider, corrupt cache, policy denial or verification failure: emit a typed terminal/waiting state; preserve recoverable artifacts; do not silently downgrade safety, consistency or authority.

**Metrics.** Record success rate, verified-success rate, p50/p95/p99 latency, token/compute usage, retry count, rollback count, recovery time and unresolved-gap count. Performance gains are invalid if they regress correctness, authorization, reproducibility, rights or recovery.

**Promotion rule.** Planned specification only. Promotion requires implementation evidence and separate independent verification at exact head; documentation presence is never completion evidence.
