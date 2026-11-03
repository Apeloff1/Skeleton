# Lantern Quay — source-bound stealth patrol

This is an original offline patrol game using the canonical Lantern Quay
movement, collision, gathering, crafting, NPC schedule and dock delivery engine.
The patrol overlay adds two authored objectives, a moving breakwater watch,
bounded suspicion, one earned smoke charge, concealment and earned extraction.
A direct ending choice is rejected. The player must actually gather resources,
craft the delivery goods, deliver to the dock and collect both patrol records.

## Playable commands

Run from the repository root. Save a JSON list of actions as actions.json.
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
