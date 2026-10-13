# Tiled → original homebrew → consumer game

## Supported editor handoff

Tiled is an independent, open-source tile-map editor. This adapter supports
**bounded finite orthogonal Tiled JSON** maps containing exactly one visible
uncompressed numeric-GID `tilelayer` per game level. Every input is converted
into Skeleton's strict original `authored_tiles.v1` geometry and verified by
the same Python game-state transitions and safe-route solver used for consumer
builds. The Tiled program does not need to be installed on the consumer device.

Tiled JSON reference:
https://docs.mapeditor.org/en/latest/reference/json-map-format/

A Tiled JSON file uses `orientation: "orthogonal"`, `infinite: false`,
`width`, `height`, and `layers: [{type: "tilelayer", data: [GID, ...]}]`.
GIDs are positive integers in the native numeric array, **not** image pixel
data. The default palette maps:

| GID | Original game code | Gameplay |
| --- | --- | --- |
| 0 / 2 | `.` | traversable floor |
| 1 | `#` | solid wall |
| 3 | `S` | player start |
| 4 | `G` | level exit |
| 5 | `C` | collectible objective |
| 6 | `H` | optional hazard |

The complete authored game geometry must have a solid border, exactly one
start and exit, the exact number of collectibles specified in the intent,
and a playable hazard-free route. Each level's dimensions must match the
odd-sized world dimensions from the typed intent. Alternative tileset GIDs
can be mapped with a separate local palette JSON such as
`{"37":"#","38":".","39":"S","40":"G","41":"C","42":"H"}`.
The palette binds *numeric identities*, not texture files.

## Run through the complete original studio in one command

```shell
python -m skeleton.ai.game_builder.original_game_studio_cli \
  --intent intent.json \
  --tiled-level original-level-1.json \
  --tiled-level original-level-2.json \
  --human-reviewed \
  --companion-practice 2 \
  --mirror-attempts 128 \
  --trusted-local-operator \
  --output /tmp/tiled-original-consumer-project
```

For arbitrary numeric tile IDs also pass `--tiled-palette palette.json`.
For a two-stage editor/import handoff, instead run:

```shell
python -m skeleton.ai.game_builder.tiled_map_cli \
  --intent intent.json \
  --tiled-level original-level-1.json \
  --tiled-level original-level-2.json \
  --human-reviewed \
  --trusted-local-operator \
  --output original-authored.json
python -m skeleton.ai.game_builder.original_game_studio_cli \
  --intent intent.json \
  --authored-world original-authored.json \
  --human-reviewed --trusted-local-operator \
  --output /tmp/original-authored-consumer-project
```

The direct pipeline produces a Godot 4 source project, playable offline
browser game, independent replay proof, actual mirror-room gameplay attacks,
companion practice games, machine almanac and consumer review dossier. It
records `studio/tiled_import.json` with source-file hashes, canonical world
and proof digests, and the count of intentionally discarded tileset metadata.
The tool execution chain records `world.tiled` as a genuine executed
Jeeves/Dragon capability. It does **not** falsely claim that the Tiled
application itself was launched.

## Legal and trust boundary

- Only reviewed **tile placement geometry** is read into the game.
- Referenced TSX tileset source paths, URLs, images, shaders, scripts,
  object properties and artwork are never opened, fetched, copied or embedded.
  The executable uses Skeleton's independently generated original geometric
  visual presentation instead.
- Unknown GIDs, flip/rotation bits (including Tiled's high-bit flags),
  hidden layers, compressed/base64 data, infinite chunks, multiple layers,
  object groups, unexpected dimensions, duplicate JSON keys, large inputs,
  symlinks, and unsolved maps fail closed.
- Each local source file is capped at 700 KB and at most eight map documents
  can supply a single original game. Every game intent remains bounded by
  canonical game-builder geometry and complexity constraints.
- The `--human-reviewed` acknowledgement means an operator reviewed the
  geometry; it does **not** constitute copyright clearance, trademark
  authorization, console vendor rights, automatic publication approval, or
  a certification of a closed-platform SDK.
- The original consumer/game package remains blocked from publication unless
  independent human/legal, hardware, security and publisher evidence clears
  the existing consumer assurance gates.

This is an interoperability foundation, not a promise that arbitrary Tiled
maps can be turned into every game genre. Animation, object layers, NPC
scripts, physics objects, multiple graphical tilesets and external media
remain explicit future adapters requiring independent rights clearance.

Tests: `python -m unittest tests.test_game_builder_tiled_map_import -v`.
The test passes a Tiled JSON level through actual compiled original gameplay,
Godot/browser source generation, mirror room, and the consumer-readiness gate.
