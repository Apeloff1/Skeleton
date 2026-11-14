# Cinder Ridge — playable field routebooks

Routebooks turn original rescue-world source into executable, editable player routes. The
source contains a bounded world and two authored tracks. Every action is checked
against the canonical engine, including NPC occupancy, finite inventory, crafting,
beacon requirements, storm damage and earned endings. A route is not declared
completed unless its final state is exactly the declared earned ending.

From the repository root:

```bash
python -m skeleton.game.gameplay.ridge_rescue.routebook_cli inspect
python -m skeleton.game.gameplay.ridge_rescue.routebook_cli run --track protect-route --output /tmp/cinder-protect.json
python -m skeleton.game.gameplay.ridge_rescue.routebook_cli verify-export --bundle /tmp/cinder-protect.json
python -m skeleton.game.gameplay.ridge_rescue.routebook_cli run --track salvage-route
```

`open` produces a session; `step --session FILE --expected-head SHA`
performs exactly one canonical action and returns the new session; `verify`
replays the whole route from source. `interactive` asks before every action.
`export` produces a portable source-bound game replay. Save and export
writes are create-only and use the descriptor-anchored IO boundary on
supported POSIX hosts. Unsupported platforms fail closed; Windows qualification
has not been performed.

`edit --operation JSON` applies an immutable CAS-guarded edit to a track
title, guard or action and **replays the edited track to its earned ending**
before publishing a source revision. `verify-edit` checks the edit evidence.
Edits cannot silently grant endings, add inventory or skip game turns.

This feature provides deterministic content integrity, not a cryptographic
signature or trusted player identity. It is not a claim of online anti-cheat,
multiplayer fairness, Windows installation or consumer release readiness.
