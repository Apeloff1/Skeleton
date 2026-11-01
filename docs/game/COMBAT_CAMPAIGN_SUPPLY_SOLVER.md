# Replay-verifiable supply route search

`python -m skeleton combat-supply-solve demo --min-hp 11` searches for a
surviving original Lantern Harbor combat route. The planner only expands
legal, source-bound `fight`, `buy` and `use` actions. Every battle is
resolved by the canonical deterministic turn-combat engine. It cannot grant
currency, health or inventory from a fabricated save.

```sh
python -m skeleton combat-supply-solve solve --source-json '<authored source>' \
  --min-hp 11 --max-states 96 --max-depth 12
python -m skeleton combat-supply-solve verify --source-json '<authored source>' \
  --receipt-json '<search result>'
```

Search is breadth-first with a deterministic action order and strategic-state
deduplication. A found route includes every command and a full verified
terminal checkpoint. Search budgets are strictly bounded (1..256 expanded
states and 1..16 actions). When the budget or depth is exhausted the status
is `inconclusive`, **not** `unreachable`. An exhausted complete frontier
without a winning state may be reported `unreachable`.

Verification recomputes the entire search and combat replay from the
original authored source; a rehashed or tampered route is rejected.
The result digest is an integrity checksum, not a signature, attestation
or authority to bypass release/security gates.

Focused tests:
`python -m pytest skeleton/testing/test_combat_campaign_supply_solver.py`.
