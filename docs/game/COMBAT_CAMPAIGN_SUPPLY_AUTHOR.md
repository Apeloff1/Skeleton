# Transactional supply authoring

The `combat-supply-author` CLI edits **original source** before a playthrough.
Its optimistic compare-and-swap input is the SHA-256 canonical source digest
from `skeleton.game.gameplay.flgb_gameplay_runtime.dig(normalize_supply(source))`.

```sh
python -m skeleton combat-supply-author demo
python -m skeleton combat-supply-author edit --source-json '<source JSON>' \
  --operations-json '[{"kind":"set-price","item":"medkit","value":6}]' \
  --expected-digest '<canonical source digest>'
python -m skeleton combat-supply-author verify --source-json '<original JSON>' \
  --receipt-json '<author receipt JSON>'
```

Supported operations: `set-price` for `medkit` or `ward` and
`set-reward` for an existing authored encounter. All operations are checked
and applied atomically to a copy, with no mutation on error. Duplicate or
unknown fields, invalid ranges, stale digests, no-op edits, and missing
encounters fail closed. After recompiling the canonical campaign, the editor
actually plays the changed source through the combat engine, returning a
source-bound save/replay preview and an integrity receipt.

Receipt verification re-executes the complete edit and combat preview from
the **original** source; a forged receipt digest alone is never accepted.
Digests are integrity checks, not authorization or signatures. Existing saves
are intentionally invalidated by source edits and require explicit restart.

Focused tests:
`python -m pytest skeleton/testing/test_combat_campaign_supply_author.py`.
