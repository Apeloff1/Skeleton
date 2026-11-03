# Studio A — Reviewed Original Item Consequences

The `world-inventory` vertical binds authored inventory effects to an exact
canonical world digest. An original prompt creates a typed unapproved item
proposal. A human operator saves it under an optimistic digest lease, reviews
it, approves it, compiles a network-disabled HTML5 game, and verifies both the
exact playable bytes and the source/proof receipt.

## Operator flow

1. Create a canonical world with `world-canon`.
2. Run `python -m skeleton world-inventory --store STORE propose --world-id harbor --prompt "An original lantern" --item-id lantern --name Lantern --description "Glass beacon" --pickup-choice pursue_goal`.
3. Save the JSON returned under `proposal` with `save --world-id harbor --create --inventory-json JSON`.
4. Open a CSP-bound offline editor with `editor --world-id harbor --expected-digest SHA`. Export unapproved JSON, then save it with an exact digest lease.
5. Review and edit with `edit --world-id harbor --expected-digest SHA --operation-json JSON`. Supported operations: replace_item, add_item, upsert_effect, remove_effect.
6. Approve using `approve --world-id harbor --expected-digest SHA --review-note "Author reviewed"`.
7. Compile with `compile --world-id harbor --expected-digest APPROVED_SHA`; verify with `verify --world-id harbor`.

A browser playable is emitted as `harbor.inventory.playable.html`. The
player never requests network access, never executes authored HTML, and
uses text-only DOM nodes. Item spending is checked before a choice is shown;
item gains respect capacity. Every reachable non-ending state must retain a
legal choice. All ending witnesses and authored effects must be reachable.

## Trust boundary

The read-only Jeeves tools `world.inventory_propose_preview` and
`world.inventory_preview` cannot approve or write. A supplied
`approved:true` is reset on every save/edit. A world revision invalidates
the item lease. All source and receipt files are bounded and read through
descriptor-anchored, no-follow custody. Writes require an exclusive world
lock, an exact expected source digest, and fsynced atomic replacement.
Receipt and playable tampering fail verification. No native/consumer,
rights, release or device qualification is implied by a browser handoff.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_inventory.py -q`.
