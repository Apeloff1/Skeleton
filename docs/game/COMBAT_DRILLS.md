# Original combat drill workshop

The installed CLI `python -m skeleton combat-drill` provides offline playable
combat lessons using the canonical source-bound turn engine. It does not call
a model, network service, executable authored script, or external game engine.

## Play and export

```bash
python -m skeleton combat-drill preview
python -m skeleton combat-drill demo
python -m skeleton combat-drill play
```

The demo exports a complete JSON checkpoint containing normalized source,
a canonical combat save, player commands, deterministic opponent turns, grade
and integrity receipt. The `verify --session-json '<checkpoint>'` command
reconstructs all state transitions and bot actions from the authored source;
`advance --session-json ... --action-json ...` continues only an active
verified checkpoint. `simulate --source-json ... --actions-json ...` runs
a deterministic command batch. Output is machine-readable JSON; malformed
inputs produce a nonzero exit code and structured error on stderr.

The interactive `play` command emits JSON-line prompts containing the
actual actor, live legal enemy targets, turn and remaining command budget.
Enter a canonical action such as
`{"kind":"attack","actor_id":"scout","target_id":"warden"}`.
Three invalid actions in one turn abort rather than fabricating a win.
EOF also aborts. Opponents use the versioned deterministic tactical policy.
No automated actions are accepted as player commands.

## Authored source

A drill has schema `skeleton.combat_drill.v1`, a stable `drill_id`,
a canonical `skeleton.turn_combat.v1` scenario, `player_team`,
`max_player_actions` and `minimum_survivor_hp`. The player must win
within the authored action budget while preserving at least one player-team
actor at the required health threshold. A draw, loss, insufficient surviving
health or exhausted player action budget is a failure. The underlying
encounter also has its own total turn limit.

All unknown fields, invalid actor IDs, duplicate actors, non-integer budgets,
impossible survivor thresholds, nonfinite/duplicate JSON keys, out-of-turn
actions and friendly fire are rejected. The canonical turn engine bounds
actors and turns, and the drill bounds player commands. Import is replay
verified rather than trusting the exported grade or state. Integrity hashes
are not signatures; authorization and source provenance remain the
responsibility of the enclosing app.

## Deterministic acceptance

```bash
python -m pytest -q skeleton/testing/test_combat_drill.py
```

Acceptance covers interactive victory, restart/replay, enemy policy drift,
forged receipts, invalid authored goals, action budgets, CLI routing and
malformed JSON. Hardware/device and full exact-head CI are separate holds.
