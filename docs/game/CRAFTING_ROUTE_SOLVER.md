# Offline crafting progression planner

The installed `skeleton-game-craft` CLI now includes a bounded `solve` mode:

```sh
skeleton-game-craft solve --plan docs/game/fixtures/lantern_harbor_crafting.json \
  --goal-item lantern --goal-quantity 1 --goal-flag light_available
```

The solver runs canonical crafting transitions locally and returns the shortest
event sequence (stable recipe-ID tie breaking), replay-verifiable save and source
digest. It never grants resources, mutates a save or calls a remote provider.
A goal may require an item quantity, a progression flag, or both.

`--max-nodes` defaults to 1024 (maximum 4096); `--max-depth` defaults
to 24 (maximum 64). `inconclusive` means a search budget was reached, not
that the goal is impossible. `unreachable` means finite graph exhaustion.
Use `CraftEngine.restore` with the same authored plan to verify a solved
witness before adopting its actions in an interactive session. This does not
certify game release, asset ownership or hardware compatibility.
