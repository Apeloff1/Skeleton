# Multi-ending original game campaign graph — 2026-10-13

**DX-109–DX-117** deliver an actual limited multi-ending game-campaign
authoring and review lane over the installed advanced genre interpreters.

* The author provides 2–8 original approved scene references, each with
  actual finite game actions, and 1–24 directed outcome links.
* Every scene is run against the **real installed reference game engine**
  and real current approved system and scene SHA. Campaign source contains
  all resulting immutable real game-state receipts, not invented outcomes.
* Branches are chosen deterministically from measured \`finished\`,
  \`failed\`, \`score_at_least\`, \`turns_at_most\`, or final \`always\`
  fallback. Priority is unambiguous. No dangling nodes, cycles,
  disconnected scenes or intermediate nodes without fallback.
* Two or more explicit original ending nodes are necessary. Ending labels
  can be good, neutral, evil, open, resolution or cliffhanger. This is a
  **bounded authored campaign program**, not proof that every potential
  player-input path yields one of the written endings.
* \`studio.campaign.plan\` compiles the campaign, executes its authored
  scene sessions and returns source SHA, real chosen ending, verified route
  and each bound source. \`studio.campaign.stage\` stages a fully regenerated
  source proposal for separate human review.
* The original \`GameWorkspace\` executes the entire real scene campaign
  again at **both** proposal and human source-commit boundaries.
  \`studio.campaign.verify\` replays the actual source stored in the
  user-selected game project and rejects source or story-choice drift.

This is the beginning of working multi-scene/multi-outcome game construction
for all installed game genres. It does not auto-create dialogue, licensed
art, arbitrary new player decisions or an untested native engine.

No test suite was run in the user-requested build-only workpass.
