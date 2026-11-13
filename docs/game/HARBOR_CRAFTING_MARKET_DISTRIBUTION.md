# Portable original game distribution with market custody

Build a playable original game distribution using market-distribution.
Verify with verify-market-distribution --package distribution.json.
Play with market-distribution-play --package distribution.json --actions actions.json.
Verify the player's replay with verify-market-distribution-play --play play.json.

The distribution contains only validated JSON sources, the canonical game
package, its original authored mission board, a replay-proven sample victory
and a market ledger with a bounded manifest. The player's game actions run
through the same canonical game engine, including collisions, crafting costs,
NPC trading, finite resources, save replay and earned ending checks.

Rehashed manifests, forged currency, changed source identity, impossible
actions and altered market totals fail closed. This is an offline portable
JSON game package, not executable delivery, app-store approval or consumer
device qualification.
