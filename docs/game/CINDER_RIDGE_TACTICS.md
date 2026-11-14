# Cinder Ridge field tactics — bounded, playable, replayable

This original field-tactics assistant ranks **real legal actions** from the
canonical Cinder Ridge rescue engine. It never grants resources, teleports
civilians, changes NPC positions, skips combat or fabricates an ending.

The player can inspect the source policy, preview every legal next action,
commit one action with a CAS journal revision, or run a bounded local autoplay
that publishes an independently replayable export. The policy specifies the
desired protect/salvage ending, risk tolerance, crafting preference and maximum
turns. The actual engine determines success, defeat, resource exhaustion and
NPC reactions. Static route distances are advisory; dynamic enemy motion can
invalidate them. No winning guarantee is claimed.

```bash
python -m skeleton.game.gameplay.ridge_rescue.tactics_cli inspect
python -m skeleton.game.gameplay.ridge_rescue.tactics_cli suggest
python -m skeleton.game.gameplay.ridge_rescue.tactics_cli open --output /tmp/ridge-journal.json
python -m skeleton.game.gameplay.ridge_rescue.tactics_cli autoplay --output /tmp/ridge-tactics.json
```

To resume, use `--journal PATH` with `suggest`, `step --expected-head
SHA`, `verify`, `export` or `autoplay`. An edit to risk, objective,
crafting preference or step budget requires the current policy SHA-256 and
produces an immutable source revision with a replayed initial preview.

Source and journals have strict size ceilings. The canonical journal
reconstructs every state transition before advice is returned. Outputs use
create-only descriptor-anchored writes on supported POSIX hosts; unsupported
platforms fail closed. Digests detect accidental or unauthenticated
modification but do not prove player identity. Online anti-cheat, Windows
device operation and release certification are not claimed.
