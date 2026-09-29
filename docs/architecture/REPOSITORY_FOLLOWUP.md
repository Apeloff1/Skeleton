# Repository integration follow-up

This continues the combined tree migration in `REPOSITORY_INTEGRATION.md`.
Canonical capability owners and provider boundaries are unchanged.

## Completed repairs

- `skeleton/distributed/network/replication.py` now owns sessions, ordering,
  history, and rollback. `_replication_protocol.py` owns packet types, canonical
  serialization, checksums, and validation. Existing public imports remain
  available from both canonical and compatibility namespaces. Frozen packet
  checksums captured before extraction verify that wire behavior is unchanged.
- `skeleton/organism/paths.py` supplies the missing state, Galaxy, KV, ledger,
  and helix paths required by existing persistence consumers. Helpers resolve
  beneath the existing organism directory and perform no writes themselves.
  The default is `.skeleton/organism/`; an explicit root uses `<root>/organism/`.
- `MeshHandoffAdapter` connects existing agent routing to existing handoff
  envelopes. It selects a healthy capable agent before creating an envelope,
  preventing orphan tasks when no agent can serve the request. The registry
  retains state-transition and event ownership. The adapter executes no task.
- Galaxy HTTP handlers are bound per transport instance. Previously, starting
  another node overwrote the shared handler's transport, breaking remote task
  replies. Repeated start is idempotent, and stop closes the listening socket.
- Source and governed AI mirrors remain synchronized. Merge Readiness now
  exercises replication, path recovery, handoff, and Galaxy bridge contracts.

## Expanded integration repairs

The previously listed command-deck, organism diagnostic, Vault, guarded
compaction, social-label and resource-budget mismatches have been repaired and
covered by focused regression tests. Deck commands now use existing capability
owners; diagnostic reads do not dispatch repairs. Context and compaction paths
respect whole-record budgets and retained constraints. Graph persistence retains
confidence and provenance and validates a full restore before mutating state.

Vault now uses authenticated AES-256-GCM envelopes with context-bound associated
data and atomic rotation. Native cryptography is loaded only when cryptographic
operations run; lightweight tooling imports remain usable without that optional
runtime being imported. The installation dependency remains declared. Old XOR
envelopes are rejected, not silently migrated. Retained master keys are in-memory
only: this component is not a durable external key-management service.

Builder follow-up repairs now carry a bounded immutable receipt binding the
existing proposal, PR head, PR number, accepted review and admitted follow-up.
Both worker parsing and manifest admission validate that evidence. This adds no
execution or merge authority. Missing, tampered, over-budget or mismatched repair
evidence fails closed. Repository context explicitly decodes UTF-8 and truncates
content on a byte budget without splitting a character.

Developer starters now construct a real Forge blueprint, create the canonical
API application and invoke an actual local server, and deliver swarm messages to
explicit receivers. Template listing consumes the existing metadata mapping.
Forced generation preflights non-regular file targets before overwriting anything.
Generated-project regressions execute all four templates in isolated processes;
the API test constructs the app and intercepts server startup without opening a
listener. Checkpoint and compiler test fixtures use explicit run identity and
replay declarations so their tamper, rollback and effect checks execute again.

Operator controls delegate threshold and repair changes to the existing policy
owner. Product cards expose actual quality and repair history from the selected
root; independent decks cannot borrow each other's history. Context/support
exports retain canonical type identity. Connector spelling repair is deterministic,
stays within its service namespace and leaves ties or unknown services unresolved.

Supervisor envelope unit tests now isolate repository discovery, with separate
coverage exercising the real model on a bounded repository fixture. An unavailable
provider is rejected before building an unused model prompt. Full repository
validation remains in the repository-model and architecture checks.

## Runtime and test integration completion batch

NPC validation accepts the actual serialized node/behavior identifiers and rejects
malformed non-string identifiers. NPC, dialogue and game-logic verifiers load the
selected project's policy root. Invalid repair proposals remain proposals: tests
no longer require repair code to invent missing content or bypass verification.

Galaxy proposers apply their local approval policy to their own proposals, just
as receiving nodes do. Terminal proposals ignore later votes, and resolution is
not counted twice. Majority requirements are unchanged.

The API mounts the shared command router directly. GameForge's canonical guarded
handlers remain the sole mounted owners of intake/run; the redundant legacy
wrapper no longer changes the generated API schema. A regression rejects duplicate
operation identifiers while checking that both GameForge and command routes exist.

Canonical pytest discovery explicitly includes the backend import root. Async
contracts in the isolated CI job explicitly load their installed runner plugin.
Migration tests validate current staged-tree identities instead of frozen hashes
from the original migrations. Deck tests isolate provenance storage from tracked
reference data. Swarm recovery fixtures now establish actual leases and bindings;
OpenAPI route checks also work with deferred FastAPI router inclusion.

Research lifecycle fixtures use explicit provider identity and bounded bridge
populations where the contract concerns a single bridge. Ranking tests remain
separate; promotion, calibration, privacy budgets and evidence gates are unchanged.
The architecture index records all 24 documented research domains without claiming
local reproduction or granting production authority.

## Historical diagnostic scope

The counts and unresolved categories in this section describe earlier repair
snapshots, not the final integration state. See the completion evidence below
and PR #2238's revision-specific checks for current validation.

The initial exploratory canonical run produced 16,164 passes, 331 failures and
91 skips. A later full diagnostic against the e9e3c12 source snapshot produced
16,324 passes, 214 failures, 86 skips and one collection error. Subsequent repairs
fix the backend collection error and multiple pipeline, swarm, research and
numeric fixtures; the complete exploratory suite has not been rerun on the final
repair snapshot and is not claimed clean.

The latest integration matrix passed 2,434 tests across 155 files spanning the
affected runtimes, repository contracts, automation and API boundaries. Its log
and machine-readable results accompany the delivery evidence. Six existing platform skips and four explicitly
deselected POSIX mutation/publication tests apply to the Windows run. Linux CI
retains every one of those tests and separately exercises rooted filesystem and
transaction boundaries. No quarantine entries or weaker production guards were
introduced to hide failures. Earlier focused counts overlap this matrix.

Remaining diagnostic failures include stale CLI/route inventory expectations,
consumer fixtures for evolved scientific/semantic contracts, deeper engine and
forecasting behavior, and platform-dependent filesystem/shell cases. The repository
organization audit also retains advisory findings and a broad dependency cycle;
passing targeted checks is not a claim that these architectural debts are retired.

## Completion evidence

The expanded integration matrix subsequently passed 2,989 tests across 196 files
(20 skips and four documented Windows exclusions). Main reconciliation passed
141 focused tests; the migration-source path correction passed 11. Packaging and
developer-command repairs passed 87 tests. A clean wheel verified 563 changed
Python files against its source tree, and its installed commands and four
generated starter projects passed 22 smoke checks.

The broad Windows diagnostic reached 16,473 passes, 95 skips and 79 explicit
platform exclusions, with one stale packaging assertion. The legacy metadata
and assertion were corrected and covered by the packaging matrix. This earlier
diagnostic is not a passing final-revision full-suite result.

Hosted validation at `07c8ae7` passed 2,084 automation tests, 308 Linux filesystem
and transaction tests, 45 isolated supervisor contracts, 3,131 backend tests,
application assembly, live Mongo integration and ARM64 builds. Its combined
quality gate identified a dynamic import in the entrypoint regression test.
That test now asserts the declared entrypoint and imports it explicitly;
the repository's dynamic-import restriction remains unchanged. Final acceptance
requires successful hosted checks on the PR's current head, including the full
canonical domain suite and combined quality gate. The full Linux diagnostic at
that revision passed 16,622 tests and exposed two integration issues: reference
tests wrote into tracked provenance, and the focused test environment lacked
PyYAML. Reference-writing legacy tests now use temporary logs while asserting
that provenance is recorded and the corpus is unchanged. PyYAML is declared for
development and the focused CI runtime. CI also verifies that the legacy runner
leaves tracked source unchanged before starting the domain suite.

The repository inventory contains 26,081 files in 65 zones with no unclassified
files or truncation. All 160 governed source/mirror mappings pass validation.
The static index retains 179 oversized-module findings, one broad runtime
dependency cycle and four zones without direct static test-import evidence.
Those are maintenance findings, not executed coverage or omitted acceptance
failures. Future capability roots remain planned until implemented and accepted.

## Verification and rollback

Run the mandatory architecture/construction/capability/provider validators and
AI-tree parity, then the focused tests listed in Merge Readiness. The replication
suite covers malformed packets, bounded buffers, acknowledgements, atomic failure,
prediction reconciliation, and rollback. Bridge tests use local loopback nodes.

Revert each canonical change with its governed mirrors and manifest identities.
The replication extraction preserves packet schemas. Vault envelope changes
require preserving access to the applicable master keys; do not roll back readers
without accounting for data written in the authenticated format. Reverting the path helpers restores the prior
missing-import failure and should not delete any subsequently persisted files.
