# Original NPC testimony and branch-exclusive canon proof

This source-complete vertical connects an original author prompt to typed
testimony proposal, explicit reviewed publication, deterministic branch proof,
private player-session replay, offline HTML5 playable and offline edit/export.

A statement is source-leased to both the canonical world and reviewed cast.
Its trigger is a real choice arriving at a scene where its actor is present.
Each statement has a claim identifier, supports/denies stance, original text,
and firsthand/hearsay/record provenance. Conflicting stances on the same claim
may exist in mutually exclusive branches, but proof rejects any reachable
playthrough that discloses both. Every statement must have an actual choice
witness and every canonical ending must remain reachable. Exploration is
bounded to 4096 states and 128 steps; unknown budgets fail closed.

CLI: `python -m skeleton world-testimony --store DIR propose --world-id harbor
--prompt "..." --statement-id tala_ledger --actor tala --scene resolution
--choice pursue_goal --claim ledger_moved --stance supports
--text "I saw the ledger cross the bridge." --provenance firsthand`.
Proposal is read-only; operator `save --create --testimony-json JSON`,
`inspect`, `edit --expected-digest HASH --operation-json JSON`,
`approve --expected-digest HASH --review-note TEXT`,
`compile --expected-digest HASH`, `verify`, `editor`, and
`player --choices-json JSON` or `player-slot --slot ID` complete the
custody and gameplay workflow. Writes are descriptor-anchored and serialized
under the world lock. Every write revokes approval; only explicit approval
can authorize a compiled playable.

The editor exports unapproved JSON for canonical CLI revalidation; it never
writes the source store. Browser gameplay uses a hashed inline script,
textContent, no network access, no external assets, and no evaluation.
Receipts bind source digests, proof digest and exact playable bytes.
The Jeeves tool registry exposes only read-only preview operations.

Focused tests: `python -m pytest skeleton/testing/test_jeeves_world_testimony.py -q`.
The code is a draft and has no consumer/device or release qualification.
