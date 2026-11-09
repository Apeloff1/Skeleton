# Lantern Quay — Playable Convoy Escort

Studio B's convoy vertical is an original offline side campaign sharing the canonical Lantern Quay world, finite gathering, crafting, collision and merchant patrol. The convoy moves only through authored traversable adjacent waypoints. Player escort actions advance one waypoint when the player is nearby; authored ambushes interrupt the route until defeated. Every strike spends one earned craftable lantern charge from the real canonical inventory. Guards prevent one tick of damage but do not defeat enemies. Hull loss, tactical rewards and the final dock delivery are derived from the complete action replay.

## End-to-end commands

Run from repository root using `python -m scripts.game.harbor_crafting`. The default source is `skeleton/game/gameplay/fixtures/harbor_lantern_quay.json` and the default convoy board is `skeleton/game/gameplay/fixtures/harbor_lantern_quay_convoy.json`.

Use `convoy-live` for a bounded interactive terminal with move, gather, craft, escort, strike, guard, status and quit. Standard output is the portable JSON save; prompts and the map go to standard error. Use `convoy-run --actions actions.json --require-all` for scripted deterministic play. Use `convoy-verify --convoy-report save.json --require-all` to reconstruct every canonical world tick and escort transition. Use `convoy-status --convoy-report save.json` for current health, ambush, waypoint and earned bounty.

A partial save can be resumed with `convoy-resume --convoy-report partial.json --actions continuation.json --expected-convoy-digest <sha256>`. The expected digest is an optimistic concurrency lease; stale, terminal and rewritten histories fail closed. `convoy-author --convoy-edits edits.json --expected-convoy-board-digest <sha256> [--convoy-report previous.json]` performs a transactional board edit with an optional replayed gameplay preview; `convoy-verify-author --convoy-revision revision.json` independently rebuilds that revision.

## Source contract and failure behavior

The convoy board binds to a canonical source ID, a finite traversable route ending at the authored dock, a craftable weapon, bounded hull/turns and unique timed encounters. Enemy strength, earned reward and convoy position are never taken from user-provided completion claims. An encounter can destroy the convoy, producing a verifiable defeated save; required victory rejects it. The convoy cannot overlap the player or the merchant route. Every export contains the original authored world, the authored convoy board, canonical replay bundle, tactical action history, per-event hash chain and replay-derived terminal state. SHA-256 detects accidental corruption but is not a signature or authenticated provenance.

## Focused acceptance

`pytest -q skeleton/testing/test_harbor_crafting_convoy.py` exercises a fully crafted/escorted victory, finite weapon charges, tactical defeat, guarding, collisions, board validation, stale CAS, adversarial resealed forgeries, transactional editor preview, CLI run/verify/resume and interactive terminal recovery. Exact-head CI, review and consumer/device qualification remain mandatory before promotion or release.
