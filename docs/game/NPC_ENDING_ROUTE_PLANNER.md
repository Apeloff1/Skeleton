# NPC authored ending route planner

The existing offline NPC schedule CLI can now find a replayable path to an
original authored ending without modifying the source, facts or save state.

```sh
python -m scripts.npc_schedule_cli \
  --schedule skeleton/testing/fixtures/lantern_harbor_npc_schedule.json \
  --solve-ending harbor_restored
```

The solver explores only authored interaction windows and executes each
candidate through `NpcSession.apply`. Successful results include canonical
commands, state digest and a portable snapshot verified by
`NpcSession.restore`. Lexical NPC ordering and increasing schedule ticks
make repeated runs deterministic. It supports alternate endings.

`--max-search-nodes` (1..4096) and `--max-search-depth` (1..64) bound
resource use. `inconclusive` means a budget was reached, not an impossible
ending. `unreachable` means all reachable authored choices were exhausted
without hitting a cutoff. No provider, network or external content is used.
