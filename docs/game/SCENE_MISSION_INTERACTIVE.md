# Playable offline mission terminal

The canonical scene-mission director owns all movement, choices, quest
dependencies, earned reputation, save lineage and ending consequences.
This terminal accepts bounded user commands and never executes authored
scripts, invokes providers or grants client-supplied rewards.

Run `python -m skeleton scene-mission-play --demo` and enter:

```text
choose restore_lantern help
collect find_key
travel north
travel inside
finish lantern_restored
```

Use `--source-json` for an authored mission or `--resume-json` for the
full `session` member of a checkpoint event. `--source-digest` pins a
trusted source identity before any output. `--checkpoint-every` is 1..64;
`--max-turns` is 1..512 per invocation. Inputs can also be strict JSON
mission actions. JSON with duplicate keys, nonfinite numbers or oversized
lines is rejected. Every prompt shows canonical currently legal actions.

Output is JSON Lines with started, prompt, accepted, checkpoint, invalid
and terminal events. EOF, three invalid attempts, exhausted turn budget or
no legal action emit a replay-verifiable checkpoint before returning error.
The terminal exports and reimports the completed game bundle before
declaring success. Digest receipts detect accidental corruption but are
not authentication signatures; never trust arbitrary source content.

Focused validation:
`python -m pytest skeleton/testing/test_scene_mission_interactive.py skeleton/testing/test_scene_mission.py -q`.
Exact-head CI and release gates remain required; unexecuted tests are not passes.
