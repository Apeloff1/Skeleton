# Lantern Quay expedition: integrated playable vertical

The expedition is a single source-bound original game, not a collection of
unrelated score reports. It combines **real movement, collision, gathering,
crafting and delivery** with replay-verified fog-of-war survey sites,
stamina-consuming storms/hazards and patrolling merchant dialogue that must
grant an earned dock permit. All three systems share the **same canonical
world action/event chain**. Dialogue actions consume canonical world ticks,
weather may reject otherwise legal actions due to exhaustion, and surveys
award points only when the player reaches real positions.

Authoring inputs are the original world and the three finite board fixtures
in \`skeleton/game/gameplay/fixtures/\` (survey, weather and dialogue).
The expedition package binds these authored sources and can be played offline
to produce a portable replay-verifiable result.

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli expedition-build \
  --survey-board survey.json --weather-board weather.json \
  --dialogue-board dialogue.json > expedition-package.json
python -m skeleton.game.gameplay.harbor_crafting_cli expedition-play \
  --expedition-package expedition-package.json --actions actions.json \
  --require-all > expedition-play.json
python -m skeleton.game.gameplay.harbor_crafting_cli expedition-verify-play \
  --expedition-play expedition-play.json --require-all
\`\`\`

\`expedition-run\` and \`expedition-resume\` work directly with the three
boards. Resume requires an exact CAS lease and verifies every prior event
prefix before appending. \`expedition-status\` reports the remaining required
survey sites, earned NPC permit, current energy, upcoming weather and ending.
\`expedition-verify\` independently rebuilds all three gameplay planes.

No scripts from authored JSON are executed. Bounds apply to actions, map
size, NPC routes, dialogue nodes, weather phases, survey sites, report size
and package size. Digest custody detects replay inconsistency but is not
cryptographic publisher authentication. Focused tests, exact-head CI, device
qualification and security review remain required before release.
