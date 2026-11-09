# Cooperative role balance and production inspection

`python -m skeleton scene-market-party-balance demo` plays the
original authored cooperative market campaign, verifies the portable
checkpoint, audits its canonical journal and returns a deterministic
source-bound role balance receipt.

`inspect --session-json JSON` reports each player's allowed roles,
productive turns, passes and role contributions. It also reports the
aggregate contribution count per role, unused roles, and the difference
between the most and least productive players. All counts are reconciled
against the replayed canonical journal; forged earned credits or edited
events are rejected before analysis.

`verify --session-json JSON --report-json JSON` independently reconstructs
the report and rejects tampering even when a checksum is recomputed.
This is game-design evidence for role bottlenecks, not a player identity
proof, anti-cheat certification, or source of economy rewards.
