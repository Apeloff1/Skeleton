# Scene market route search and player board

The market route search is a **bounded gameplay witness generator**, not a
speculative inventory planner. It searches authored tile movement, pickups,
exits, finite-stock purchases, crafting stations and one-shot NPC deliveries.
Every successful route is replayed by the canonical market reducer from the
exact checkpoint, then checked against the earned-victory condition.

Run `python -m skeleton scene-market-route demo --max-nodes 4096 --max-depth 40`
to obtain an exact-source replay witness. Use `solve --session-json JSON`
for a checkpoint and `verify --session-json JSON --report-json JSON` to
recompute the route and reject fabricated witnesses.

Run `python -m skeleton scene-market-board demo --hint-nodes 4096
--hint-depth 40` for a read-only player view of inventory, remaining NPC
deliveries, position, legal action candidates and the first replay-proven
winning move. `inspect --session-json JSON` operates on any verified save;
`verify --session-json JSON --board-json JSON` checks the complete report.

## Safety and determinism

* All actions pass through the existing market and tile reducers. There is no
  direct balance mutation, free currency, inventory grant or teleport.
* Checkpoint source/state/save digests are bound to the witness. Reports have
  deterministic checksums, **not cryptographic signatures**.
* Search nodes are bounded to 1–4096 and depth to 0–64. A node/depth cap or
  failure to find a winning path returns **inconclusive**, never a false claim
  of impossibility or playability. The route is evidence for one exact source.
* Recomputed search verifies a route report even if an attacker recomputes
  its unkeyed checksum. A verified board is a read-only projection, not an
  authority for spendable funds.
* Failed moves, invalid purchases, exhaustion and malformed checkpoints are
  rejected without modifying the input save. Portable exports use the existing
  canonical `scene-market export` and `scene-market import` operations.
* The route finder does not qualify device installers, game rights, or release
  readiness; focused tests and exact-head CI are required before promotion.
