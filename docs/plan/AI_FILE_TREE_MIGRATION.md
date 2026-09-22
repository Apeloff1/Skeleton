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


## Move-preparation tagging and batch map

The former plan-derived `next_move_assignments` queue has now been promoted
into the governed mapping set. The queue is intentionally empty: an item is no
longer described as merely assigned once its reviewed source Git object has an
actual destination mirror under `skeleton/ai`.

Current preparation state:

- **104 governed source -> destination mappings**
- **1,997 changed files under `skeleton/ai`** in this migration PR
- package scaffolding remains assembly metadata rather than a separate move source
- `next_move_assignments` is empty because all previously assigned extant
  sources have been promoted into `mappings`
- **33 top-level/package/deployment/authority surfaces** are explicitly retained
  outside the AI tree instead of being silently ignored

Every governed mapping now carries three machine-enforced tags:

- `ai-tree:mapped`
- `migration:staged-mirror`
- exactly one of `cutover:parity-ready`, `cutover:owner-sensitive`, or
  `cutover:quarantine`

The cutover tag is structural migration metadata only. It does **not** claim
AIQ/work-package completion, production maturity, source deletion, import
inversion, or independent verification.

The prepared units are divided into five deterministic batches:

- **B1-core-runtime (54 mappings):** core runtime, provider-neutral surfaces,
  agents, cognition, learning, evaluation, reliability, state, and supporting
  engine capabilities.
- **B2-domain-build (12 mappings):** repository/build engineering, simulation,
  and Forge-owned domains.
- **B3-owner-sensitive (7 mappings):** mappings with compatibility facades or
  parity exceptions. Provider credentials, network ownership, or other
  authority-bearing implementation stays at the legacy owner until an explicit
  owner/import cutover is approved.
- **B4-research-quarantine (29 mappings):** historical and model-internals
  research lineage. These units remain characterization-gated and are not
  production cutover candidates.
- **B3-compat-convergence (2 mappings):** Turn and Telemetry compatibility
  mirrors that must merge into existing canonical owners rather than become
  independent production authorities.

Exact-parity sources remain in place until import inversion and affected-domain
regression gates are green. Owner-sensitive sources remain until explicit
authority-owner cutover. Quarantine sources remain until characterization and
independent evidence justify promotion.

The validator recomputes the expected cutover tag and batch from each mapping's
destination and parity/facade contract, so manual relabeling cannot silently
turn a sensitive or quarantined unit into a parity-ready one.


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


### Latest extension audit status

The current governed set contains **104 mappings**. The prior direct Git-object
audit covered the first **78 mappings**. The remaining **26 current mappings**
are explicitly carried in the pending refresh scope; stale references to the
removed legacy project-manifest mirror have been dropped.

The preparation ledger is now internally consistent:

- 54 mappings in `B1-core-runtime`
- 12 mappings in `B2-domain-build`
- 7 mappings in `B3-owner-sensitive`
- 2 mappings in `B3-compat-convergence`
- 29 mappings in `B4-research-quarantine`
- 0 pending move assignments
- 33 retained-outside classifications

Fresh full-object/parity audit and CI evidence are still required before import
inversion, source retirement, or any cutover-complete claim.


## Compatibility convergence surfaces

Legacy runtime packages that overlap a canonical owner are staged under
`skeleton/ai/compat` instead of being promoted as new authorities.

- `skeleton/turn -> skeleton/ai/compat/turn` must converge into canonical
  conversation/execution state owners.
- `skeleton/telemetry -> skeleton/ai/compat/telemetry` must converge into
  canonical observability/operation-stream owners.

These mirrors are evidence and migration inputs only. Their relocation cannot
create production authority or satisfy completion checkboxes.

## AI shell and configuration

`skeleton/config` and `skeleton/shells/ai` are plan-owned engine surfaces
and are mirrored under `skeleton/ai/runtime/config` and `skeleton/ai/shell`.
The shell migration preserves provider-boundary isolation: routing and provider
health code may consume canonical provider contracts but must not acquire
credentials or provider-SDK ownership.


## Historical architecture lineage

The legacy Python architecture registry and numbered architecture rounds
(`skeleton/architecture.py`, `architecture_index.py`, and rounds 3–22) are
mirrored under `skeleton/ai/research/historical/architecture_registry`.

These files are preserved for reverse engineering, provenance, and comparison
against later designs. They are explicitly **non-authoritative**:
`machine/architecture.json` remains the sole current architecture authority.
No historical module can become a production owner through relocation alone;
promotion requires an explicit masterplan adoption, evaluation evidence, and
the normal signed-accountability process.


## Transfer v2 clean rebuild

Transfer v2 is rebuilt directly on the hardened baseline bridge to eliminate unrelated reconciliation history.

Scope:
- 26 new governed mappings
- 89 new mirrored files
- 5 inherited `skeleton/automation` exact-parity mirrors refreshed after post-#1930 source changes
- 2 governance files updated (`machine/ai_file_tree.json`, this migration packet)
- expected PR delta: 96 files

New research-quarantine mappings:
- `backend/gameforge/exocortex/agentic`
- `backend/gameforge/exocortex/zaibatsu`
- `backend/gameforge/reasoning`
- `backend/gameforge/rag`
- `backend/gameforge/math_exocortex`
- `backend/gameforge/personal/neuro`

Twenty selected `backend/core` Jeeves/model/memory/swarm/world modules are staged under `skeleton/ai/compat/backend_core` as convergence inputs only. They do not become independent authorities by relocation.

No import inversion, source retirement, AIQ completion, work-package completion, or production-readiness claim is made by this transfer.


### Transfer v2 clean-audit evidence

Payload `83483a87f5a19d15f4158ad2b34d655c31e0f22b` (tree `b554c929c4e607847835752290f7c0114303aad0`) was audited across all 130 governed mappings before implementation attestation:
- 0 stale source Git-object identities
- 0 missing source/destination mappings
- 0 tree-membership drift
- 0 exact mirror blob drift
- 16 compatibility facades validated
- 0 forbidden provider credential/network markers in those facades

The implementation attestation is bound to the payload SHA above. Independent verification remains unsigned and final main-based CI/App Assembly must still pass.


## Durable transfer-v2B recovery

The managed `integration/ai-file-tree-transfer-v2` branch was repeatedly rebuilt by baseline automation and dropped the second-wave expansion. To preserve the work without fighting the controller, the expansion is staged on `integration/ai-file-tree-transfer-v2b-legacy-recovery` as a child of the latest transfer-v2 head.

This durable recovery adds **20 mappings / 148 exact-object mirrored files**, taking the governed set from **130 to 150 mappings**.

Fourteen legacy GameForge AI trees are quarantined under `skeleton/ai/research/legacy/gameforge`: agents, Jeeves, workflow, runtime, omega, personal diaries, personal logs, forges, knowledge, skills, navigation, bootstrap, orchestrator, and indexing.

Six backend-core modules are staged under `skeleton/ai/compat/backend_core`: `agent_ledger.py`, `agent_mesh.py`, `collection_agents.py`, `deployment_planner.py`, `director_agent.py`, and `playable_simulation.py`.

The provider-bearing `backend/core/ai_provider.py` and `backend/core/ai_provider_compat.py` remain deliberately excluded until a non-owning facade/authority-cutover design is approved.
