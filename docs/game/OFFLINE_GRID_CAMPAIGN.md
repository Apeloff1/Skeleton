# Offline grid campaign — canonical game-plane text adapter

This adapter runs an original deterministic grid campaign without a network, model,
graphics renderer, or audio backend. It uses the canonical gameplay contract owner
for IDs, quest dependency validation, and canonical digests. It does **not** claim
Godot export, native 3D, audio synthesis, network multiplayer, or device certification.

Run from the repository root:

```sh
python -m scripts.game.offline_grid_campaign inspect
python -m scripts.game.offline_grid_campaign play
python -m scripts.game.offline_grid_campaign run --commands commands.json > output.json
python -m unittest skeleton.testing.test_offline_grid_campaign -v
```

The command file is a JSON list of `{"command_id":"unique","kind":"move","target":"east"}`
objects. Supported actions are move (north/south/east/west), collect (item ID),
talk (NPC ID), finish (ending ID), and wait (empty target). Rejected actions never
advance state. A successful run emits `{"save": {...}, "map": "..."}` to stdout.
For a later session, extract the `save` object into a JSON file and use
`--resume save.json`; the entire ledger is re-executed and checked against the
immutable authored source digest and state digest. There is no automatic disk
write, implicit network request, hidden model call, or provider credential.

Original sample: **Lantern Harbor**, CC0-1.0, written for this repository.
From the start, move east, collect `lantern`, move east, talk to `keeper`,
move south twice, east twice, south, and finish `homecoming`. At the goal,
`wanderer` is an alternate ending without the quest requirement. The map
shows @ player, # collision, * collectible, N NPC, G goal. The engine enforces
64x64 tiles, 128 objects/quests/endings, 4096 events and 64 KiB authored JSON.

A snapshot is a *tamper-evident deterministic replay record*, not a signed
authentication receipt. SHA-256 identity does not prove authorship, rights,
or provenance of arbitrary imported worlds. The operator remains responsible
for atomic persistence and for trusting external authored content. The
source contract is versioned; unknown versions and malformed dependencies
fail closed. CLI file reads reject symlinks at the final path on platforms
supporting O_NOFOLLOW and cap input bytes; parent-directory race resistance
and a production storage service are not claimed.

The `play` command offers a real interactive text-grid loop on a local terminal.
It renders the current map after each accepted action, rejects invalid commands
without advancing the tick, and prints a replayable save as the final output
line on victory, quit, or end-of-file. Keyboard text input is supported; touch,
controller, screen-reader and native rendering qualification remain separate.

A bounded turn-based enemy is also supported: original `mireling` starts
with 3 HP and attack 1. `strike mireling` requires Manhattan adjacency,
inflicts 2 damage, and permits a counterattack only while the enemy survives.
Living enemies block movement. Health starts at 10; zero health terminates in
`defeat`. No RNG, external game assets, or hidden real-time simulation is used.
Combat health and enemy state are included in source-bound save/replay hashes.
