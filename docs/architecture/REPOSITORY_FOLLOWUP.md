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

## Remaining validation scope

An exploratory canonical run on the initial repair snapshot produced 16,164
passes, 331 failures and 91 skips. The combined final regression
matrix passes 738 tests across 49 files, including repair receipts, generated
projects, checkpoint binding and compiler rollback. This does not establish
that the complete exploratory suite is clean. Earlier focused counts overlap
this matrix and must not be added to it.

Remaining failures include older consumer fixtures and deeper runtime contracts.
POSIX filesystem, executable-mode and transaction tests require Linux; Windows
must continue to reject operations when its platform cannot supply the required
security primitives. Merge Readiness runs the Linux boundary tests explicitly.
No remaining failure is hidden by adding quarantine entries or weakening guards.

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
