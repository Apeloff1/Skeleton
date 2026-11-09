# Quest inventory provenance: earned gifts and crafting conservation

`python -m skeleton quest-inventory demo` replays the original Lantern
Harbor NPC/crafting/combat quest and produces a bounded source-bound ledger.
Every NPC gift and crafting input/output is reconciled against the canonical
quest transition, action receipt, save ancestry and portable export checksum.

`audit --session-json JSON` returns per-action inventory changes, exact
credits/debits and final holdings. `prove --session-json JSON --item-id reed`
explains precisely when a resource was earned and consumed. Unknown items
report zero credits, zero debits and no history; they never create stock.

`verify --session-json JSON --audit-json JSON` recomputes the entire ledger
from source and actions and rejects forged balances, reward claims, receipts
or saved state. The report checksum detects corruption but is not an author
signature or an authorization token. No filesystem or network writes occur.

Focused validation:

```sh
python -m pytest skeleton/testing/test_expedition_quest_inventory.py -q
python -m skeleton quest-inventory demo
```

This is gameplay conservation and replay evidence, not a device qualification,
security approval or substitute for mandatory exact-head CI.
