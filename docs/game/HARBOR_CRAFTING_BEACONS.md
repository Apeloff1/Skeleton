# Lantern Quay — Beacon Rescue

This original playable vertical is integrated with the canonical Lantern Quay world. The player must gather wood and ore, craft a lantern, repair and signal two authored beacons in prerequisite order, deliver the real dock cargo, and earn the signal rescue ending. Movement, collision, inventory, crafting, merchant patrol, delivery and consequence state are executed by the existing canonical engine rather than duplicated.

## Play, save and verify

Run from the repository root. Write the actions as a JSON list; use the sequence in the regression test winning_actions() for the original authored board.

    python -m skeleton.game.gameplay.harbor_crafting_beacon_cli run --source skeleton/game/gameplay/fixtures/harbor_lantern_quay.json --board skeleton/game/gameplay/fixtures/harbor_lantern_quay_beacons.json --actions actions.json --require-rescue > report.json
    python -m skeleton.game.gameplay.harbor_crafting_beacon_cli verify --report report.json --require-rescue

Use resume with --expected-digest from report_digest to continue a partial report. Use package and play to distribute an original, offline, source-bound board and record a portable replay. The editor supports CAS-protected power, position, prerequisites and turn-budget changes; previews are replayed rather than trusted. All outputs are canonical JSON. Invalid inputs fail closed with exit status 2. Digest checks prove internal integrity and replay consistency, not authenticated origin or device qualification.

Focused regression: pytest -q skeleton/testing/test_harbor_crafting_beacons.py. This documentation does not claim tests or required CI have passed.

Interactive terminal: `skeleton-harbor-beacon-rescue live --source <world.json> --board <beacons.json> --require-rescue` (or the equivalent Python module invocation). Commands: move north/south/east/west, gather, craft <recipe>, trade <item>, repair <beacon>, signal <beacon>, deliver, rescue, wait, quit. Rejected commands do not advance state; a partial report is emitted as canonical JSON for later CAS resume. The installed entry point is declared in pyproject.toml.

The optional `hint` command returns only legal, replay-executed next actions and the resulting report digests. `verify-hint --report <report.json> --guidance <guidance.json>` reconstructs each action to reject forged or stale hints. Interactive `hint` prints the same legal actions without consuming a world tick.

A completed portable play can produce a compact deterministic original-game acceptance certificate: `accept --play <play.json>`, followed by `verify-accept --play <play.json> --acceptance <certificate.json>`. This proof binds the actual replayed dock delivery, ordered signals, earned ending, canonical event tip and score to the exact package and play digests. It is not a cryptographic signature, independent platform test, or release approval.

Append-only CAS save journals support `journal-init`, `journal-append --expected-digest <tip>`, `journal-verify`, `journal-at --index N`, and `journal-fork --index N`. Every checkpoint is replayed against the original world and beacon board, including real inventory and NPC collision, before it can be resumed or exported. A fork preserves ancestry up to the selected checkpoint and cannot silently rewrite the original. Limits: 32 checkpoints, 80 authored ticks in the original board, 512 KiB journal. Journals are replay-verified integrity records, not signatures or multi-process durable locks.

Five original chained beacon quests bind to the exact beacon board and derive earned scores only from replay-verified repair, signal, delivery and rescue actions. Commands: `quest-run --report <rescue.json> --quest-board <quests.json> --require-rescue`, `quest-verify --quest-report <report.json>`, `quest-author --report <rescue.json> --quest-board <quests.json> --edits <edits.json> --expected-digest <board_digest>`, `quest-verify-author --quest-revision <revision.json>`. The quest layer does not mutate canonical inventory or invent progress.

Authored high-water tide hazards are tied to the canonical game clock and movement. The original crossing at tiles [3,3] and [4,3] drains stamina during high phases; shelter rest is only legal at the authored [1,3] refuge. Drowning is terminal and cannot be reclassified as rescue. Commands: `tide-run`, `tide-verify`, `tide-resume --expected-digest`, `tide-author`, and `tide-verify-author`. Each result includes the actual replayed beacon rescue and a deterministic tide event chain.
