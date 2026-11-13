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

## Player-controlled tactical fights and JSON-line play

`python -m skeleton combat-expedition play --demo` emits one JSON object
per line. Each `turn` includes the next authored arena, available shop,
earned currency, hero health, inventory and stable state digest. Send one
JSON action per line on standard input. Invalid actions are rejected without
mutating the checkpoint, with at most three attempts per turn. EOF before a
terminal outcome fails closed. The terminal event contains the complete
replay-verifiable expedition save. `play --resume-json JSON` accepts only a
checkpoint whose normalized source digest matches the resumed expedition.

Besides automatic `{"kind":"fight"}`, players may submit
`{"kind":"fight_tactical","hero_actions":[...]}` with ordered canonical
arena commands (`move`, `attack`, `guard`, `rest`) for the authored hero.
Enemy turns use the deterministic offline arena policy. A script must supply
exactly the hero actions required to reach a terminal victory, defeat or draw;
missing, opponent-owned, illegal or surplus commands are rejected without
awarding currency or committing the encounter. Full opponent actions, source
identity, combat event receipts and parent save lineage are reconstructed on
verification and portable bundle import. This is a bounded text interaction,
not a graphical or network multiplayer implementation.

Focused tests: `python -m pytest skeleton/testing/test_arena_player_policy.py -q`.

### Interrupted play and trusted source recovery

Interactive play emits replay-verified `checkpoint` events every
`--checkpoint-every N` accepted actions (N=1..32, default 8), and
immediately before failing closed on EOF or three rejected commands.
The checkpoint contains the complete source-bound session and can be
passed back with `--resume-json`. For imported saves, provide a trusted
external manifest digest with `--source-digest`; a mismatched or malformed
64-character lowercase SHA-256 digest is rejected. The emitted digest alone
does not authenticate the game author or its license. Partial actions never
consume rewards, and all restored journal entries are re-executed before
accepting a new action.
