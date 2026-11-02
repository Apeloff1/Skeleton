# Lantern Quay mission-board production vertical

The authored mission board is stored in `skeleton/game/gameplay/fixtures/harbor_lantern_quay_missions.json`.
It binds to the original playable world's ID, checks mission prerequisites in source
order, and rejects cycles, duplicate IDs, unknown items, blocked destinations,
oversized boards, impossible objective types and noncanonical objective fields.

Progress is **earned by actual canonical player actions**. A mission's objectives
are credited only after its prerequisites were complete *before* the current
tick. Gathering, crafting, trading, movement, cargo delivery and final player
choices are evaluated against the same transitions that power interactive play.
Per-mission deadlines and the global gameplay tick budget remain enforced.

The `mission-report` CLI reads a portable gameplay bundle and mission board,
replays the complete source-bound action history, and writes a canonical report
with a per-tick hash-linked mission journal. `verify-mission-report` does not
trust saved points or mission flags: it independently recomputes the entire
journal from the embedded world and verified gameplay event chain.

`solve-missions` executes the canonical bounded campaign planner and refuses
to report mission success unless **every authored objective** is earned.
For the sample board, the signal ending earns salvage (10), workshop (20),
and dispatch (30) points. The shelter ending is a legitimate game ending but
cannot earn the signal-only dispatch mission.

## Example

```sh
python -m scripts.game.harbor_crafting demo --require-win > /tmp/lantern-bundle.json
python -m scripts.game.harbor_crafting mission-report --bundle /tmp/lantern-bundle.json --require-all > /tmp/lantern-missions.json
python -m scripts.game.harbor_crafting verify-mission-report --report /tmp/lantern-missions.json --require-all
python -m scripts.game.harbor_crafting solve-missions --choice signal --require-all
```

These portable JSON digests provide tamper evidence and replay consistency,
not authenticated authorship or a signed distribution. No network, dynamic
execution, paid assets, device qualification or release claim is involved.
