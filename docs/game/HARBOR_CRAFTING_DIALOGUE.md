# Lantern Quay merchant dialogue and earned dock permit

The authored merchant conversation board defines finite dialogue nodes, choice
consequences, trust requirements and prerequisite flags. A talk is legal only
while the player is adjacent to the **actual patrolling NPC**, not a claimed
position. It consumes one canonical world tick and advances NPC motion as a
wait. Delivery requires an earned \`dock_pass\` flag from a legal dialogue
choice. Declining the permit cannot be repaired by changing a score field.

The original authored fixture is
\`skeleton/game/gameplay/fixtures/harbor_lantern_quay_dialogue.json\`.
Actions may include \`{"op":"talk","node":"merchant_intro","choice":"permit"}\`
alongside normal movement, crafting, trading, delivery and ending choices.
The resulting portable report includes original player actions, canonical
gameplay replay, choice and flag history, NPC positions, trust, and a digest.

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli dialogue-run \
  --dialogue-board skeleton/game/gameplay/fixtures/harbor_lantern_quay_dialogue.json \
  --actions dialogue-actions.json --require-win > dialogue-report.json
python -m skeleton.game.gameplay.harbor_crafting_cli dialogue-verify \
  --dialogue-report dialogue-report.json --require-win
\`\`\`

\`dialogue-resume\` accepts an incomplete verified report and a CAS digest,
then replays the entire old and new action history. \`dialogue-author\` accepts
CAS leases for source and board, strictly bounded node/choice edits and an
optional prior report for actual replay preview. \`dialogue-verify-author\`
independently reconstructs the edit and preview.

Reports are integrity-checked, not signed or authenticated. The conversation
does not claim network multiplayer authority or device release qualification.
