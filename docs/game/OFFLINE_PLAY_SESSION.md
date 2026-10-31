# Source-bound offline play sessions

`python scripts/game/game_project.py --play-capsule project.json --controls-file actions.json --save-session save.json`

The actions file is `{"controls":[{"left":false,"right":true,"jump":false}]}`.
Each command admits 1–64 frames, the entire history is limited to 1,024 frames,
and a win is terminal. No renderer, device driver, network, native exporter,
proprietary assets, model provider or license verification is implied.

Resume from an independently verified original capsule and an existing save:

`python scripts/game/game_project.py --resume-play-session save.json --session-capsule project.json --controls-file more.json --save-session save-2.json`

Verify/replay a save without changing any file:

`python scripts/game/game_project.py --verify-play-session save-2.json --session-capsule project.json`

The capsule verifier rechecks source and edited tile hashes, the original
rights manifest, the platform planning catalog and controller playability.
Session verification then replays every saved control from the canonical spawn
and compares the entire resulting state and digest. Hashes provide integrity
against accidental changes, **not** cryptographic authentication against an
attacker able to rewrite both the source and receipt. The CLI writes new files
exclusively, never silently replaces a save, and requires local regular
non-symlink inputs. A 1,024-frame history is bounded and replayed on every
resume; this is a deliberate correctness-over-throughput tradeoff.

Supported: deterministic headless grid controls and local source-bound save
replay. Not supported: on-device rendering, sound, multiplayer authority,
third-party game imports, legal release clearance or native target binaries.

The same actions are reachable from the assembled product via
`python -m skeleton app game-project --play-capsule ...` and
`python -m skeleton app game-project --verify-play-session ...`.

For a read-only ASCII preview of the last verified player position, run
`python -m skeleton app game-project --render-play-session save.json --session-capsule project.json`.
This renders a text grid with `@` for the player; it does not assert GPU,
native desktop or mobile renderer support.
