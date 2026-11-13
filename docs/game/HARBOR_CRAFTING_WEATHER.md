# Lantern Quay weather, stamina and hazard production

Weather is authored as a strictly ordered, finite phase schedule. Each legal
player move executes the canonical movement/collision/NPC engine before its
weather cost and hazard consequences are committed. Rain, storm and night
change energy consumption. Rest actions restore bounded energy; exhaustion
rejects an action rather than granting free movement or negative stamina.

The original authored fixture is
\`skeleton/game/gameplay/fixtures/harbor_lantern_quay_weather.json\`.
The weather report contains canonical source and action replay, a separately
chained energy/hazard timeline, final energy, weather statistics and digest.
A portable verifier rebuilds all values from the source and actions.

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli weather-run \
  --weather-board skeleton/game/gameplay/fixtures/harbor_lantern_quay_weather.json \
  --actions actions.json --require-win > weather-report.json
python -m skeleton.game.gameplay.harbor_crafting_cli weather-verify \
  --weather-report weather-report.json --require-win
python -m skeleton.game.gameplay.harbor_crafting_cli weather-forecast \
  --weather-report weather-report.json > forecast.json
\`\`\`

For incomplete games, \`weather-resume\` requires the exact report digest
and additional actions; history is replayed and compared before publication.
The bounded \`weather-forecast\` returns a replay-verifiable 1–64 tick timeline.
The CAS editor supports strict weather-phase, hazard and energy-setting edits,
plus optional gameplay preview. Editing a board never rewrites a prior save.
If an edited board would make previous actions illegal, preview fails closed.

This system is deterministic and offline. A digest is not a publisher signature.
Device performance, focused tests and final-head CI are independent release holds.
