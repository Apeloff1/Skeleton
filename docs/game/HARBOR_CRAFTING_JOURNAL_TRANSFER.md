# Offline journal-to-game-package transfer

A Lantern Quay player may turn a complete or partial verified journal into
an original, portable playable package session. The export checks that the
journal's original source exactly matches the validated package world,
reconstructs the full gameplay action history and verifies the mission
report against the package's authored board.

    python -m scripts.game.harbor_crafting journal-package-play --journal journal.json --package game-package.json > transfer.json
    python -m scripts.game.harbor_crafting journal-verify-package-play --play transfer.json

The transfer is a JSON artifact containing the replay-verifiable journal
and packaged play session. It is not a signed installer. No victory or
mission points can be invented by editing an outer digest. A partial
campaign remains partial; --require-all rejects missing objectives.
The verifier replays both the journal and the packaged game. File storage
and transfer authenticity remain the caller's responsibility.
