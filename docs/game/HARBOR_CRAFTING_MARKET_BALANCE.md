# Lantern Quay economic authoring and playable balance proof

The economic authoring command uses the existing allowlisted, CAS-protected
source editor. It accepts merchant price, finite resource stock, recipe and
delivery quantity changes, but not arbitrary code, new assets or unbounded
inventory. Both the original and edited worlds must complete every authored
mission and earn a legal victory through the canonical solver.

Commands: market-balance --edits edits.json --expected-source-digest DIGEST;
verify-market-balance --comparison comparison.json. The comparison embeds
source revision provenance, original and edited gameplay/mission reports,
replay-derived market ledgers, terminal witnesses and before/after deltas.
The verifier recomputes every result, rejecting even correctly rehashed
fabricated outcomes. A revision that is valid JSON but makes the campaign
unplayable fails closed instead of being declared production-ready.

This is source-level economic balancing for a finite original game, not
real-money commerce, dynamic live pricing or device release certification.
