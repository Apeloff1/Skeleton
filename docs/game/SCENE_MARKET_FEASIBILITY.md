# Scene market authoring feasibility

`python -m skeleton scene-market feasibility --source-json '<source>'`
runs a deterministic bounded over-approximation of the authored economy.

The analyzer computes the maximum collectible coin budget from canonical
pickups, flags offers that individually exceed that budget, and computes a
monotonic fixed point of goods obtainable from affordable offers and authored
recipes. It reports blocked recipes and deliveries whose goods have no
possible production chain. If a required delivery is among them, the source
is `definitely_unreachable`.

`potentially_reachable_unproven` **does not mean playable**. Shared money,
stock limits, map paths, turn budgets and conflicting ingredient consumption
can still make a seemingly feasible campaign unwinnable. Only full canonical
gameplay and replay acceptance can establish a winning witness.

No source or save is modified. Unknown schema, unbound pickups, malformed
offers, invalid quantities and oversized inputs fail closed. The report is
source-digest-bound and checksummed, but not cryptographically signed.

Focused validation: `python -m pytest
skeleton/testing/test_scene_market_feasibility.py
skeleton/testing/test_scene_market_acceptance.py`.
