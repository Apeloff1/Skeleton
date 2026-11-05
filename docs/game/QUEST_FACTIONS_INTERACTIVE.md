# Interactive NPC faction campaign

Run `python -m skeleton quest-factions-play --demo` and enter one JSON object
per line. The runtime prints canonical JSON-line frames: `prompt` with
currently legal authored actions, `transition` with earned consequences,
`rejected` for invalid moves, and `checkpoint` with a replay-verifiable
portable save. No network or hosted AI is required.

Use `{"action":{"kind":"talk","npc_id":"guide","decision":"aid"}}`,
`{"action":{"kind":"travel","to":"forge"}}`, or any action offered in
the current prompt. The authored quest and faction rules both validate every
transition. No free reputation, teleportation, crafting or currency injection
is possible. `{"command":"save"}` emits a full checkpoint without moving
the game, `{"command":"export"}` emits the portable checksum bundle, and
`{"command":"quit"}` returns a checkpoint. EOF also preserves a checkpoint.

Resume with `--resume-json JSON`; authored games use `--source-json JSON`.
`--source-digest DIGEST` rejects a changed or untrusted source identity.
`--checkpoint-every N` (1..32) periodically emits checkpoints, and
`--max-turns N` bounds accepted gameplay actions. Eight consecutive invalid
inputs stop the session rather than allowing unbounded rejection loops.
Every save must pass replay verification before resuming.

Focused test:
`python -m pytest skeleton/testing/test_quest_factions_interactive.py -q`.

Security: digests detect corruption but do not authenticate authors. These
commands are not proof of release, device or installer qualification.
