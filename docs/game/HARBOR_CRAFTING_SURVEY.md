# Lantern Quay exploration and fog-of-war

The survey vertical reads the canonical original world source and a separate
authored board. A site is earned only when the actual player position reaches
the site during a legal replayed movement sequence. Revealed map cells are
calculated using a bounded Manhattan radius; visibility does not award a site.
Score, completion, site order and tick are reconstructed from game events.
No network, runtime code execution or externally supplied score is accepted.

The bundled original board is
\`skeleton/game/gameplay/fixtures/harbor_lantern_quay_survey.json\`.
Use the same world fixture as the existing Lantern Quay campaign.

Play and export:

\`\`\`sh
python -m skeleton.game.gameplay.harbor_crafting_cli survey-run \
  --survey-board skeleton/game/gameplay/fixtures/harbor_lantern_quay_survey.json \
  --actions actions.json --require-all > survey.json
python -m skeleton.game.gameplay.harbor_crafting_cli survey-verify \
  --survey-report survey.json --require-all
\`\`\`

For checkpoint continuation, supply a verified incomplete \`--survey-report\`,
additional \`--actions\` and the report's exact \`--expected-survey-digest\`.
A stale digest, invalid game action, completed game or overwritten history
fails closed. \`survey-hint\` proposes a bounded route to the nearest unvisited
site using the canonical NPC-aware route engine; \`survey-verify-hint\` replays
the proposed route and tie-breaking. The editor accepts CAS leases for both
source and board, validates every changed site, and can replay a previous
survey under the edited board without changing the original history.

Portable report digests detect accidental or adversarial alteration followed
by failed canonical replay, but they are not signatures and cannot establish
the identity of an author or trusted publisher. Canonical tests and required
final-head security/CI gates must pass before promotion or release.
