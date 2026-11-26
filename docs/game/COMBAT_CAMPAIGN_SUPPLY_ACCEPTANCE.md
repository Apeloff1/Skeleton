# Original combat supply: end-to-end playable acceptance

`python -m skeleton combat-supply-accept demo` executes the entire original
Lantern Harbor supply vertical without external services:

1. Canonical original source and optimistic transactional source editing.
2. Actual deterministic turn-combat encounter and earned currency.
3. Verified checkpoint restore, purchase of an affordable medkit and healing.
4. Second canonical encounter, winning ending and deterministic save lineage.
5. JSON round-trip replay, portable package export and import verification.
6. Bounded route solver returning a real winning command witness.
7. Compact reproducible acceptance receipt with exact state/source digests.

`python -m skeleton combat-supply-accept verify --receipt-json '<JSON>'`
re-executes all seven stages and rejects rehashed, tampered evidence.

This is an offline **functional acceptance fixture**, not an external
authorization signature, installation qualification, hardware benchmark,
rights certification, full test-suite pass or production release approval.

Focused tests:
`python -m pytest skeleton/testing/test_combat_campaign_supply_acceptance.py`.
