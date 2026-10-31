# Original offline tactical expedition

\`python -m skeleton combat-expedition demo\` executes two original
Lantern Harbor arenas through the canonical tactical arena runtime,
then returns a source-bound, replay-verifiable save. This is an offline
gameplay system; it does not claim native rendering, installation,
cryptographic authorship, or provider-driven NPC intelligence.

## Real player decisions

A source includes one stable hero, up to six bounded arenas and up to
twelve finite shop items. Each arena carries its own collision map,
enemy roster, turn limit and earned victory reward. The hero carries
remaining health into the next arena; defeated or drawn fights terminate
the expedition and award no reward for that encounter. Between fights,
players may buy finite-stock items with **earned** currency and consume
them to restore bounded health. Inventory is capped at sixteen items,
and purchases cannot exceed authored stock or balance.

\`simulate --source-json JSON --actions-json JSON\` accepts a sequence of
\`{"kind":"fight"}\`, \`{"kind":"buy","item_id":"tide_tonic"}\`,
and \`{"kind":"use","item_id":"tide_tonic"}\`. Checkpoints from
\`simulate\` or \`resume\` can be passed to
\`verify --session-json JSON\`, or resumed using
\`resume --session-json JSON --actions-json JSON\`.

## Trust and recovery

Every action is replayed from the normalized authored source and the
entire snapshot, source digest, action receipts, nested combat saves,
earned rewards and parent-save lineage are compared. Saves are checksums,
not trusted signatures. Untrusted authored input cannot inject scripts,
network calls, currencies, unearned items, or arbitrary file paths.
Source changes invalidate checkpoint reuse; there is no implicit
migration across incompatible authored arena revisions.

Focused tests: \`python -m pytest
skeleton/testing/test_arena_expedition.py -q\`. Required architecture,
security, exact-head CI and platform qualification are separate gates.
