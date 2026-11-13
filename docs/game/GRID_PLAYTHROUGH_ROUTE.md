# Replay-verified full grid campaign playthrough solver

The original grid campaign combines movement and collision, items,
NPC interactions, crafting, quests, enemy combat, save/replay and
alternate endings. `solve` explores **real canonical commands** to
find a shortest playable path to a requested authored ending.

```sh
python -m scripts.game.offline_grid_campaign solve --goal-ending homecoming
python -m scripts.game.offline_grid_campaign solve --goal-ending bright-harbor
python -m pytest skeleton/testing/test_grid_playthrough_route.py
```

The solver enumerates legal collect, talk, craft, strike, move and
finish commands. It executes every candidate through `Session.step`,
which enforces actual walls, enemy occupancy, health, item ownership,
quest prerequisites and terminal endings. Each winning save is
restored by `Session.restore`, replaying its complete event ledger.
No imaginary moves, items or ending grants are accepted.

Results contain the exact source digest, target ending, search budgets,
expanded states, visited states, attempted transitions, ordered
commands, final state digest, replayable save and checksum.
`verify_playthrough` recomputes the bounded search and checks
the saved ending. Receipts are integrity checks, not signatures.

The planner caps state exploration at 4096, depth at 128 and all
attempted transitions at 32768 (including rejected moves).
`solved` includes a real replay witness. `unreachable` requires
complete exploration; budget exhaustion yields `inconclusive`,
never a false unwinnable claim. It uses no network, provider or
external scripts and makes no device-qualification claim.
