# reflection: epilogue narrative director

## Function
A typed, deterministic dialogue progression machine that controls six authored narrative beats and rejects unauthorized state advances. It is a fictional world component rather than an authentication or real-life decision service.

## Profile parameters
- Scenario key: epilogue_reflection
- Narrative domain: epilogue
- Minimum proposal rapport: 29
- Accepted beat rapport gain: 6
- Proposal tension increase: 5
- Six beats: introduce, listen, reveal, propose, agree, leave
- Protected beats: reveal and propose require distinct evidence IDs.

## Authoritative integration
1. Resolve acting character and world-instance permissions.
2. Load immutable current state and version from durable storage.
3. Verify evidence provenance and its binding to the requested scene.
4. Convert user or model authored dialogue into a typed beat choice.
5. Call `advance` with the exact optimistic version and a unique event ID.
6. Commit accepted state and receipt atomically with the evidence ledger.
7. Present new narrative text only after the authoritative commit completes.
8. Return rejection reasons without changing the active state.

## Failure containment
Unknown fields, invalid types, duplicate events, reused proofs, stale versions, wrong-stage choices and insufficient rapport fail closed. Withdrawal is terminal. A dialogue cannot be moved backward by a normal request.

## Privacy and safety
Proof text is only a shape-validated opaque token and is not identity verification. Never derive real-person trust, consent or social eligibility from fictional scores. The language model must not assert accepted transitions without receiving an authoritative receipt.

## Validation plan
Run the associated pytest regression file and Python compilation. Parse the request JSON Schema and synthetic scenario, then require all exact-head security, CI, source-ownership and integration gates. Synthetic success does not imply player experience, localization, accessibility or release certification.

## Future development
Branching language understanding, emotion modeling and dynamic intent recognition may be supplied by a separate typed inference adapter. Maintain deterministic authorization of state transitions and replay protection even under probabilistic language generation.
