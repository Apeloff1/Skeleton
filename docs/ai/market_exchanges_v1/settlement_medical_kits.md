# medical kits exchange

## Economic simulation boundary
The `settlement_medical_kits` commodity exchange operates exclusively on fictional world inventory and in-game credit units. It cannot authorize purchases, move real money, perform transfers on external accounts, or attest to asset provenance. Callers must provide trusted actor identity and atomic durable persistence.

## Commodity rules
- Domain: `settlement`
- Commodity: `medical_kits`
- Base price: `107` in-world credits per unit
- Integer buy markup numerator: `125` per 100
- Price tariff units: `6`
- Storage capacity: `318`
- Initial market inventory: `87`
- Initial market treasury and trader wallet: `7342` each
- Maximum units per command: `32`
- Replay ledger capacity: `4096`

## Pricing model
Quotes are deterministic integer arithmetic. Scarcity increases price as the market inventory decreases. A buy applies markup and rounds upward; a sell applies a discounted numerator and rounds downward, with a minimum positive unit price. This is a game economy design choice and must be calibrated for economic stability and player fairness.

## Trade transaction protocol
1. Obtain a trusted actor identifier at the surrounding world-session boundary.
2. Read the durable ledger at the current optimistic version.
3. Construct a command containing side, quantity, event ID, expected version, and logical tick.
4. Call `transact(state, command)` to obtain a proposed ledger and immutable decision receipt.
5. Accept only if the command is unique, uses the correct version and clock, and has sufficient credits and inventory.
6. Commit the ledger update and identity record atomically.
7. Notify world observers only after the durable transaction commits.
8. On a retry, use the stored receipt to avoid duplicate exchange application.

## Accounting invariants
Each accepted trade transfers inventory between market stock and the trader's holdings, preserving the combined unit count. Credits move between trader wallet and market treasury, preserving their combined total. Rejected transactions leave the previous immutable state unchanged. The module does not implement taxes paid to a third party or economic sinks.

## Failure containment
- Unknown fields, malformed values and unsupported trade sides are rejected.
- Invalid numbers, booleans passed as integers and negative quantities are invalid.
- Insufficient stock, wallet funds, holdings or treasury funds reject without mutation.
- Market capacity prevents overflow when traders sell inventory.
- A duplicate transaction ID rejects replay regardless of changed version.
- A stale expected version or nonmonotonic logical tick rejects concurrent modifications.
- At the receipt ledger limit, pause until a verified durable checkpoint is available.

## Integration and evidence
Use `quote` for read-only previews, `transact` for a proposed trade, `snapshot` for UI telemetry, and `replay` to rebuild state from a bounded durable event set. The JSON Schema is a request shape, not an authorization mechanism. Synthetic scenarios are regression aids and not proof of balanced economies or production release.

## Validation
Run `python -m pytest -q skeleton/testing/market_exchanges_v1/test_settlement_medical_kits.py`, compile the matching module, parse both JSON files, then execute all exact-head merge readiness and repository security gates. Test real concurrent trader sessions, persistence faults, receipt recovery, and game-server event authentication before connecting this to an interactive game.

## Roadmap
Dynamic trading routes, player-made market orders, auctions, crafting conversion and faction taxation require separate reviewed contracts. Preserve price determinism, account partitioning, overflow safety, and transactional audit logs as extensions are introduced.
