# Source-bound tile push puzzles

The player can push movable crates on authored tile maps, activate pressure
plates and open authored scene exits. The canonical tile engine still owns
movement, walls, pickups, earned keys, transitions and terminal endings.

## Play and checkpoint

Run \`python -m skeleton scene-push demo\` for an original quay puzzle. The
result is a versioned session containing the normalized authored source,
ordered action receipts, deterministic state and save-parent digest chain.

Use \`scene-push simulate --source-json ... --actions-json ...\` to play a
custom puzzle, \`resume --session-json ... --actions-json ...\` to continue a
verified checkpoint, \`verify --session-json ...\` to replay from source,
\`legal --session-json ...\` to inspect legal moves, and \`export\`/\`import\`
to package and restore portable offline saves. CLI output is strict JSON.
Invalid input returns code 2 and a JSON error on stderr.

\`scene-push author --source-json ... --expected-digest ... --edits-json ...\`
supports transactional crate/plate relocation and optional
\`--preview-actions-json\`. The source digest is a compare-and-swap lease:
stale edits fail closed without mutating the source. The author result can be
fed directly into simulate. The \`solve\` command performs bounded shortest
action search; its status is \`found\`, \`unreachable\`, or \`inconclusive\`.
Search exhaustion is never advertised as a proof of impossibility.

## Source contract

The schema is \`skeleton.scene_tile_push.v1\`, with \`tile_source\` (canonical
\`scene_tile_walk.v1\`), \`turn_limit\`, and three authored arrays:

* \`crates\`: unique \`{id, scene_id, at:[x,y]}\` objects.
* \`plates\`: unique \`{id, scene_id, at:[x,y]}\` pressure plates.
* \`locks\`: \`{scene_id, exit_id, requires_plates:[id,...]}\` bound to
  authored exits. Every required plate must be occupied by a crate.

Crates cannot begin on walls, spawns, pickups, exits or other crates.
Pushing into walls, map boundaries, other crates, pickups or exits is
rejected. Plates can be shared across authored exit conditions; crate
locations persist through scene travel. Source and action limits are
bounded. There are no executable authored callbacks, remote fetches or
implicit item grants.

## Integrity and release holds

A saved checkpoint is accepted only when rebuilding the complete journal
from its normalized source yields exactly the same state, receipts, event
bus digest and save ancestry. Export checksums detect accidental corruption
and unauthenticated tampering; they are **not** signatures or authorization
proofs. Do not treat a checksum as provenance.

Run \`pytest skeleton/testing/test_scene_tile_push.py\` and the repository's
mandatory exact-head CI before promotion. The original demo and tests cover
physical crate collisions, locked exits, earned keys, deterministic
save/resume, transactional authoring, solver exhaustion, malformed JSON,
forged journals, bundle tampering and CLI dispatch. No consumer-device or
release qualification is implied by source publication.

## Live play and end-to-end acceptance

`python -m skeleton scene-push-play demo` replays the original puzzle through
exactly the same bounded JSON-line input protocol used by a real player.
`scene-push-play play --source-json ...` prompts with a state digest, legal
actions, crate locations and activated plates, then accepts one action JSON
per line. Supply `--session-json` to resume an independently replay-verified
checkpoint. Invalid input is retried at most three times without changing
state; EOF, exhausted turns and malformed commands never become a victory.

`python -m skeleton scene-push-accept demo` proves a real authored victory,
mid-session portable export/import, exact restart equality, editor preview,
full replay and final portable package. `scene-push-accept accept --source-json
... --actions-json ...` verifies custom authored levels. Acceptance receipts
are deterministic integrity evidence, not device or release certificates.
