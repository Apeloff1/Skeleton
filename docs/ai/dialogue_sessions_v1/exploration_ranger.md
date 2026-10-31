# Dialogue scene: ranger

## Purpose
This exploration scenario models a deterministic six-beat conversation through immutable state changes and explicit receipts. It does not invent localized dialogue text, authorize a real user, or persist conversation history.

## Interaction rules
- Scenario ID: exploration_ranger
- Initial trust: 25 / 100
- Initial tension: 10 / 100
- Negotiation minimum trust: 30 / 100
- Accepted rapport gain per stage: 5
- Tension increase on negotiation: 6
- Stage progression: greet, ask, explain, negotiate, reconcile, close
- Maximum ordinary interaction turns: 16

## Evidence and narrative authority
The explain and negotiate beats require distinct evidence identifiers issued by the trusted world runtime. This implementation checks their nonempty shape and replay identity but cannot authenticate the origin. The game host must verify the evidence before invoking a transition.

## Director execution
1. Load the current authoritative dialogue state for one NPC and world instance.
2. Evaluate `snapshot` to identify the expected beat.
3. Resolve player intent through a separately reviewed typed intent adapter.
4. Validate the event identity, optimistic version and proof within the trusted game server.
5. Apply `choose` to calculate an immutable state and decision receipt.
6. Commit accepted state and receipt atomically, then publish the narrative beat.
7. Reject replayed identities and stale optimistic versions without mutation.
8. End the encounter at explicit withdrawal, resolution, or a policy failure.

## Failure scenarios
The director rejects out-of-order beats, missing proofs, reused evidence, stale versions, repeated event IDs, invalid command fields, wrong data types and insufficient rapport. A rejected result never grants a story milestone or advances a quest.

## Observability and durability
Track scene identity, version, chosen beat, acceptance, rejection reason and normalized numeric trust/tension. Keep raw user dialogue private. Host-side replay should use immutable durable event journals with idempotency fences.

## Integration and validation
Execute the corresponding Python regression file and compile the policy module. Parse the request schema and scenario. Run exact-head CI, lint, artifact, malware, security and integration checks. Preserve admission caps. Synthetic conversation scripts are not playable-content qualification or release evidence.

## Expansion
Branching alternatives, localization, speech-to-text and model-generated responses must be mapped into the same typed choice contract. Model outputs are proposals, not permission to skip the gate. Add semantic validation of character continuity at the world-engine layer.
