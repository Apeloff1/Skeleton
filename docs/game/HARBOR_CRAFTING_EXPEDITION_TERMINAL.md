## Interactive expedition terminal

The integrated game can be played directly, without preparing an action JSON
file. \`expedition-live\` accepts the three original authored boards, reads
bounded terminal commands and prints a fog-of-war map, verified status, action
acceptance/rejection and portable JSON saves. Valid commands include movement
directions, gather, craft, trade, talk, deliver, choose, wait, map, status, save,
help and quit. NPC reachability, weather exhaustion, wall collisions, survey
site visits and delivery permits are enforced on every attempted action.

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli expedition-live \
  --survey-board survey.json --weather-board weather.json \
  --dialogue-board dialogue.json
\`\`\`

For resumed interactive play, provide \`--expedition previous.json\` and its
exact \`--expected-expedition-digest\` alongside the same three source boards.
An invalid command is rejected without changing the current checkpoint.
A successful victory emits \`EXPEDITION_WIN\` and \`EXPEDITION_SAVE\`, which
can be independently verified using \`expedition-verify\`. A clean quit or EOF
emits \`EXPEDITION_CHECKPOINT\`. The UI has a finite command budget and does
not execute source-authored scripts.
