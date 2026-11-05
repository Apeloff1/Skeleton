# Original expedition quest and event production

The quest engine awards objectives only from replayed canonical actions and
the integrated expedition's actual survey visits, merchant dialogue flags,
NPC interactions and weather energy. Each authored quest has a finite trigger,
source-bound target, prerequisite flags/sites/tokens, minimum energy, reward,
required flag and unique grant token. Dependencies must point to previously
authored tokens; cycles and invented source identifiers fail closed.

The original authored board is
\`skeleton/game/gameplay/fixtures/harbor_lantern_quay_quest_events.json\`.
Its five required objectives form a playable chain from gathering wood and
crafting a lantern through obtaining the merchant's dock permit, delivering
supplies and choosing the earned beacon ending.

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli quest-run \
  --expedition expedition.json --quest-board quest-board.json \
  --require-all > quest-report.json
python -m skeleton.game.gameplay.harbor_crafting_cli quest-verify \
  --quest-report quest-report.json --require-all
\`\`\`

\`quest-status\` lists remaining required objectives. \`quest-author\`
performs CAS-protected source-bound rule edits and optional replayed preview
without modifying the original expedition save. \`quest-verify-author\`
independently reconstructs the edited board and preview. The portable quest
report includes the full verified expedition and a chained event award log.
Its digest is integrity evidence, not a trusted author signature.
