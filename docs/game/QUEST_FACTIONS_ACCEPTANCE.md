# Faction quest end-to-end gameplay acceptance

`python -m skeleton quest-factions-accept demo` runs the original playable
Lantern Harbor quest through real NPC dialogue, authored travel, workshop
crafting, tactical combat, earned purchases and the faction-gated ending.
The output is a deterministic replay receipt with source and state digests,
earned standing, NPC decisions, crafted inventory, combat outcome, currency,
all intermediate checkpoint digests, and the portable save checksum.

`accept --source-json JSON --actions-json JSON [--ending-id ID]` accepts
only a fully finished, actually earned ending. Every action is applied
through the canonical quest and faction runtimes; every prefix is separately
replayed from the original source. The final portable bundle is exported
and imported before a receipt is emitted.

`verify --source-json JSON --receipt-json JSON` recomputes the complete
trace, checkpoints, earned resources, consequence standing and checksum.
A changed source, forged reward, skipped step, or altered ending fails closed.

Focused contract:
`python -m pytest skeleton/testing/test_quest_factions_acceptance.py -q`.

This is playable vertical evidence only. It is not a substitute for exact-head
CI, independent review, provenance, installation or device qualification.
