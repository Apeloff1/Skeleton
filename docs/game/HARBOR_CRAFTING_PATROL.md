# Lantern Quay — source-bound stealth patrol

This is an original offline patrol game using the canonical Lantern Quay
movement, collision, gathering, crafting, NPC schedule and dock delivery engine.
The patrol overlay adds two authored objectives, a moving breakwater watch,
bounded suspicion, one earned smoke charge, concealment and earned extraction.
A direct ending choice is rejected. The player must actually gather resources,
craft the delivery goods, deliver to the dock and collect both patrol records.

## Playable commands

Run from the repository root. A fully replayable authored first-playable action list is included at `skeleton/game/gameplay/fixtures/harbor_lantern_quay_patrol_demo.json`.
For live interactive keyboard gameplay, use `python -m scripts.game.harbor_patrol live`.
Save a JSON list of actions as actions.json.
For the authored first-playable sequence, use the 18 canonical demo actions
from \`harbor_crafting.demo_actions()\`, insert
\`{"op":"collect","objective":"tide_registry"}\` after the second wood
gather, insert \`{"op":"collect","objective":"dock_manifest"}\` before
delivery, and replace the final \`choose\` with \`{"op":"extract"}\`.

\`\`\`sh
python -m scripts.game.harbor_patrol run --actions actions.json --require-complete > report.json
python -m scripts.game.harbor_patrol verify --report report.json --require-complete
python -m scripts.game.harbor_patrol package --actions actions.json > package.json
python -m scripts.game.harbor_patrol verify-package --package package.json
python -m scripts.game.harbor_patrol play --package package.json --actions actions.json --require-complete > play.json
python -m scripts.game.harbor_patrol verify-play --play play.json --require-complete
\`\`\`

To resume a partial report, supply the exact prior report digest as
\`--expected-digest\` and an additional action list. Stale leases, terminal
resumption and impossible transitions fail closed. To edit the board, supply
a JSON list of \`set-alert-limit\`, \`set-guard-sight\` or
\`set-objective-reward\` operations and the exact current board digest.
The authoring revision can be replay-verified with \`verify-author\`.

## Boundaries and qualification

Every export embeds the authored source and event chain. Import reconstructs
the canonical game state and patrol events, not merely an outer checksum.
SHA-256 digests provide integrity and deterministic replay, **not signer
authentication or trusted provenance**. Limits apply to actions, turns,
source, boards, reports and packages. No network or executable payloads.
This is a terminal first playable, not a qualified graphical/device build.
Focused tests and required exact-head CI must pass before promotion or release.

## Earned consequences

The source-bound debrief board offers two distinct outcomes after extraction:
`publish` restores the breakwater watch with higher credits; `protect`
secures families with higher reputation. Both require replayed objectives,
score and alert thresholds. No client may invent credits or bypass the earned
ending by editing the outer digest.

```sh
python -m scripts.game.harbor_patrol choices --report report.json
python -m scripts.game.harbor_patrol debrief --report report.json --choice protect > debrief.json
python -m scripts.game.harbor_patrol verify-debrief --debrief debrief.json
```

## Deterministic legal-action hints

`python -m scripts.game.harbor_patrol hint --report report.json`
replays every bounded candidate against the exact report history. It returns
legal moves, guard forecasts, next alert/score, per-result digest and a
conservative suggested action. Hints are advisory, never proof of victory;
any chosen action still passes through the canonical transition and CAS replay.

## Authored mission event chain

Five source-bound quests award points only after replayed objective collection,
crafting, dock delivery and extraction, in prerequisite order. The authored
quest board binds to the exact patrol board digest. An outer hash alone never
certifies an invented quest reward.

```sh
python -m scripts.game.harbor_patrol quest-run --report report.json --require-all > quests.json
python -m scripts.game.harbor_patrol quest-verify --quest-ledger quests.json --require-all
```

Patrol quest rewards and prerequisites can be edited transactionally with
`quest-author --report report.json --quest-edits edits.json --expected-digest SHA256`.
Every accepted edit produces before/after replayed quest ledgers; use
`quest-verify-author --quest-revision revision.json` to verify custody.
