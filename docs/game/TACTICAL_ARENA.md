# Source-bound tactical arena (Studio B)

The canonical Python CLI now exposes \`python -m skeleton combat-arena\`.
This is a **playable offline turn simulation**, not a claim that a 3D
renderer, native game installer, gamepad, audio mixer, or cryptographic
signer is implemented. It consumes the same deterministic gameplay event
and save contracts as the existing combat engine.

## Try the original encounter

\`\`\`sh
python -m skeleton combat-arena demo
python -m skeleton combat-arena auto --source-json '{"schema_version":"skeleton.tactical_arena.v1", ...}'
\`\`\`

For authored games use \`simulate --source-json JSON --actions-json JSON\`,
then \`resume --session-json JSON --actions-json JSON\`. A save can be
checked with \`verify --session-json JSON\`. Input is bounded to 128 KiB
per CLI argument, sources are restricted to 32x32 cells, 16 actors, 512
walls, and 256 turns. No network connection or provider credential is
required.

## Gameplay and replay contract

Every actor has a source-defined team, position, HP, attack, defense,
speed, and orthogonal weapon range. Actors take turns in descending speed
and then stable ID order. A living actor can move exactly one cell in a
cardinal direction, attack an enemy in orthogonal line of sight, guard to
halve the next incoming hit, or rest to restore two HP. Walls, bounds,
and other living actors block movement; walls and intervening living
actors also block ranged attacks. Friendly fire is rejected. The game
ends when one team remains or the authored turn limit is reached.

Each action stores its pre-state digest, post-state digest and receipt.
A save contains a source digest, event bus digest and parent save digest.
Resume and verify **replay every action** and compare the entire derived
snapshot. SHA-256 detects accidental and naive tampering; it is not a
signature and does not establish who authored the source. Authorization
and asset licensing remain responsibilities of the upstream source owner.
No untrusted source-supplied scripts are executed.

## Regression commands

\`\`\`sh
python -m pytest skeleton/testing/test_tactical_arena.py -q
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
\`\`\`

Full repository exact-head checks and device qualification remain
separate release gates. The tactical arena is intentionally a source-
bound offline simulation with explicit unsupported renderer capabilities.

## Interactive offline play and pathfinding

\`python -m skeleton combat-arena play --demo\` prints one JSON object
per line. Each human turn includes an accessible ASCII grid, stable actor
legend, legal cardinal moves, legal targets, source-bound state digest
and valid action kinds. Supply an action JSON line such as
\`{"kind":"move","actor_id":"scout","direction":"east"}\` or
\`{"kind":"guard","actor_id":"scout"}\`. Use \`--auto-team reedbound\`
to assign one authored team to the deterministic offline opponent. The
opponent uses bounded breadth-first search over the actual collision
map, not a model call or network service. At least one team must remain
human-controlled in interactive mode.

A complete terminal session is emitted only after a genuine win or draw.
EOF, oversized commands, malformed JSON, out-of-turn actions and retry
exhaustion fail closed. Interactive checkpoints can be replay-verified and
resumed with \`--resume-json JSON\` after the author source is checked.
The policy never teleports an actor, skips an obstacle, or bypasses the
canonical turn engine. An unreachable opponent yields a guard/rest action
rather than a fabricated route.

Run \`python -m pytest skeleton/testing/test_arena_interactive.py -q\`
alongside the core tactical arena suite before exact-head CI qualification.
