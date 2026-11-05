# Original salvage quest and event director

This source-bound story engine composes the canonical Lantern Quay world with
the replay-verified salvage rescue mission. The original five-beat authored
story discovers the wrecked skiff, discovers the tide cache, secures the
manifest, delivers supplies and finally restores the harbor rescue beacon.
Each quest requires earlier earned quests and a real world/overlay transition.
Story reputation is a separate earned narrative score, not canonical coins.

`python -m scripts.game.harbor_salvage_story --help` exposes:
`run --actions actions.json --require-all`, `verify --story story.json`,
`resume --story story.json --actions continuation.json --expected-digest SHA`,
`author --report report.json --edits edits.json --expected-digest BOARD_SHA`,
`verify-author`, `package`, `verify-package`,
`play --package package.json --actions actions.json --require-all`,
and `verify-play`. All input/output is bounded JSON and every exported
story is independently reconstructed from source-bound canonical actions.

The authored quest board rejects duplicate IDs or story beats, future or
cyclic prerequisites, unknown salvage sites, invalid thresholds and
unrecognized fields. Transactional edits may preview existing gameplay and
reject impossible story changes. The event chain seals the preceding event,
quest ID, story beat and tick; independent verification recomputes all events
and earned consequences, not just the digest. The completed example earns
22 narrative reputation and the original `harbor_restored` ending.

No external text or code is executed. Digests are not signatures; this
original offline CLI is not a device or release qualification claim.
