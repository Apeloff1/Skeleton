# Studio A — Integrated original-world playable and continuity handoff

This opt-in production plane joins five real source owners: canonical world
scenes, reviewed NPC dialogue, reviewed navigation, reviewed narrative
promises, and a private author context journal. It preserves the existing
`world-experience` format unchanged and introduces `world-integrated`
for users who need cross-plane closure and verified playable publication.

## End-user path

Author and persist a world through `world-canon`, a cast through
`world-cast`, a reviewed route through `world-route`, a promise through
`world-promises`, and an explicit private journal through `world-context`.
Use the respective browser editors to export typed changes, then apply and
review them with the operator CLIs. The unified compiler requires the exact
current source digests and context hash head:

```sh
python -m skeleton world-integrated --store PRIVATE compile \
  --world-id reef --world-digest WORLD_SHA256 --cast-digest CAST_SHA256 \
  --route-digest ROUTE_SHA256 --promises-digest PROMISES_SHA256 \
  --context-head CONTEXT_HEAD
python -m skeleton world-integrated --store PRIVATE verify --world-id reef
python -m skeleton world-integrated --store PRIVATE player \
  --world-id reef --slot PLAYER_SLOT
```

The HTML5 player includes original NPC dialogue, source-proven route guidance,
and live promise progress derived from the same choice trace. It displays
open narrative promises and refuses to show a successful ending if a required
promise remains open. Independently, compilation exhaustively proves that
all reachable endings satisfy required closure; a single happy-path witness
is not sufficient. Context journal private note text never enters the player
or handoff manifest; only typed kind/hash metadata is exported.

All five sources are read under one descriptor-held world lease. The HTML
and manifest are published before a receipt. Verification independently
recompiles every artifact from current sources and rejects stale digests,
tampering, partial publication, missing reviews, and changed context heads.
The player API uses a real persisted session and replays the actual choices.

This is **source-qualified handoff only**, not device qualification, signed
authenticity, or consumer release readiness. Run
`python -m pytest skeleton/testing/test_jeeves_world_integrated_experience.py -q`
at the exact head, followed by canonical regression and security gates.
