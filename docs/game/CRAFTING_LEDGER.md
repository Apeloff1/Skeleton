# Source-bound crafting ledger: earned item provenance

The canonical offline crafting engine owns every transaction. The new
`ledger` and `verify-ledger` commands on the installed
`skeleton-game-craft` CLI provide a replay-derived account of exactly which
ingredients were consumed, which products were made, what currency was spent,
and which progression flags were unlocked.

```bash
skeleton-game-craft ledger --plan plan.json --save session.json > ledger.json
skeleton-game-craft verify-ledger --plan plan.json --report ledger.json
```

The ledger includes the original canonical save, source digest, before/after
state digests for every action, ordered receipt, per-recipe input/output
stacks, inventory deltas and aggregate consumed/produced items. Batch
multipliers are applied to both ingredients and fees. It never treats a
submitted balance as authority: all events are replayed from the exact
source-bound plan. A forged save, action, item balance or currency amount
is rejected even when the attacker recomputes the outer checksum.

Reports and CLI inputs are bounded to 1 MiB. No filesystem paths are taken
from authored content; the existing CLI retains no-follow regular-file
reads, no-clobber save creation and strict duplicate/nonfinite JSON parsing.
All values are game items and game currency, not external payment or
financial-accounting records. Hashes provide consistency, not signatures
or ownership proof.

```bash
python -m pytest -q skeleton/testing/test_crafting_ledger.py
```

Acceptance includes exact item/currency conservation, batch scaling,
source binding, forged receipt rejection, CLI export/import, missing
arguments and no-op histories. Exact-head CI and consumer qualification
remain separate release holds.
