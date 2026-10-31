# Faction governance: land stewardship

## Fictional policy mandate
This `frontier_land_stewardship` ballot governs a bounded, in-world frontier decision. It does not conduct real elections, verify citizenship, confer legal rights or issue external account permissions.

## Ballot constants
- Proposal family: `land_stewardship`
- Simulated governance domain: `frontier`
- Delegate seats: 7
- Quorum threshold: 3 distinct delegates
- Approval floor: 2 affirmative votes plus a strict majority of votes cast
- Replay ledger capacity: 256 accepted events
- Allowed ballot choices: yes and no
- States: idle, voting, approved, rejected

## Lifecycle
1. A trusted world host authenticates the proposer and validates the proposal scope.
2. The host opens a ballot with a unique proposal identifier and event ID.
3. Each authorized delegate casts a single vote bound to the proposal.
4. The coordinator enforces expected state version before applying a ballot.
5. Finalization waits for quorum; approval requires its configured threshold and majority.
6. A terminal approval or rejection cannot be reopened by normal commands.
7. The host atomically persists state and receipt before notifying observers.
8. A separate authorized world action may consume the recorded decision.

## Integrity rules
- The same event identifier cannot be applied twice.
- Each delegate votes once per ballot even with distinct event IDs.
- Stale versions and mismatched proposal identifiers reject without mutation.
- Insufficient quorum cannot produce an approval.
- Unknown delegate IDs, unsupported ballot values and extra command fields are invalid.
- Read-only inspection does not mutate version or count votes.
- Cancellation rejects the ballot and remains a terminal action.

## Security considerations
Delegate strings are allowlisted but are not authenticated credentials. The host must bind every caller to a seat, enforce separation of duties, check proposal eligibility, and prevent client-side fabrication. Approval is a fictional-game decision; it never overrides repository CI, game-server security, real-money controls, or release policies.

## Durable operation
The reference module provides immutable state transitions and deterministic receipts only. Store the proposal, delegate vote ledger, unique receipt IDs and version within a single transaction. Multi-host operation requires an authoritative partition and optimistic compare-and-swap. An in-memory ledger reaching its capacity must be checkpointed under a separate verified retention protocol.

## Test protocol
Run `python -m pytest -q skeleton/testing/faction_governance_v1/test_frontier_land_stewardship.py`, Python compilation, JSON Schema parsing and synthetic scenario replay. Follow with repository identity, security, dependency, artifact and exact-head integration gates.

## Boundaries and further work
NPC narrative persuasion, diplomatic leverage, vote trading and faction penalties belong to distinct independently reviewed systems. Do not infer legitimacy from the deterministic ballot alone. Real game balance, network failure recovery, stakeholder consent, native-device performance and consumer readiness remain unqualified.
