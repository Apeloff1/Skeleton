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
