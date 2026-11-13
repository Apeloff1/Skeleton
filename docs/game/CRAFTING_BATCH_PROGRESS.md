# Source-bound batch crafting progression

The existing crafting planner explores one recipe batch per action.
For multi-item game goals, that can create unnecessary interactions.
`solve-batch` explores legal 1..100 batch quantities through the real
`CraftEngine`, finding the shortest *number of crafting actions* while
preserving currency, inventory, prerequisite flags, save replay and
finite resource budgets.

```sh
python -m skeleton.game.gameplay.crafting_cli solve-batch \
  --plan docs/game/fixtures/lantern_harbor_crafting.json \
  --goal-item lantern --goal-quantity 2 --max-batches 100
python -m pytest skeleton/testing/test_crafting_batch_planner.py
```

The original Lantern Harbor example starts with four fiber, two oil and
ten coins. The optimal route batches two wicks, then two lanterns in
two real transactions. Both actions are replayed by the canonical
engine and the resulting save can be restored without granting
inventory or money from a client-supplied assertion.

The result is versioned, source-digest-bound and includes the exact
goal, search budgets, state/transition counts, ordered actions,
replayable save and checksum. The `verify_batch_route` API recomputes
the search and restores any winning save. It rejects changed plans,
forged receipts, noncanonical goals and unsupported schema versions.

`solved` has a concrete replay witness. `unreachable` means the
finite explored state space has been exhausted under the current
recipes and bounds. `inconclusive` means a search limit was reached,
not that a game is unwinnable. Search is capped at 4096 states,
64 actions, 100 batches per action and 16384 attempted transitions.
No provider, network, marketplace payment or native asset is used.
This is offline in-game economy simulation, not financial custody.
