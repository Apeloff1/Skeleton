# Player Combat Campaign — Deterministic Timeline and Delivery

`python -m skeleton combat-campaign-timeline demo` runs an original
player-controlled combat campaign and emits a portable bundle containing its
canonical save plus a replay-derived tactical timeline.

`audit --session-json '<save>'` reconstructs each hero action from the
original campaign source, including the canonical opponent response, carried
health, encounter completion and reward currency. Each row carries the
canonical combat receipt, before/after state digests, earned reward delta,
hero health delta, current encounter and ending. The audit enforces that
currency increments equal only the rewards in completed canonical encounters.

`verify --session-json '<save>' --report-json '<timeline>'` recomputes every
claim; a recomputed checksum cannot validate fabricated health or rewards.
`export --session-json '<save>'` and `import --bundle-json '<bundle>'`
round-trip the playable game and timeline without network access.
`resume --bundle-json '<bundle>' --actions-json '<hero actions>'`
continues the real campaign and returns a new export with its updated
timeline; it never mutates the original checkpoint.

All JSON is bounded, replayed and validated with strict duplicate-key
handling. Reports provide offline functional provenance only, not a
cryptographic signature, trusted authorship, device qualification or release
certification. The canonical combat reducer remains the sole authority for
damage, turns, opponent policy, victory and rewards.

Focused tests:
`python -m pytest skeleton/testing/test_combat_campaign_timeline.py -q`.
