# Cinder Ridge offline rescue league

The league accepts portable **actual game replays**, not claimed scores or
client-supplied victory flags. A submission replays every action through the
canonical engine, verifies the world matches the authored league source,
requires an earned protect/salvage ending, and derives score, health,
rescues, combat results, beacon and turns from the final replay state.

```bash
python -m skeleton.game.gameplay.ridge_rescue.league_cli open --output /tmp/ridge-board.json
python -m skeleton.game.gameplay.ridge_rescue.league_cli rank --board /tmp/ridge-board.json
python -m skeleton.game.gameplay.ridge_rescue.league_cli submit --board /tmp/ridge-board.json --expected-head HEAD --handle ridge-hero --run /tmp/protect-run.json --output /tmp/ridge-board-v2.json
python -m skeleton.game.gameplay.ridge_rescue.league_cli export --board /tmp/ridge-board-v2.json
```

Every submission requires an exact board revision and a unique, strictly
validated local handle. The board enforces a bounded 32-entry maximum,
deterministic tie-break ordering, no overwrite of previous saves and
replay-derived scores. A portable league export includes all submitted
source-bound runs and a verifiable ranking.

**Limits:** Handles are untrusted labels, not identity or anti-cheat
authentication. The SHA-256 digests detect changes but are not signatures.
This is an offline league only. No online fairness, device qualification,
production service deployment or release readiness is claimed.
