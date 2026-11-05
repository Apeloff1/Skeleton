# Studio A — Original Scene Puzzle Gate

`world-puzzles` adds authored questions and answers to canonical world scenes.
A puzzle unlocks exactly one existing choice, never changes canonical world
source, and cannot grant model write authority. The deterministic verifier
explores solve actions and world choices together, proving reachable puzzles,
reachable endings, bounded state count and absence of gameplay dead ends.

## Reviewed operator workflow

1. Create a world using `world-canon`.
2. Run `python -m skeleton world-puzzles --store STORE propose --world-id clocktower --prompt "Original bell puzzle" --puzzle-id bell_riddle --scene opening --question "Number after two?" --answer three --hint "Count" --unlock-choice pursue_goal`.
3. Save the `proposal` JSON with `save --world-id clocktower --create --puzzles-json JSON`.
4. Open the CSP-bound offline editor using `editor --world-id clocktower --expected-digest SHA`; export unapproved typed JSON.
5. Edit with `edit --world-id clocktower --expected-digest SHA --operation-json JSON`; actions: add_puzzle, replace_puzzle, remove_puzzle.
6. Approve with `approve --world-id clocktower --expected-digest SHA --review-note "Author reviewed"`.
7. Compile with `compile --world-id clocktower --expected-digest APPROVED_SHA` and verify with `verify --world-id clocktower`.

The HTML5 handoff has a strict CSP, no network, no external assets, no
dynamic HTML injection and no executable authored code. Wrong answers show
an authored hint; correct answers unlock the exact choice and produce a
deterministic in-player action trace. Answer text is visible in offline
client source and is not a security credential.

The Jeeves read-only tools `world.puzzles_propose_preview` and
`world.puzzles_preview` cannot persist or approve. Every save resets
approval; a changed world digest invalidates the puzzle lease. All writes
are descriptor-anchored, bounded, exclusive-locked and fsynced. Receipt and
playable byte mismatches fail verification. No consumer/device/release claim.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_puzzles.py -q`.
