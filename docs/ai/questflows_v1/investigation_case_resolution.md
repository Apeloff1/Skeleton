# case resolution quest workflow

## Director placement
- Catalog key: `investigation_case_resolution`
- Mission plane: `investigation`
- Source schema: `skeleton.quest_flow.v1`
- Evidence scope: world-instance event ledger, never an account authorization token.
- Four linear execution phases: discover, prepare, execute, resolve.

## State model
The director owns an immutable `QuestState` with the current phase index, an optimistic version fence, terminal status, granted milestone set, and replay identities. Each accepted advance increments the phase by exactly one and produces one independently observable receipt. This implementation has no I/O and does not itself guarantee durable storage.

## Stage-to-evidence mapping
1. **discover_case_resolution**: require `investigation:case_resolution:discover:proof`; issue `investigation:case_resolution:stage:1` after successful validation (risk class 5).
2. **prepare_case_resolution**: require `investigation:case_resolution:prepare:proof`; issue `investigation:case_resolution:stage:2` after successful validation (risk class 6).
3. **execute_case_resolution**: require `investigation:case_resolution:execute:proof`; issue `investigation:case_resolution:stage:3` after successful validation (risk class 7).
4. **resolve_case_resolution**: require `investigation:case_resolution:resolve:proof`; issue `investigation:case_resolution:stage:4` after successful validation (risk class 8).

## Interaction sequence
1. Load durable state under the world-instance namespace.
2. Query `inspect(state)` for the pending phase and required evidence.
3. Acquire the evidence from the trusted world-event producer, not arbitrary client strings.
4. Send `decide(state, command)` with exact expected version and a unique event identity.
5. Persist the new state and receipt in one transaction before notifying observers.
6. Publish success only when durable state commit returns. Never promote rejection receipts.
7. On worker restart, replay the durable intent journal in original command order.

## Failure containment
- Duplicate identities are rejected even if the caller changes the version.
- Stale versions are rejected; the caller must fetch current state before retrying.
- Missing evidence does not increment the version or mutate grants.
- Unknown actions, event fields, malformed evidence and invalid versions are errors.
- Abandoned and completed quests cannot be reopened by this module.
- The 4,096-ID bounded in-memory ledger rejects capacity overflow; rotation requires an explicitly verified durable checkpoint.
- The `inspect` command is read-only and does not authorize gameplay progress.
- Evidence strings are format-validated but **not authenticated** here. Integrators must verify real world-event origins before invoking this module.

## Test and integration requirements
Execute `python -m pytest -q skeleton/testing/questflows_v1/test_investigation_case_resolution.py`, JSON Schema parsing, syntax compilation, and the repository's final-head integration gates. Distinguish source completeness from fully playable game qualification, narrative coherence testing, and device release approval.

## Rollback and telemetry
Retain immutable receipts and the prior version when a transaction fails. Record rejection reason, version, status, and phase index as non-secret telemetry. For cross-shard transitions, synchronize durable event identity and state version under a single world lease.
