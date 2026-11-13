# Lantern Quay: playable salvage and rescue

The original, offline salvage mission extends the canonical harbor world without
forking movement, crafting, NPC collisions, economy or earned choice rules.

## Production path

Authored source `harbor_lantern_quay.json` and salvage board
`harbor_lantern_quay_salvage.json` are independently validated. All movement,
gathering, crafting, trade and dock delivery go through the canonical engine.
`salvage`, `offload`, `patch` and `rescue` consume canonical wait/choice
ticks. A salvage site must be occupied by the player, cargo must fit the authored
capacity, and a high-tide salvage can damage the hull. Patching requires a
canonical craftable tool and sacrifices recovered cargo. The ending requires
every site to be offloaded, canonical cargo delivery, and an earned signal
choice at the dock. Direct `choose` is rejected.

The deterministic event chain records each action, overlay state hashes,
canonical world hashes and previous-event custody. Replay rebuilds both the
canonical bundle and salvage overlay; a checksum alone never certifies play.
CAS continuation rejects stale digest leases and terminal runs. Source revisions
validate after every edit and optionally replay existing actions to refuse
edits that invalidate a live session.

## User entrypoint

Run `python -m scripts.game.harbor_salvage --help` for all commands. Input and
output are bounded JSON; output goes to stdout for deliberate redirection.
No network, arbitrary code, pickle or external asset execution is used.

- `run --actions actions.json --require-complete` builds portable replay.
- `verify --report report.json --require-complete` independently replays it.
- `resume --report report.json --actions continuation.json --expected-digest SHA`
  continues a verified, nonterminal save with optimistic concurrency.
- `live` runs the bounded interactive terminal; invalid actions do not mutate.
- `hint --report report.json` gives NPC-aware, replay-tested legal actions.
- `contract-run --report report.json --require-all` awards only replay-earned
  original salvage mission objectives and consequences.
- `author --edits edits.json --expected-digest BOARD_SHA` edits authored rules.
- `journal-init`, `journal-append`, `journal-at`, `journal-fork` and
  `journal-verify` preserve bounded historical replay custody.
- `package`, `play --package package.json --actions actions.json`,
  `verify-play`, `accept` and `verify-accept` close source-to-export acceptance.

The bundled example is reachable by gathering two wood and one ore, gathering
food, crafting lantern and ration, recovering the skiff at (2,1), then the tide
cache at (5,3), offloading adjacent to the dock, delivering and rescuing.
Salvage mission rewards are score-only; no unearned canonical coins are minted.

## Safety and qualification

Source, action, journal, package, contract and report sizes are bounded.
Malformed JSON, duplicate fields, unsupported actions, impossible authored
positions, unearned objectives, stale leases, replay divergence and terminal
continuation fail closed. Tests cover full victory, incomplete attempts,
adversarial edits, forged digests, legal hints, historical forks, portable
package play, CLI and interactive rejection.

Digests are **not signatures**, source provenance is not independently
attested, and this is **not** Windows/device or consumer release qualification.
Focused tests and all required exact-head CI must pass before promotion.
