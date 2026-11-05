# Lantern Quay market ledger and saved-future economy

This production vertical exposes the existing playable game's actual gathering,
crafting, NPC trade, inventory and earned delivery outcomes. It never accepts
arbitrary client-provided balances as game authority. Each economic entry is
replayed through the canonical movement, collision, stock, trade, crafting,
mission and ending transition engine.

Use the installed CLI module with commands:

- market-report --bundle victory.json
- verify-market --report market.json
- market-checkpoint --report market.json --tick 10
- market-resume --report checkpoint.json --actions suffix.json --expected-terminal-digest DIGEST
- market-futures --bundle portfolio.json
- verify-market-futures --report futures.json

All outputs are canonical portable JSON. Inputs and outputs have explicit size
limits; invalid JSON, fabricated market values, rehashed fraudulent totals,
stale checkpoint leases and impossible gameplay are rejected. A successful
digest check alone is never sufficient: verification rebuilds every economic
event from the authored source and original action sequence.

This is a deterministic economic *audit*, not dynamic pricing, multiplayer
banking or a device-qualified commercial game. No invented rewards or currency
minting are permitted.
