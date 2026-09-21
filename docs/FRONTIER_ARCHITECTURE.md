# Frontier Architecture Contract

## Layering

Dependencies point inward/downward. Core packages must not import cockpit or domain packs.

```text
apps / cockpit
       |
    services
       |
 forge / game / learning
       |
 intelligence / swarm
       |
 memory
       |
 runtime
       |
 kernel
```

## Canonical contracts

### Agent

```python
class Agent:
    name: str
    capabilities: set[str]

    async def run(self, task, context=None): ...
```

Implementations may differ internally, but callers must depend on the contract rather than vendor/model-specific classes.

### Memory

```python
class MemoryStore:
    async def put(self, item): ...
    async def search(self, query, *, limit=10, filters=None): ...
    async def delete(self, item_id): ...
```

### Event

All cross-subsystem state changes should be representable as typed domain events with correlation and causation identifiers.

### Capability

Agents, services and tools expose explicit capabilities. Capability checks happen before side effects.

### Provenance

Generated artifacts retain source, model/provider, prompt/task identity where available, timestamps, and validation state.

## Model/provider neutrality

The frontier build must not hard-code one model provider into the kernel. Provider adapters belong below the intelligence contract. Model routing, fallback and evaluation are runtime policy.

## Data boundaries

- operational state: database adapters;
- vector state: memory adapters;
- static knowledge: versioned knowledge packs;
- large assets: LFS/artifact storage;
- secrets: runtime secret provider;
- telemetry: observability backend.

## Runtime profiles

`minimal` — kernel + runtime only.
`ai` — intelligence + memory + tools.
`game` — AI + game + simulation.
`learning` — AI + memory + tutoring.
`studio` — all application planes + cockpit.

The default developer environment should remain lightweight; optional profiles prevent the full multi-GB asset plane from becoming a prerequisite for ordinary source development.


## Adversarial cross-cutting invariants

The frontier contract inherits the hostile audit in architecture/masterplan-gap-audit.md.

These are higher-order constraints across every runtime profile:

1. Representation identity — every model binds immutable tokenizer/representation identity.
2. Artifact identity — architecture, representation, weights, adapters, quantization, runtime ABI, data/eval roots and provenance are one loadable manifest.
3. Data lineage — weight-changing training binds a reconstructable dataset/mixture lineage root.
4. State-compatible rollback — no rollback claim is valid if old code cannot safely read state written by the candidate.
5. Evaluation firewall — blind promotion evidence is isolated from training and repeated adaptive optimization.
6. Principal identity — meaningful actions bind authenticated principal, tenant, delegation, policy and expiry.
7. Containment — authorization is necessary but insufficient; high-risk execution is sandboxed.
8. Supply-chain integrity — privileged artifacts are digest/provenance verified and subject to revocation/quarantine.
9. Declared storage semantics — authoritative stores expose consistency, transaction, corruption and restore guarantees.
10. Stale-writer rejection — distributed mutations use lease/fencing/ordering semantics.
11. Secret containment — raw secrets are not ordinary prompt, log, trace, config or artifact content.
12. Verified recovery — backups/checkpoints count only after restore verification.
13. Control-plane reserve — ordinary workload cannot starve revoke, rollback, kill or recovery authority.
14. Immutable config identity — consequential evidence binds exact runtime/policy configuration.
15. Unknown-outcome safety — non-idempotent side effects are reconciled/compensated rather than blindly retried.
16. Deletion propagation — deletion reaches derived indexes, caches, memory and future training inputs where policy requires.
17. Poisoning resistance — training/retrieval/synthetic inputs remain untrusted until validated.
18. Safe loading — untrusted artifacts are resource bounded and cannot implicitly execute code.
19. Tamper-evident authority history — meaningful mutations carry ordered actor/causation/integrity evidence.
20. Safe mode — production has one known degraded/read-only state for containment and recovery.

A lower-level implementation or historical architecture round cannot waive these invariants.

## Durable contract primitives

The frontier architecture reserves the following canonical primitive families:

RepresentationSpec
DatasetManifest / MixtureManifest / HoldoutBoundary
ModelArtifactManifest
ConfigSnapshot
Principal / DelegationChain
ToolIntent / ValidatedToolCall / ToolExecutionReceipt
LeaseEpoch / FencingToken
SchemaVersion / MigrationPlan
DeletionTombstone
AuditEvent
RecoveryManifest

Exact implementation types may evolve, but their authority boundaries may not disappear.

## Production-readiness rule

A subsystem may be experimentally useful while P0 audit gaps remain open, but it may not be described as production-grade unless all applicable P0 findings in the hostile audit are closed with tests, fault injection, observability, recovery evidence and signoff.
