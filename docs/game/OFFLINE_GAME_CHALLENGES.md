# Offline original-game time trials and scoreboards

The canonical `python -m skeleton app game-project` command can score actual
controller-driven, verified original capsule saves without a network connection.
These are **local gameplay challenge receipts**, not trusted player identities,
anti-cheat attestations, native console exports, or independent rights clearance.

Create an original capsule and a source-bound save using the existing
`--demo-project` and `--play-capsule` / `--terminal-play-capsule` flows.
A challenge policy is a small JSON object:

```json
{"schema_version":"skeleton.game.play_challenge_policy.v1","mode":"fastest","max_frames":1024,"max_jump_frames":1024,"max_left_frames":1024}
```

Supported modes are `fastest`, `fewest_inputs` and `fewest_jumps`.
Each run must reach the actual goal and respect all frame, jump and left-input
limits to be ranked. Unfinished and disqualified runs remain visible below
eligible runs, but have no winning rank key. Tie-breaking uses the replayed
session SHA-256 for deterministic ordering.

```sh
python -m skeleton app game-project --score-play-session save.json --session-capsule capsule.json --challenge-policy policy.json --score-output score.json
python -m skeleton app game-project --verify-play-score score.json --session-capsule capsule.json
python -m skeleton app game-project --rank-play-scores --session-capsule capsule.json --score-input score.json --score-input alternative-score.json --board-output board.json
python -m skeleton app game-project --verify-play-board board.json --session-capsule capsule.json
```

Every score embeds the exact source-bound session and policy, and every board
embeds its score packages. Reopening either recomputes the original capsule's
source identity, the deterministic physics replay, victory state, input metrics,
scoring policy and ordering. Unknown fields, malformed booleans, tampering,
duplicate sessions and mixed policies fail closed. At most eight entries per
board; each score is at most 120 KiB, each board at most 160 KiB.

The exclusive-create output path never overwrites an existing save or follows
an input symlink. Local SHA-256 hashes detect accidental or adversarial
modification *relative to the original capsule* but are **not digital signatures**.
A malicious actor controlling both capsule and score can author a different
self-consistent history; do not use these scores for prize payouts or
identity-sensitive competition. No model inference, third-party game assets,
native renderer or external service is needed.
