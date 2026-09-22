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

The machine manifest records every exact source, destination, and source Git
object identity.

## Authority, security, and privacy notes

Provider credentials remain behind the canonical provider runtime. Relocation
does not widen authority, add egress, change data classification, or grant
Jeeves/tool code direct provider credentials. Backend and frontend adapters
remain application compatibility surfaces.

## Migration and compatibility

The sequence is **strangler mirror -> import inversion -> compatibility facade -> source removal**. Non-credential implementation remains byte-identical while mirrored. Credential-bearing surfaces are the explicit exception: the destination must be a pure re-export facade so provider credentials, SDK imports, and network ownership remain singular at the canonical source until cutover. Any undeclared drift fails closed.

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
