# Cinder Ridge — original playable rescue vertical

Cinder Ridge is a deterministic, offline, turn-based original game, implemented in `skeleton.game.gameplay.ridge_rescue`. It is intentionally separate from the Harbor vertical. The player must navigate a finite tile map, rescue civilians, manage weather and stamina, gather finite resources, craft signal gear, defeat or avoid hostile raiders, and choose a consequence-bearing evacuation. There is no network, external model, paid service or nondeterministic RNG.

## Play from source

`python -m skeleton.game.gameplay.ridge_rescue.cli inspect` validates the authored world and its static reachable objectives. `python -m skeleton.game.gameplay.ridge_rescue.cli interactive` shows current actions with indices, accepts one choice per turn, and returns a portable replay bundle at the end. `play --actions '[{"verb":"rest"}]'` executes a deterministic action list without a terminal. `guide --actions '[...]'` supplies observational static path guidance, not a victory promise. `verify --bundle run.json` independently reconstructs the source world and replays every action; `author --operation '{"kind":"rename","target":"world","value":"New Ridge"}'` produces a CAS-bound immutable revision, and `verify-author` independently reconstructs that edit. Use `--output new-file.json` to create a new local file without overwriting an existing one.

## Core contracts

World source is `ridge.rescue.world.v1` with strict field sets, bounded 24x24 rectangular terrain, a finite object count, unique identifiers and positions, no impassable spawn or objective, and 8–256 turns. Each action is checked against `available_actions` before mutation. Invalid or terminal actions fail closed without changing the caller state. Weather damage is tied to turn number; raiders move in sorted ID order using deterministic tie-breaking. A protection ending requires the signal beacon to be actually crafted and lit at the shelter. The alternative salvage ending is distinct and cannot claim protected evacuation.

A portable `ridge.rescue.run.v1` envelope includes authored world, exact actions, final state and a canonical SHA-256 digest. Digest is **corruption detection, not authenticity**: hostile actors can replace and rehash an entire bundle. Verification recomputes all transitions and rejects mismatched outcomes, invalid actions, tampered states and unsupported versions. This is not a signed competitive leaderboard or trusted remote save. The CLI's output is create-only, 0600, fsynced and never intentionally overwrites. Parent-directory trust and cross-process transactional guarantees are not claimed.

## End-to-end acceptance

Focused tests cover source validation, movement and collision, finite crafting, NPC behavior, rescue and mutually exclusive endings, state replay and tamper rejection, transactional authoring and CLI. Required exact-head CI, independent runtime testing, security review and device qualification must be completed before promotion or release. Draft size and CI state are not release proof.
