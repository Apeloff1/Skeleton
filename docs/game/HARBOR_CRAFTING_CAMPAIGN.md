# Lantern Quay: playable crafting and delivery campaign

This is an original, bounded terminal game production vertical. The checked-in
JSON source defines the map, player start, resource deposits, merchant patrol,
crafting recipes, cargo manifest and tick limit. No remote assets, executable
scripts, downloaded ROMs or unlicensed game material are required.

## Play and export

Run the authored victory demonstration:

    python -m scripts.game.harbor_crafting demo --require-win > lantern-save.json

Verify the resulting portable save by independently re-running the complete
event chain against the included authored source:

    python -m scripts.game.harbor_crafting verify --bundle lantern-save.json --require-win

Author your own JSON action array and play it:

    python -m scripts.game.harbor_crafting play --actions my-actions.json > my-save.json

Use the game module directly if the scripts package is unavailable:

    python -m skeleton.game.gameplay.harbor_crafting_cli demo --require-win

The player begins at (1,1). Move by north/south/east/west, gather finite
resource deposits by standing on them, craft a lantern and ration, reach a
tile adjacent to the dock at (6,3), deliver cargo and choose to signal the
beacon or shelter the town. The merchant follows a deterministic two-tile
patrol and sells limited food for coins when adjacent. Player/NPC collisions,
invalid recipes, depleted deposits, insufficient cargo, unearned endings and
inventory overflow fail closed.

## Source, state, replay, export

The source contract is skeleton.game.harbor.v1. The exported bundle contract
is skeleton.game.harbor.bundle.v1. A bundle includes the source and its digest,
each accepted player action, the previous-event digest, before/after state
digests, the terminal state and a canonical outer digest. Verification does
not trust the stored state: it reconstructs every tick, NPC movement,
inventory change, transaction, delivery and choice, then compares the exact
event chain and terminal state. A partial save is valid for resume/audit but
does not satisfy --require-win.

Canonical JSON rejects duplicate fields, NaN and Infinity. Input and output
byte limits, world dimensions, resource and recipe counts, per-item quantities,
inventory totals and tick counts are enforced. The CLI prints no success
artifact when a command fails; its error exit code is 2. The portable bundle
is integrity-checked, **not cryptographically signed or encrypted**. Anyone
who can rewrite both the authored source and the complete replay can create
a different self-consistent bundle. Do not use this as an adversarial
publisher identity or entitlement mechanism.

## Acceptance

    pytest -q skeleton/testing/test_harbor_crafting_campaign.py

The suite covers authored source validation, a real won game, an alternative
ending, deterministic bit-identical replay, portable save verification,
resource depletion, merchant trades, movement/NPC collision, illegal actions,
source/event/state tampering, oversized input and CLI success/failure paths.

No graphical frontend, installed-device acceptance, publisher signature,
multiplayer authority or consumer release qualification is claimed. This
is a reviewable independent gameplay vertical pending exact-head CI.

## Installed package integration

The project declares the `skeleton-harbor-crafting` console entry point and
ships the authored JSON fixture as package data. After installation, use
`skeleton-harbor-crafting demo --require-win` or the module invocation above.
A source checkout remains usable without installing a new dependency.
