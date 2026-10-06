# FLGB-10 — Scene ECS Physics and Simulation

Canonical overlay: Functional LLM + Game Builder 10MB execution atlas
Masterplan relationship: depth-only; VOL-000..420 breadth freeze preserved
Implementation authority: none
Implementation signed: false
Independent verification signed: false

## Plane objective
Specify a complete implementation/evidence surface for Scene ECS Physics and Simulation. Requirements are shared by the conversational LLM plane and the AI game-builder plane wherever the capability crosses project boundaries.

## FLGB-10-00001 — entity component storage / contract / unit proof
**Objective.** Make entity component storage production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00002 — transform hierarchy / contract / unit proof
**Objective.** Make transform hierarchy production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00003 — fixed timestep / contract / unit proof
**Objective.** Make fixed timestep production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00004 — collision broadphase / contract / unit proof
**Objective.** Make collision broadphase production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00005 — collision narrowphase / contract / unit proof
**Objective.** Make collision narrowphase production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00006 — rigid body / contract / unit proof
**Objective.** Make rigid body production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00007 — character controller / contract / unit proof
**Objective.** Make character controller production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00008 — constraints / contract / unit proof
**Objective.** Make constraints production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00009 — deterministic simulation / contract / unit proof
**Objective.** Make deterministic simulation production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00010 — physics query / contract / unit proof
**Objective.** Make physics query production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00011 — simulation snapshot / contract / unit proof
**Objective.** Make simulation snapshot production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00012 — rollback simulation / contract / unit proof
**Objective.** Make rollback simulation production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00013 — entity component storage / admission / unit proof
**Objective.** Make entity component storage production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00014 — transform hierarchy / admission / unit proof
**Objective.** Make transform hierarchy production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00015 — fixed timestep / admission / unit proof
**Objective.** Make fixed timestep production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00016 — collision broadphase / admission / unit proof
**Objective.** Make collision broadphase production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00017 — collision narrowphase / admission / unit proof
**Objective.** Make collision narrowphase production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00018 — rigid body / admission / unit proof
**Objective.** Make rigid body production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00019 — character controller / admission / unit proof
**Objective.** Make character controller production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00020 — constraints / admission / unit proof
**Objective.** Make constraints production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00021 — deterministic simulation / admission / unit proof
**Objective.** Make deterministic simulation production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00022 — physics query / admission / unit proof
**Objective.** Make physics query production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00023 — simulation snapshot / admission / unit proof
**Objective.** Make simulation snapshot production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00024 — rollback simulation / admission / unit proof
**Objective.** Make rollback simulation production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00025 — entity component storage / compile / unit proof
**Objective.** Make entity component storage production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00026 — transform hierarchy / compile / unit proof
**Objective.** Make transform hierarchy production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00027 — fixed timestep / compile / unit proof
**Objective.** Make fixed timestep production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00028 — collision broadphase / compile / unit proof
**Objective.** Make collision broadphase production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00029 — collision narrowphase / compile / unit proof
**Objective.** Make collision narrowphase production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00030 — rigid body / compile / unit proof
**Objective.** Make rigid body production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00031 — character controller / compile / unit proof
**Objective.** Make character controller production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00032 — constraints / compile / unit proof
**Objective.** Make constraints production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00033 — deterministic simulation / compile / unit proof
**Objective.** Make deterministic simulation production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00034 — physics query / compile / unit proof
**Objective.** Make physics query production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00035 — simulation snapshot / compile / unit proof
**Objective.** Make simulation snapshot production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00036 — rollback simulation / compile / unit proof
**Objective.** Make rollback simulation production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00037 — entity component storage / execute / unit proof
**Objective.** Make entity component storage production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00038 — transform hierarchy / execute / unit proof
**Objective.** Make transform hierarchy production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00039 — fixed timestep / execute / unit proof
**Objective.** Make fixed timestep production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00040 — collision broadphase / execute / unit proof
**Objective.** Make collision broadphase production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00041 — collision narrowphase / execute / unit proof
**Objective.** Make collision narrowphase production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00042 — rigid body / execute / unit proof
**Objective.** Make rigid body production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00043 — character controller / execute / unit proof
**Objective.** Make character controller production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00044 — constraints / execute / unit proof
**Objective.** Make constraints production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00045 — deterministic simulation / execute / unit proof
**Objective.** Make deterministic simulation production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00046 — physics query / execute / unit proof
**Objective.** Make physics query production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00047 — simulation snapshot / execute / unit proof
**Objective.** Make simulation snapshot production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00048 — rollback simulation / execute / unit proof
**Objective.** Make rollback simulation production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00049 — entity component storage / observe / unit proof
**Objective.** Make entity component storage production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00050 — transform hierarchy / observe / unit proof
**Objective.** Make transform hierarchy production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00051 — fixed timestep / observe / unit proof
**Objective.** Make fixed timestep production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00052 — collision broadphase / observe / unit proof
**Objective.** Make collision broadphase production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00053 — collision narrowphase / observe / unit proof
**Objective.** Make collision narrowphase production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00054 — rigid body / observe / unit proof
**Objective.** Make rigid body production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00055 — character controller / observe / unit proof
**Objective.** Make character controller production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00056 — constraints / observe / unit proof
**Objective.** Make constraints production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00057 — deterministic simulation / observe / unit proof
**Objective.** Make deterministic simulation production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00058 — physics query / observe / unit proof
**Objective.** Make physics query production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00059 — simulation snapshot / observe / unit proof
**Objective.** Make simulation snapshot production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00060 — rollback simulation / observe / unit proof
**Objective.** Make rollback simulation production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00061 — entity component storage / verify / unit proof
**Objective.** Make entity component storage production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00062 — transform hierarchy / verify / unit proof
**Objective.** Make transform hierarchy production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00063 — fixed timestep / verify / unit proof
**Objective.** Make fixed timestep production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00064 — collision broadphase / verify / unit proof
**Objective.** Make collision broadphase production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00065 — collision narrowphase / verify / unit proof
**Objective.** Make collision narrowphase production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00066 — rigid body / verify / unit proof
**Objective.** Make rigid body production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00067 — character controller / verify / unit proof
**Objective.** Make character controller production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00068 — constraints / verify / unit proof
**Objective.** Make constraints production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00069 — deterministic simulation / verify / unit proof
**Objective.** Make deterministic simulation production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00070 — physics query / verify / unit proof
**Objective.** Make physics query production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00071 — simulation snapshot / verify / unit proof
**Objective.** Make simulation snapshot production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00072 — rollback simulation / verify / unit proof
**Objective.** Make rollback simulation production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00073 — entity component storage / recover / unit proof
**Objective.** Make entity component storage production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00074 — transform hierarchy / recover / unit proof
**Objective.** Make transform hierarchy production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00075 — fixed timestep / recover / unit proof
**Objective.** Make fixed timestep production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00076 — collision broadphase / recover / unit proof
**Objective.** Make collision broadphase production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00077 — collision narrowphase / recover / unit proof
**Objective.** Make collision narrowphase production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00078 — rigid body / recover / unit proof
**Objective.** Make rigid body production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00079 — character controller / recover / unit proof
**Objective.** Make character controller production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00080 — constraints / recover / unit proof
**Objective.** Make constraints production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00081 — deterministic simulation / recover / unit proof
**Objective.** Make deterministic simulation production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00082 — physics query / recover / unit proof
**Objective.** Make physics query production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00083 — simulation snapshot / recover / unit proof
**Objective.** Make simulation snapshot production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00084 — rollback simulation / recover / unit proof
**Objective.** Make rollback simulation production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00085 — entity component storage / replay / unit proof
**Objective.** Make entity component storage production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00086 — transform hierarchy / replay / unit proof
**Objective.** Make transform hierarchy production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00087 — fixed timestep / replay / unit proof
**Objective.** Make fixed timestep production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00088 — collision broadphase / replay / unit proof
**Objective.** Make collision broadphase production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00089 — collision narrowphase / replay / unit proof
**Objective.** Make collision narrowphase production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00090 — rigid body / replay / unit proof
**Objective.** Make rigid body production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00091 — character controller / replay / unit proof
**Objective.** Make character controller production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00092 — constraints / replay / unit proof
**Objective.** Make constraints production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00093 — deterministic simulation / replay / unit proof
**Objective.** Make deterministic simulation production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00094 — physics query / replay / unit proof
**Objective.** Make physics query production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00095 — simulation snapshot / replay / unit proof
**Objective.** Make simulation snapshot production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00096 — rollback simulation / replay / unit proof
**Objective.** Make rollback simulation production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00097 — entity component storage / optimize / unit proof
**Objective.** Make entity component storage production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00098 — transform hierarchy / optimize / unit proof
**Objective.** Make transform hierarchy production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00099 — fixed timestep / optimize / unit proof
**Objective.** Make fixed timestep production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00100 — collision broadphase / optimize / unit proof
**Objective.** Make collision broadphase production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00101 — collision narrowphase / optimize / unit proof
**Objective.** Make collision narrowphase production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00102 — rigid body / optimize / unit proof
**Objective.** Make rigid body production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00103 — character controller / optimize / unit proof
**Objective.** Make character controller production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00104 — constraints / optimize / unit proof
**Objective.** Make constraints production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00105 — deterministic simulation / optimize / unit proof
**Objective.** Make deterministic simulation production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00106 — physics query / optimize / unit proof
**Objective.** Make physics query production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00107 — simulation snapshot / optimize / unit proof
**Objective.** Make simulation snapshot production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00108 — rollback simulation / optimize / unit proof
**Objective.** Make rollback simulation production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00109 — entity component storage / promote / unit proof
**Objective.** Make entity component storage production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00110 — transform hierarchy / promote / unit proof
**Objective.** Make transform hierarchy production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00111 — fixed timestep / promote / unit proof
**Objective.** Make fixed timestep production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00112 — collision broadphase / promote / unit proof
**Objective.** Make collision broadphase production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00113 — collision narrowphase / promote / unit proof
**Objective.** Make collision narrowphase production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00114 — rigid body / promote / unit proof
**Objective.** Make rigid body production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00115 — character controller / promote / unit proof
**Objective.** Make character controller production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00116 — constraints / promote / unit proof
**Objective.** Make constraints production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00117 — deterministic simulation / promote / unit proof
**Objective.** Make deterministic simulation production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00118 — physics query / promote / unit proof
**Objective.** Make physics query production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00119 — simulation snapshot / promote / unit proof
**Objective.** Make simulation snapshot production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00120 — rollback simulation / promote / unit proof
**Objective.** Make rollback simulation production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00121 — entity component storage / rollback / unit proof
**Objective.** Make entity component storage production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00122 — transform hierarchy / rollback / unit proof
**Objective.** Make transform hierarchy production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00123 — fixed timestep / rollback / unit proof
**Objective.** Make fixed timestep production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00124 — collision broadphase / rollback / unit proof
**Objective.** Make collision broadphase production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00125 — collision narrowphase / rollback / unit proof
**Objective.** Make collision narrowphase production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00126 — rigid body / rollback / unit proof
**Objective.** Make rigid body production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00127 — character controller / rollback / unit proof
**Objective.** Make character controller production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00128 — constraints / rollback / unit proof
**Objective.** Make constraints production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00129 — deterministic simulation / rollback / unit proof
**Objective.** Make deterministic simulation production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00130 — physics query / rollback / unit proof
**Objective.** Make physics query production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00131 — simulation snapshot / rollback / unit proof
**Objective.** Make simulation snapshot production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00132 — rollback simulation / rollback / unit proof
**Objective.** Make rollback simulation production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00133 — entity component storage / retire / unit proof
**Objective.** Make entity component storage production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00134 — transform hierarchy / retire / unit proof
**Objective.** Make transform hierarchy production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00135 — fixed timestep / retire / unit proof
**Objective.** Make fixed timestep production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00136 — collision broadphase / retire / unit proof
**Objective.** Make collision broadphase production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00137 — collision narrowphase / retire / unit proof
**Objective.** Make collision narrowphase production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00138 — rigid body / retire / unit proof
**Objective.** Make rigid body production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00139 — character controller / retire / unit proof
**Objective.** Make character controller production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00140 — constraints / retire / unit proof
**Objective.** Make constraints production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00141 — deterministic simulation / retire / unit proof
**Objective.** Make deterministic simulation production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00142 — physics query / retire / unit proof
**Objective.** Make physics query production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00143 — simulation snapshot / retire / unit proof
**Objective.** Make simulation snapshot production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00144 — rollback simulation / retire / unit proof
**Objective.** Make rollback simulation production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** unit proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00145 — entity component storage / contract / property proof
**Objective.** Make entity component storage production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00146 — transform hierarchy / contract / property proof
**Objective.** Make transform hierarchy production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00147 — fixed timestep / contract / property proof
**Objective.** Make fixed timestep production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00148 — collision broadphase / contract / property proof
**Objective.** Make collision broadphase production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00149 — collision narrowphase / contract / property proof
**Objective.** Make collision narrowphase production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00150 — rigid body / contract / property proof
**Objective.** Make rigid body production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00151 — character controller / contract / property proof
**Objective.** Make character controller production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00152 — constraints / contract / property proof
**Objective.** Make constraints production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00153 — deterministic simulation / contract / property proof
**Objective.** Make deterministic simulation production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00154 — physics query / contract / property proof
**Objective.** Make physics query production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00155 — simulation snapshot / contract / property proof
**Objective.** Make simulation snapshot production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00156 — rollback simulation / contract / property proof
**Objective.** Make rollback simulation production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00157 — entity component storage / admission / property proof
**Objective.** Make entity component storage production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00158 — transform hierarchy / admission / property proof
**Objective.** Make transform hierarchy production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00159 — fixed timestep / admission / property proof
**Objective.** Make fixed timestep production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00160 — collision broadphase / admission / property proof
**Objective.** Make collision broadphase production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00161 — collision narrowphase / admission / property proof
**Objective.** Make collision narrowphase production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00162 — rigid body / admission / property proof
**Objective.** Make rigid body production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00163 — character controller / admission / property proof
**Objective.** Make character controller production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00164 — constraints / admission / property proof
**Objective.** Make constraints production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00165 — deterministic simulation / admission / property proof
**Objective.** Make deterministic simulation production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00166 — physics query / admission / property proof
**Objective.** Make physics query production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00167 — simulation snapshot / admission / property proof
**Objective.** Make simulation snapshot production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00168 — rollback simulation / admission / property proof
**Objective.** Make rollback simulation production-functional through admission under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00169 — entity component storage / compile / property proof
**Objective.** Make entity component storage production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00170 — transform hierarchy / compile / property proof
**Objective.** Make transform hierarchy production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00171 — fixed timestep / compile / property proof
**Objective.** Make fixed timestep production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00172 — collision broadphase / compile / property proof
**Objective.** Make collision broadphase production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00173 — collision narrowphase / compile / property proof
**Objective.** Make collision narrowphase production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00174 — rigid body / compile / property proof
**Objective.** Make rigid body production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00175 — character controller / compile / property proof
**Objective.** Make character controller production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00176 — constraints / compile / property proof
**Objective.** Make constraints production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00177 — deterministic simulation / compile / property proof
**Objective.** Make deterministic simulation production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00178 — physics query / compile / property proof
**Objective.** Make physics query production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00179 — simulation snapshot / compile / property proof
**Objective.** Make simulation snapshot production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00180 — rollback simulation / compile / property proof
**Objective.** Make rollback simulation production-functional through compile under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00181 — entity component storage / execute / property proof
**Objective.** Make entity component storage production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00182 — transform hierarchy / execute / property proof
**Objective.** Make transform hierarchy production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00183 — fixed timestep / execute / property proof
**Objective.** Make fixed timestep production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00184 — collision broadphase / execute / property proof
**Objective.** Make collision broadphase production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00185 — collision narrowphase / execute / property proof
**Objective.** Make collision narrowphase production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00186 — rigid body / execute / property proof
**Objective.** Make rigid body production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00187 — character controller / execute / property proof
**Objective.** Make character controller production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00188 — constraints / execute / property proof
**Objective.** Make constraints production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00189 — deterministic simulation / execute / property proof
**Objective.** Make deterministic simulation production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00190 — physics query / execute / property proof
**Objective.** Make physics query production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00191 — simulation snapshot / execute / property proof
**Objective.** Make simulation snapshot production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00192 — rollback simulation / execute / property proof
**Objective.** Make rollback simulation production-functional through execute under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00193 — entity component storage / observe / property proof
**Objective.** Make entity component storage production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00194 — transform hierarchy / observe / property proof
**Objective.** Make transform hierarchy production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00195 — fixed timestep / observe / property proof
**Objective.** Make fixed timestep production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00196 — collision broadphase / observe / property proof
**Objective.** Make collision broadphase production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00197 — collision narrowphase / observe / property proof
**Objective.** Make collision narrowphase production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00198 — rigid body / observe / property proof
**Objective.** Make rigid body production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00199 — character controller / observe / property proof
**Objective.** Make character controller production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00200 — constraints / observe / property proof
**Objective.** Make constraints production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00201 — deterministic simulation / observe / property proof
**Objective.** Make deterministic simulation production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00202 — physics query / observe / property proof
**Objective.** Make physics query production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00203 — simulation snapshot / observe / property proof
**Objective.** Make simulation snapshot production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00204 — rollback simulation / observe / property proof
**Objective.** Make rollback simulation production-functional through observe under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00205 — entity component storage / verify / property proof
**Objective.** Make entity component storage production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00206 — transform hierarchy / verify / property proof
**Objective.** Make transform hierarchy production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00207 — fixed timestep / verify / property proof
**Objective.** Make fixed timestep production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00208 — collision broadphase / verify / property proof
**Objective.** Make collision broadphase production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00209 — collision narrowphase / verify / property proof
**Objective.** Make collision narrowphase production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00210 — rigid body / verify / property proof
**Objective.** Make rigid body production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00211 — character controller / verify / property proof
**Objective.** Make character controller production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00212 — constraints / verify / property proof
**Objective.** Make constraints production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00213 — deterministic simulation / verify / property proof
**Objective.** Make deterministic simulation production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00214 — physics query / verify / property proof
**Objective.** Make physics query production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00215 — simulation snapshot / verify / property proof
**Objective.** Make simulation snapshot production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00216 — rollback simulation / verify / property proof
**Objective.** Make rollback simulation production-functional through verify under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00217 — entity component storage / recover / property proof
**Objective.** Make entity component storage production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00218 — transform hierarchy / recover / property proof
**Objective.** Make transform hierarchy production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00219 — fixed timestep / recover / property proof
**Objective.** Make fixed timestep production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00220 — collision broadphase / recover / property proof
**Objective.** Make collision broadphase production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00221 — collision narrowphase / recover / property proof
**Objective.** Make collision narrowphase production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00222 — rigid body / recover / property proof
**Objective.** Make rigid body production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00223 — character controller / recover / property proof
**Objective.** Make character controller production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00224 — constraints / recover / property proof
**Objective.** Make constraints production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00225 — deterministic simulation / recover / property proof
**Objective.** Make deterministic simulation production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00226 — physics query / recover / property proof
**Objective.** Make physics query production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00227 — simulation snapshot / recover / property proof
**Objective.** Make simulation snapshot production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00228 — rollback simulation / recover / property proof
**Objective.** Make rollback simulation production-functional through recover under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00229 — entity component storage / replay / property proof
**Objective.** Make entity component storage production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00230 — transform hierarchy / replay / property proof
**Objective.** Make transform hierarchy production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00231 — fixed timestep / replay / property proof
**Objective.** Make fixed timestep production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00232 — collision broadphase / replay / property proof
**Objective.** Make collision broadphase production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00233 — collision narrowphase / replay / property proof
**Objective.** Make collision narrowphase production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00234 — rigid body / replay / property proof
**Objective.** Make rigid body production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00235 — character controller / replay / property proof
**Objective.** Make character controller production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00236 — constraints / replay / property proof
**Objective.** Make constraints production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00237 — deterministic simulation / replay / property proof
**Objective.** Make deterministic simulation production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00238 — physics query / replay / property proof
**Objective.** Make physics query production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00239 — simulation snapshot / replay / property proof
**Objective.** Make simulation snapshot production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00240 — rollback simulation / replay / property proof
**Objective.** Make rollback simulation production-functional through replay under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00241 — entity component storage / optimize / property proof
**Objective.** Make entity component storage production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00242 — transform hierarchy / optimize / property proof
**Objective.** Make transform hierarchy production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00243 — fixed timestep / optimize / property proof
**Objective.** Make fixed timestep production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00244 — collision broadphase / optimize / property proof
**Objective.** Make collision broadphase production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00245 — collision narrowphase / optimize / property proof
**Objective.** Make collision narrowphase production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00246 — rigid body / optimize / property proof
**Objective.** Make rigid body production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00247 — character controller / optimize / property proof
**Objective.** Make character controller production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00248 — constraints / optimize / property proof
**Objective.** Make constraints production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00249 — deterministic simulation / optimize / property proof
**Objective.** Make deterministic simulation production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00250 — physics query / optimize / property proof
**Objective.** Make physics query production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00251 — simulation snapshot / optimize / property proof
**Objective.** Make simulation snapshot production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00252 — rollback simulation / optimize / property proof
**Objective.** Make rollback simulation production-functional through optimize under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00253 — entity component storage / promote / property proof
**Objective.** Make entity component storage production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00254 — transform hierarchy / promote / property proof
**Objective.** Make transform hierarchy production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00255 — fixed timestep / promote / property proof
**Objective.** Make fixed timestep production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00256 — collision broadphase / promote / property proof
**Objective.** Make collision broadphase production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00257 — collision narrowphase / promote / property proof
**Objective.** Make collision narrowphase production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00258 — rigid body / promote / property proof
**Objective.** Make rigid body production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00259 — character controller / promote / property proof
**Objective.** Make character controller production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00260 — constraints / promote / property proof
**Objective.** Make constraints production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00261 — deterministic simulation / promote / property proof
**Objective.** Make deterministic simulation production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00262 — physics query / promote / property proof
**Objective.** Make physics query production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00263 — simulation snapshot / promote / property proof
**Objective.** Make simulation snapshot production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00264 — rollback simulation / promote / property proof
**Objective.** Make rollback simulation production-functional through promote under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00265 — entity component storage / rollback / property proof
**Objective.** Make entity component storage production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00266 — transform hierarchy / rollback / property proof
**Objective.** Make transform hierarchy production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00267 — fixed timestep / rollback / property proof
**Objective.** Make fixed timestep production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00268 — collision broadphase / rollback / property proof
**Objective.** Make collision broadphase production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00269 — collision narrowphase / rollback / property proof
**Objective.** Make collision narrowphase production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00270 — rigid body / rollback / property proof
**Objective.** Make rigid body production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00271 — character controller / rollback / property proof
**Objective.** Make character controller production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00272 — constraints / rollback / property proof
**Objective.** Make constraints production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00273 — deterministic simulation / rollback / property proof
**Objective.** Make deterministic simulation production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00274 — physics query / rollback / property proof
**Objective.** Make physics query production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00275 — simulation snapshot / rollback / property proof
**Objective.** Make simulation snapshot production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00276 — rollback simulation / rollback / property proof
**Objective.** Make rollback simulation production-functional through rollback under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00277 — entity component storage / retire / property proof
**Objective.** Make entity component storage production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00278 — transform hierarchy / retire / property proof
**Objective.** Make transform hierarchy production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00279 — fixed timestep / retire / property proof
**Objective.** Make fixed timestep production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00280 — collision broadphase / retire / property proof
**Objective.** Make collision broadphase production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00281 — collision narrowphase / retire / property proof
**Objective.** Make collision narrowphase production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_narrowphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00282 — rigid body / retire / property proof
**Objective.** Make rigid body production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rigid_body.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00283 — character controller / retire / property proof
**Objective.** Make character controller production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/character_controller.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00284 — constraints / retire / property proof
**Objective.** Make constraints production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/constraints.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00285 — deterministic simulation / retire / property proof
**Objective.** Make deterministic simulation production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/deterministic_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00286 — physics query / retire / property proof
**Objective.** Make physics query production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/physics_query.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00287 — simulation snapshot / retire / property proof
**Objective.** Make simulation snapshot production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/simulation_snapshot.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00288 — rollback simulation / retire / property proof
**Objective.** Make rollback simulation production-functional through retire under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/rollback_simulation.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** property proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00289 — entity component storage / contract / integration proof
**Objective.** Make entity component storage production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/entity_component_storage.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** integration proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00290 — transform hierarchy / contract / integration proof
**Objective.** Make transform hierarchy production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/transform_hierarchy.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** integration proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00291 — fixed timestep / contract / integration proof
**Objective.** Make fixed timestep production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/fixed_timestep.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** integration proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.

## FLGB-10-00292 — collision broadphase / contract / integration proof
**Objective.** Make collision broadphase production-functional through contract under cold start, with finite execution, explicit authority, durable state, deterministic contract semantics and recovery behavior.

**Implementation target.** `skeleton/game/simulation/collision_broadphase.py` plus its schema, migration, tests and operator evidence. Use canonical IDs and versioned records; provider/engine-native objects terminate at adapters. Reads and writes declare consistency and transaction semantics.

**LLM binding.** Preserve conversation/project identity, model/config identity, context provenance, inference usage, tool authority, verification state and terminal replay. A model proposal is never equivalent to an authorized side effect.

**Game-builder binding.** Apply the same contract to world/scene/entity/asset/script/build state. Editor-visible state, simulation-visible state and exported-build state must have explicit synchronization rules; no hidden mutation may bypass project transactions.

**Evidence.** integration proof must cover nominal behavior and cold start; assert typed failure, cancellation safety, bounded retry, replay/idempotency, exact artifact provenance and absence of silent authority escalation. Where deterministic output is impossible, deterministic envelopes and tolerances are mandatory.

**Adversarial case.** Inject stale/corrupt/incompatible input, unavailable dependency, resource exhaustion and contradictory upstream state. The system must fail closed or degrade only through an explicitly authorized compatibility policy, retaining diagnostics sufficient for reconstruction.

**Quality gate.** Track correctness, verified-success, latency, resource use, reproducibility, rollback success and unresolved dependencies. No optimization can compensate for a regression in rights, security, integrity, isolation, determinism boundaries or recovery.

**Status.** Specification atom only: implementation_signed=false; verification_signed=false. Closure requires exact-head executable evidence and an independent verifier.
