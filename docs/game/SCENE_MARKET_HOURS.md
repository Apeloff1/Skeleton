# Source-bound merchant opening hours

`python -m skeleton scene-market-hours demo` completes an original offline
trading, crafting and delivery quest using the canonical market engine.
`simulate --source-json JSON --actions-json JSON` accepts a normalized
authoring source and exact player actions. `resume --session-json JSON
--actions-json JSON` resumes a replay-verified checkpoint; `verify`,
`export`, `import` and `board` provide bounded portable custody and
read-only next-turn merchant availability. `edit --source-json JSON
--operations-json JSON` atomically adds or removes authored opening windows.

The `skeleton.scene_market_hours.v1` source contains `market_source` and
`windows`. Every market requires at least one non-overlapping window:
`{ "market_id": "gate_trader", "opens_at": 1, "closes_at": 64,
"min_reputation": 0 }`. The next canonical purchase tick must fall within
a window and the player must have already earned the required reputation.
A closed merchant rejects a purchase without changing the supplied checkpoint.

This layer never creates credits, inventory, deliveries or reputation. The
canonical market reducer enforces earned money, authored position and finite
stock. Session journals bind each action, canonical state and parent save
digest; import replays every event. Board checksums are public corruption
checks, not signatures or authorization proofs. Source digests must be
pinned by trusted consumers when provenance matters. Replay, deterministic
exports and CLI acceptance do not certify device installation or online
multiplayer security.
