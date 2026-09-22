# AI File-Tree Migration Build Packet

Status: **staged mirror / cutover not authorized**

Authority: `machine/ai_file_tree.json`
Canonical destination: `skeleton/ai`
Baseline: `6834ce802d1492ca1dcfa388b93c24db013419c1`

## Objective and non-goals

Consolidate build-plan-relevant AI implementation already present on `main`,
plus Jeeves, into one governed assembly tree without breaking the application
or losing provenance. This packet does not change provider behavior, move
backend/frontend ownership, delete compatibility sources, claim AIQ/work-package
completion, or expand the breadth-frozen architecture.

## Requirement and volume references

The migration follows the canonical master plan, master build sequence,
architecture strangler rule, signed-accountability contract, and existing
Jeeves domain material. It deepens existing volumes rather than creating a new
parallel architecture.

## Work-package and AIQ references

Per-source work-package and AIQ references are recorded in
`machine/ai_file_tree.json`. Relocation does not change their lifecycle state.

## Canonical contracts and state owners

`machine/architecture.json` remains architectural authority. Provider
credentials, durable state, operation identity, context, retrieval, memory,
tools, and verification retain their existing owners while paths are mirrored.
The destination is an assembly tree, not a second divergent runtime owner.

## Exact implementation paths

Canonical destinations are:
- `skeleton/ai/providers/{contract.py,runtime.py}`
- `skeleton/ai/runtime/{contracts,persistence,context,retrieval,memory,intelligence,frontier,skills}`
- `skeleton/ai/agents/jeeves`
- `skeleton/ai/build/shift_supervisor`

The machine manifest records every exact source, destination, source Git object identity, work-package reference, and AIQ reference.

### Second plan-owned batch

The plan-derived expansion also maps the engine API, governance vault, core agents, repository automation, artifact plane, observability, extended contexts, security, evaluation, kernel, reliability, controlled learning, resilience, cognition, primitives, and repository intelligence into governed `skeleton/ai` destinations. Product shell, tests, installer/deployment support, and accelerator roots remain outside this tree because their ownership is separate in the architecture contract.

## Authority, security, and privacy notes

Provider credentials remain behind the canonical provider runtime. Relocation
does not widen authority, add egress, change data classification, or grant
Jeeves/tool code direct provider credentials. Backend and frontend adapters
remain application compatibility surfaces.

## Migration and compatibility

The sequence is **strangler mirror -> import inversion -> compatibility facade -> source removal**. Mirrored Python implementation remains AST-equivalent while non-Python content stays byte-identical. Credential-bearing surfaces are the explicit exception: the destination must be a pure re-export facade so provider credentials, SDK imports, and network ownership remain singular at the canonical source until cutover. Any undeclared drift fails closed.

## Failure, recovery, and rollback

Before cutover, rollback removes the destination mirror and manifest/CI wiring;
legacy imports remain intact. Once import inversion begins, rollback must
restore the previous import graph and pass focused validation before source
removal.

## Test and eval plan

Mandatory evidence includes `python scripts/check_ai_file_tree.py`, the
focused file-tree test, canonical local quality gates, App Assembly, and
affected domain tests before import inversion.

## Observability and cost signals

This structural stage adds no runtime request path, so model/tool/storage cost
must not change. CI duration and file-tree drift failures are the primary new
signals until runtime cutover.

## Edge-case obligations

The packet guards stale compatibility code, dual-owner drift, partial moves, missing package parents, provider-boundary widening, accidental duplicate credential owners, accidental completion claims, and rollback loss. Existing full-program edge obligations continue
through referenced work packages.

## Evidence references

Initial evidence is the payload commit containing exact Git-object mirrors plus
validator/test/CI results. Evidence uses full Git SHAs; prose is not evidence.

## Implementation signoff

Implementation signoff is recorded only after the payload commit exists and its
actual GitHub identity can be bound to that full SHA.

## Independent verification signoff

Independent verification is not self-issued. A distinct verifier must validate
the payload, parity, plan references, quality gates, and rollback semantics.
Until then, source deletion and migration-complete state are forbidden.


### Explicit planned-domain recovery

Two existing main-tree implementations were already named by the masterplan but still marked as planned/unverified:

- `VOL-019 World Models & Simulation` -> `skeleton/ai/simulation` with cognitive/planning ownership (`WP-W11`, `WP-W12`).
- `VOL-023 Forge` -> `skeleton/ai/forge` with primary Forge ownership (`WP-W27`).

Moving them into the governed tree does **not** mark either volume complete. Their existing accountability checkboxes remain open until the planned tests/evaluations and independent evidence exist.


## Planned-path closure

The migration now includes the native acceleration core from `skeleton/native`
under `skeleton/ai/runtime/native`, preserving VOL-032's ABI, fallback, memory
safety, and deterministic error-translation obligations.

`machine/ai_file_tree.json` also carries a fail-closed planned-path audit.
Application/assets, shared configuration, deployment/release, repository tests,
and shell compatibility surfaces remain outside AI engine ownership by design.
Planned engine roots that do not yet exist are recorded explicitly; if one of
those roots appears later, validation fails until it is moved into the canonical
AI tree or given an architecture-approved external owner. Existing naming
aliases such as `skeleton/evaluation` -> `skeleton/eval` and
`skeleton/runtime/resilience` -> `skeleton/resilience` are recorded rather
than treated as missing code.

### Cortex and Organism engine recovery

The next engine-owned recovery batch brings two long-lived AI/runtime domains under the governed tree without widening credential authority:

- `skeleton/cortex` -> `skeleton/ai/runtime/cortex` for owned-model cognition, routing, interchange, multimodal, and learning support.
- `skeleton/organism` -> `skeleton/ai/runtime/organism` for the engine runtime DAG, policy/health/quality, resilience, and operator-control support.

Three sensitive surfaces are intentionally **not duplicated as owners**. `cortex/interchange.py` and `cortex/gates.py` remain the legacy owners of provider-key/network discovery, while `organism/secret_manager.py` remains the encrypted credential-store owner. Their AI-tree counterparts are pure compatibility re-export facades until an explicit owner/import cutover is approved.

This remains a staged mirror. The batch does not mark model-runtime, cognition, learning, security, resilience, or observability work packages complete.


## Assigned next migration batch

The manifest now carries a plan-derived `next_move_assignments` queue. These are assignments, not completed moves. Each item remains pending until its source is mirrored or merged into the canonical owner, parity/evidence is produced, imports are inverted where applicable, and the assignment is promoted into the governed `mappings` set.

Priority 1 assignments are the structural/runtime spine:

- `skeleton/state` -> `skeleton/ai/runtime/state`
- `skeleton/network` -> `skeleton/ai/runtime/distributed/network`
- `skeleton/kv` -> `skeleton/ai/runtime/inference/kv`
- `skeleton/swarm` -> `skeleton/ai/agents/swarm`
- `skeleton/telemetry` -> `skeleton/ai/runtime/observability/telemetry`
- `skeleton/quality` -> `skeleton/ai/evaluation/quality`
- `skeleton/foundation` -> `skeleton/ai/runtime/foundation`
- `skeleton/gate_plane` -> `skeleton/ai/runtime/policy/gate_plane`
- `skeleton/build` -> `skeleton/ai/build/core`
- `skeleton/repo_machine` -> `skeleton/ai/build/repo_machine`

Priority 2 assignments deepen governed subsystems without creating new owners:

- `skeleton/hive` -> `skeleton/ai/agents/swarm/hive`
- `skeleton/integrations` -> `skeleton/ai/runtime/tools/integrations`
- `skeleton/inventory` -> `skeleton/ai/runtime/capabilities/inventory`
- `skeleton/graphs` -> `skeleton/ai/runtime/knowledge/graphs`
- `skeleton/creator` -> `skeleton/ai/forge/creator`
- split `skeleton/acquired/learning.py`, `resilient_cache.py`, and `runtime_guard.py` into learning/state/reliability owners while preserving acquired-source provenance.

Priority 3 assignments require overlap/domain comparison before cutover:

- `skeleton/pipelines` -> `skeleton/ai/forge/pipelines` with game-domain scope retained.
- `skeleton/persist` -> merge useful behavior into `skeleton/ai/runtime/persistence/legacy_persist` under the existing persistence owner rather than establishing another state authority.

The validator fails if required assignments disappear, point outside `skeleton/ai`, duplicate an occupied destination, lose work-package ownership, reference malformed volume IDs, or lose their migration preconditions. Assignment does not satisfy implementation, verification, maturity, or signed-accountability requirements.


## Masterplan assignment expansion — runtime, build, research, simulation

This pass binds the pending move queue to Git object identities from
`2291e57f40c55b4aa705faa64a5e5c1ae34e437a` and expands assignment coverage without claiming implementation
completion.

New priority-1 engine/build assignments include:

- `skeleton/application` -> `skeleton/ai/runtime/application`
- `skeleton/core` -> `skeleton/ai/runtime/core`
- `skeleton/data` -> `skeleton/ai/runtime/data`
- `skeleton/genesis.py` -> `skeleton/ai/runtime/bootstrap/genesis.py`
- `skeleton/galaxy`, `skeleton/mesh`, and `skeleton/overseer` -> governed distributed-runtime subtrees
- `skeleton/kv_cache.py` -> `skeleton/ai/runtime/inference/kv_cache.py`
- `skeleton/chronicle` -> `skeleton/ai/runtime/provenance/chronicle`
- `skeleton/developer` and `skeleton/pr_automation` -> governed AI build/repository-engineering subtrees.

Priority-2 assignments converge support, learning, research intake, simulation,
and optional JVM runtime support:

- `skeleton/support` -> runtime support
- `skeleton/school` -> controlled learning
- `skeleton/social` -> research intake
- `skeleton/content`, `skeleton/game`, `skeleton/economy`, `skeleton/platform`, and `skeleton/world` -> simulation/world-model ownership
- `skeleton/jvm_accelerators.py` -> the AI runtime native/JVM registry while the separate `java-accelerators/` architecture root remains external.

Priority-3 historical/model-internals code is assigned with
`quarantine_then_characterize`, not production cutover:

- `skeleton/viscera` -> model-internals research
- `skeleton/spine`, `skeleton/sheaf`, `skeleton/motive`, `skeleton/circulation`, and `skeleton/hoag` -> historical research lineage.

Every pending assignment now records `source_git_object_sha`. If the source
tree/blob changes before migration, the assignment must be refreshed rather
than silently treating a different object as the reviewed source.


## Explicit non-move classification

The assignment pass also closes the top-level classification gap. Architecture
authority/history, package CLI/metadata, release/deployment support, and the
mixed `skeleton/acquired` quarantine are explicitly retained outside
`skeleton/ai`.

The file-tree validator now fails if a live first-level `skeleton/*` path is
neither:

1. already governed by a migration mapping,
2. assigned to the pending move queue,
3. architecture-approved as external,
4. explicitly excluded, or
5. listed in `retained_outside_ai_tree`.

This prevents future "move everything" passes from accidentally relocating
architecture authority, package/bootstrap metadata, release infrastructure, or
uncharacterized acquired code.


### Classification audit source-of-truth correction

The top-level classification gate enumerates Git-tracked `skeleton/*` paths
with `git ls-files`, not arbitrary live directories. Earlier architecture
checks may create untracked runtime/generated directories such as
`skeleton/telemetry` or `skeleton/turn`; those are not source roots and must
not force false move classifications. Failure to enumerate the Git index is
itself fail-closed.
