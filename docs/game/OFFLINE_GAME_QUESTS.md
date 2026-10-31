# Offline original-game pickups, crafting and quest claims

The canonical `python -m skeleton app game-project` CLI supports real
source-bound item pickup, inventory spending, crafting and quest claiming on
the same deterministic integer-tick platformer as the portable game capsule.
This overlay does not create a second physics engine or alter the underlying
game save, and does not certify rights or native hardware.

Author a `skeleton.game.play_quest_manifest.v1` JSON object with the
verified capsule's `capsule_sha256`, up to 64 collectible placements,
32 recipes and 32 quests. Every collectible has a unique lowercase
`id`, `item_id`, traversable `x`/`y` and positive `amount`.
Recipes have `id`, nonempty `costs` and one `output`; quests have
`id`, prerequisite quest IDs in `requires`, nonempty `costs` and
one `reward`. IDs use lowercase ASCII letters, digits, hyphen and
underscore. Cycles, unknown prerequisites, duplicate IDs, unbounded
quantities and wall placements are rejected.

For every saved controller frame, supply exactly one explicit action
`{"craft":null,"claim":null}`, replacing either null with a declared
recipe/quest ID when desired. At each actual frame boundary the engine
replays the original platformer control, picks up every unclaimed
collectible at the resulting avatar coordinate, executes a requested craft
by spending existing inventory, then claims a prerequisite-qualified
quest by spending its costs and adding its reward. Collectibles and quests
are one-time; crafting may repeat only while ingredients remain.

```sh
python -m skeleton app game-project --play-quest-overlay session.json --session-capsule capsule.json --quest-manifest quests.json --quest-actions decisions.json --quest-output quest-save.json
python -m skeleton app game-project --verify-quest-overlay quest-save.json --session-capsule capsule.json
```

The output includes the complete verified source-bound session, authored
manifest, per-frame decisions, final inventory, pickup/quest state, ordered
events and a SHA-256 integrity receipt. Reopening reconstructs the same
gameplay and rejects modified saves, forged rewards, missing inventory,
invalid decisions, unknown schema versions and mismatched source capsules.
Output is exclusively created in an existing local directory, never
overwritten. Symlinked input files and oversized data are rejected.

This is offline single-player simulation. The hash is **not a signature**
or trusted multiplayer anti-cheat evidence. Native renderers, proprietary
game exports, third-party content and independent legal clearance are
not provided by this module.
