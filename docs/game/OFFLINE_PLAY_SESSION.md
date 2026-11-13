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

## Portable offline transfer

Create a source-bound, rights-attested, engine-neutral transfer bundle:

`python -m skeleton app game-project --export-play-bundle save.json --session-capsule project.json --bundle-output portable.json`

Reopen without needing the separate original files:

`python -m skeleton app game-project --verify-play-bundle portable.json`

Continue the same replay history on another offline machine:

`python -m skeleton app game-project --resume-play-bundle portable.json --controls-file more.json --bundle-output portable-next.json`

Bundles are bounded to 150 KiB of canonical content and use a strict
checksum, embedded capsule rights evidence and complete controller replay.
A digest is **not** an authentication signature or independent proof of
copyright ownership. Bundle export is portable JSON, not a native binary.


## Deterministic replay inspection and alternate timelines

Inspect any exact frame (including frame 0, the canonical spawn) without
trusting serialized player coordinates or modifying the source save:

`python -m skeleton app game-project --inspect-play-frame save.json --session-capsule project.json --at-frame 0`

The returned ASCII grid, position and prefix trace digest are independently
recomputed from the verified capsule and the original complete control history.
The source session SHA binds the inspection to its immutable parent receipt.

Create a new, divergent playthrough from an earlier frame with 1–64 new
controller inputs, without overwriting or editing the original save:

`python -m skeleton app game-project --fork-play-session save.json --session-capsule project.json --at-frame 2 --controls-file alternative.json --save-session alternate.json`

Frame 0 discards the old controls and starts from the canonical spawn.
A fork at or after a verified victory is rejected; earlier frames can branch
to a different ending. Every fork is fully replayed from original source,
remains subject to the 1,024-frame cap, and produces a normal independently
verifiable v1 session. The CLI receipt identifies the original session digest
and fork frame; a save by itself intentionally contains only its own replay
history and does not claim authenticated parent lineage.

A portable transfer bundle supports the same offline fork:

`python -m skeleton app game-project --fork-play-bundle portable.json --at-frame 2 --controls-file alternative.json --bundle-output alternate-portable.json`

The resulting bundle embeds the same original capsule with the new verified
session. Input files must be regular non-symlinks and output files must not
already exist. Frame inspection is read-only. No network, native renderer,
legal clearance, signature, or native target binary is produced.


## Actual turn-by-turn offline terminal play

For keyboard/screen-reader-friendly gameplay without preparing a controller
JSON file, open a verified original capsule and enter one command per frame:

`python -m skeleton app game-project --terminal-play-capsule project.json --save-session terminal-save.json`

The prompt accepts `a` (left), `d` (right), `w` (jump), `aw`/`dw`
(combined move and jump), `.` (wait), or `q` (quit). Commands are case
insensitive. Each accepted command advances one **actual deterministic**
simulation frame and prints the current ASCII map; the save contains the
canonical input history, not a self-declared player position. Contradictory,
duplicate, oversized or unknown commands fail closed. An empty or immediate
quit does not create a fake save. Victory ends the session.

Continue from a prior save (without overwriting it):

`python -m skeleton app game-project --terminal-resume-session terminal-save.json --session-capsule project.json --save-session terminal-next.json --terminal-max-frames 32`

A single terminal invocation admits 1–64 new frames; a complete play history
is limited to 1,024 frames. Keyboard prompts and map frames go to stderr,
leaving stdout as one machine-readable JSON completion receipt. Standard input
can be an interactive terminal or a bounded piped command stream; no network,
GPU, audio, live AI, third-party assets or native exporter is used. This is
**turn-based ASCII gameplay**, not a continuous real-time graphics engine.
