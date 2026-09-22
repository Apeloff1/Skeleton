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

- **130 governed source -> destination mappings**
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

The current governed set contains **130 mappings**. The prior direct Git-object
audit covered the first **78 mappings**. The remaining **26 current mappings**
are explicitly carried in the pending refresh scope; stale references to the
removed legacy project-manifest mirror have been dropped.

The preparation ledger is now internally consistent:

- 54 mappings in `B1-core-runtime`
- 12 mappings in `B2-domain-build`
- 7 mappings in `B3-owner-sensitive`
- 22 mappings in `B3-compat-convergence`
- 35 mappings in `B4-research-quarantine`
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


## Transfer v2: legacy backend and GameForge AI recovery

Transfer v2 is rebased onto current `main` after PR #1930 merged. It adds **26 governed mappings / 89 mirrored files**, extending the governed set from 104 to 130 without changing legacy imports or granting new runtime authority.

### B4 research-quarantine recovery
- `backend/gameforge/exocortex/agentic` -> `skeleton/ai/research/legacy/gameforge/exocortex/agentic`
- `backend/gameforge/exocortex/zaibatsu` -> `skeleton/ai/research/legacy/gameforge/exocortex/zaibatsu`
- `backend/gameforge/reasoning` -> `skeleton/ai/research/legacy/gameforge/reasoning`
- `backend/gameforge/rag` -> `skeleton/ai/research/legacy/gameforge/rag`
- `backend/gameforge/math_exocortex` -> `skeleton/ai/research/legacy/gameforge/math_exocortex`
- `backend/gameforge/personal/neuro` -> `skeleton/ai/research/legacy/gameforge/personal/neuro`

These trees are research evidence and historical implementation lineage. Relocation does not promote them into production authorities.

### B3 compatibility-convergence recovery
Twenty `backend/core` Jeeves/model/memory/swarm/world modules are mirrored under `skeleton/ai/compat/backend_core`. They must converge into existing canonical owners before any legacy retirement; relocation alone cannot create provider, memory, retrieval, planning, execution, agent, or simulation authority.

### Post-#1930 parity reconciliation
After #1930 merged, current `main` changed five exact-parity files under `skeleton/automation`: `build_plane.py`, `build_repair.py`, `builder_plane.py`, `secretary.py`, and `supervisor_runtime.py`. Transfer-v2 refreshes their `skeleton/ai/build/automation` mirrors and updates the mapping source-tree identity. `specialist_bots.py` remains an intentional compatibility facade and is not mirrored over.

### Updated batch counts
- B1-core-runtime: 54
- B2-domain-build: 12
- B3-owner-sensitive: 7
- B3-compat-convergence: 22
- B4-research-quarantine: 35

Independent verification remains unsigned. Fresh full 130-mapping object/parity audit, the canonical file-tree validator, affected-domain validation, and required CI remain mandatory before any cutover or source retirement.


### Transfer-v2 implementation attestation

Implementation preparation is identity-bound to payload `fab8888ce760274984b52cbb50733f943a909581` and tree `1b44c743dfa667b7519adfb46756f9914cd36a94` by GitHub identity. This attestation does not authorize import inversion, source retirement, or production cutover. Independent verification remains unsigned.


## Transfer-v2 reconciliation closure

A fresh full-object/parity audit was completed on PR #1937 head `a3d200375e6775e95ac50add5daaca30bbabe058` after retargeting directly to `main`.

- 130/130 mapping source identities current
- zero missing source/destination objects
- zero source/destination membership drift
- zero undeclared exact-object drift
- overlay mappings checked against governed child destinations
- 16/16 declared compatibility facades contain the required re-export
- zero forbidden OpenAI credential/provider-network markers in those facades

The inherited `BASE-FRONTEND-TSC-01` blocker is closed by merged PR #1936 (`3ec4a71a53186887853a6c188bb3110701fed6d8`). Current `main` carries Expo 54 with React 19.1.0, React DOM 19.1.0, React Native 0.81.6, and matching React types. This closes the historical frontend dependency mismatch only; it does not substitute for fresh App Assembly/CI on transfer-v2.

Remaining transfer-v2 gates are canonical CI/App Assembly and affected-domain validation on the PR head, independent verification signoff, and explicit owner convergence before any compatibility-source retirement.


## Transfer-v2 frontend blocker transition

`BASE-FRONTEND-TSC-01` is retained as resolved historical evidence. PR #1936 merged the Expo 54 React/React Native alignment, and App Assembly run `35743872291` / job `106800300393` shows `yarn tsc --noEmit` completing successfully. The operation-stream reducer suite also passes 10/10.

The active inherited frontend gate is `BASE-FRONTEND-SSR-RAF-01`. The same App Assembly run advances into `expo export --platform web` and then fails during Node-side static rendering with `ReferenceError: requestAnimationFrame is not defined`, originating from `react-native-worklets/lib/module/threads.js` under Node v24.20.0.

Transfer-v2 changes no `frontend/*` files. The SSR/export failure is therefore tracked as downstream base-state debt rather than transfer-v2 object/parity drift. The full 130-mapping object/parity audit remains green, but App Assembly must be green before source retirement, `cutover_complete`, or independent completion signoff.


## Pull-request head synchronization

The transfer-v2 branch has been reconciled directly onto `main`, completed its 130-mapping object/parity audit, and recorded the inherited Expo SSR export blocker. This checkpoint is intentionally documentation-only and exists to force a standard GitHub pull-request `synchronize` event from the current branch tip so App Assembly, CI/CD, Backend Quality, Frontier Contracts, and Merge Readiness evaluate the exact live transfer head.


## Quarantine hygiene normalization

Repository Hygiene exposed trailing whitespace inherited from 11 legacy GameForge Python sources after they were mirrored into the research-quarantine tree. The destination mirrors were normalized by stripping trailing spaces only; legacy sources were not modified. Python migration parity remains valid because the canonical file-tree validator accepts AST-equivalent Python content. These normalized research mirrors are therefore semantic-parity mirrors, not byte/object-identical mirrors.

## Static-render RAF repair

The inherited `BASE-FRONTEND-SSR-RAF-01` failure was reproduced from App Assembly run `35743872291`: TypeScript and the operation-stream reducer suite passed, then `expo export --platform web` failed in Node v24 while `react-native-worklets` called an undefined `requestAnimationFrame`.

The validated transfer branch adds a supported Expo Router custom entry point that installs `requestAnimationFrame` / `cancelAnimationFrame` fallbacks only when missing and then loads `expo-router/entry`. `frontend/package.json` now points `main` at that entry. This is a repair-applied/pending-validation state until a fresh App Assembly run proves static export succeeds.
