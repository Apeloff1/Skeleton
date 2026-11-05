# Studio A — Reviewed counterfactual world branches

This original-world vertical follows a real authored world and a persisted
player session. It never trusts an LLM assertion as a player transition and
never silently edits a save or invents an ending after bounded search fails.

## Operator flow

Create and compile a canonical world with world-canon, then create and advance
a world-session save. Every actual decision must replay against the source.

Use python -m skeleton world-counterfactual --store PRIVATE propose
--world-id marsh --slot save --prompt "Compare the courier's choices".

The returned digest is an optimistic lease. Preview computes deterministic
alternatives and their ending and flag consequences. Edit accepts a strict
JSON set_limits or set_prompt operation, revokes approval and requires renewed
review. Approve explicitly with a note and the current digest, then compile
using the new digest. Verify independently rebuilds the playable HTML, static
report, JSON witness and source-bound receipt.

All artifacts live in the private descriptor-anchored world directory.
The world lock serializes world, session and review writes. Every review
binds the exact world digest, session digest, slot and ordered choices.
Player advancement, source revision, stale CAS, malformed identifiers,
unsafe source leaves and tampered artifacts fail closed.

## Semantics

Alternatives are only taken at decisions the player actually reached.
The solver applies an alternative at the historical prefix and performs
deterministic bounded breadth-first search for an authored ending. Each
candidate trace is independently replayed. Cycles are bounded by
(scene, flags) states. Step or state exhaustion is an error, not a
false unreachable claim. More than 64 variants is an error, not sampling.
No divergence is invented for an unplayed session.

The review is advisory authoring evidence, not automatic approval, model
prediction, device certification or engine compatibility qualification.
The offline playable is compiled from canonical world source. Static report
HTML uses deny-all CSP, no JavaScript or external resources, and escapes
authored text.

Focused regression: python -m pytest
skeleton/testing/test_jeeves_world_counterfactual.py -q

Required exact-head repository security and CI gates remain mandatory.
