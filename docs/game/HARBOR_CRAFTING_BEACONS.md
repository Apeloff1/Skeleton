# Lantern Quay — Beacon Rescue

This original playable vertical is integrated with the canonical Lantern Quay world. The player must gather wood and ore, craft a lantern, repair and signal two authored beacons in prerequisite order, deliver the real dock cargo, and earn the signal rescue ending. Movement, collision, inventory, crafting, merchant patrol, delivery and consequence state are executed by the existing canonical engine rather than duplicated.

## Play, save and verify

Run from the repository root. Write the actions as a JSON list; use the sequence in the regression test winning_actions() for the original authored board.

    python -m skeleton.game.gameplay.harbor_crafting_beacon_cli run --source skeleton/game/gameplay/fixtures/harbor_lantern_quay.json --board skeleton/game/gameplay/fixtures/harbor_lantern_quay_beacons.json --actions actions.json --require-rescue > report.json
    python -m skeleton.game.gameplay.harbor_crafting_beacon_cli verify --report report.json --require-rescue

Use resume with --expected-digest from report_digest to continue a partial report. Use package and play to distribute an original, offline, source-bound board and record a portable replay. The editor supports CAS-protected power, position, prerequisites and turn-budget changes; previews are replayed rather than trusted. All outputs are canonical JSON. Invalid inputs fail closed with exit status 2. Digest checks prove internal integrity and replay consistency, not authenticated origin or device qualification.

Focused regression: pytest -q skeleton/testing/test_harbor_crafting_beacons.py. This documentation does not claim tests or required CI have passed.
