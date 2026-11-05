# Production recipe: ward plate

## Domain and design intent
The `arcane_ward_plate` recipe implements a pure deterministic lot-production workflow for the arcane subsystem. It models materials, operator energy, work stages, quality acceptance, product yields and scrap. This code is simulation logic; it cannot actuate manufacturing machinery or authenticate player identity.

## Versioned recipe parameters
- Recipe ID: `arcane_ward_plate`.
- Schema family: `skeleton.production_pipeline.v1`.
- Material cost per batch unit: `4`.
- Energy cost per stage and batch unit: `4`.
- Maximum lot batch quantity: `3`.
- Product yield per accepted batch unit: `1`.
- Scrap output per accepted batch unit: `0`.
- Initial materials: `52`.
- Initial energy: `85`.

## Ordered production phases
1. **Start**: reserve and consume the declared raw material stock for a selected batch. The lot enters the working lifecycle.
2. **Prepare**: validate externally produced preparation evidence and spend the first stage energy budget.
3. **Fabricate**: validate fabrication evidence and spend its stage energy budget.
4. **Inspect**: validate inspection evidence and spend the final stage energy budget.
5. **Finish**: require final, independently verified quality evidence before publishing completed product and scrap output.
6. **Cancel**: terminate an unfinished lot without granting any product. Consumed materials remain spent until an separately designed recovery workflow is approved.

## Transaction boundaries
The calling production coordinator reads a world-instance-scoped immutable state, assigns a unique receipt identity and expected version, and supplies a strictly increasing logical tick. The pure `transition` function either returns a new immutable state and acceptance receipt or preserves the old state with a rejection reason. State and receipt history must be stored atomically before any UI or marketplace observer is notified.

## Quality and evidence custody
The core validates the presence and shape of evidence strings, but a string is not a proof of provenance. The host must validate the signer, source event, recipe binding and permissions for each stage and for final quality acceptance. Never expose the `finish` command to an untrusted client without server-side evidence verification.

## Conservation and resource safety
Materials are deducted on start and accounted in `spent_materials`. Energy is deducted only on accepted stage advancement. Products and scrap are minted as fictional production outputs only on accepted completion. Output counters are capped, and no negative materials or energy are allowed. Rejected transitions never change balances or ledgers.

## Replay, contention, and crash recovery
The workflow rejects duplicate event identities, stale optimistic versions, nonmonotonic ticks, malformed commands, unsupported actions and oversize batches. The in-memory ledger supports a maximum of 4,096 accepted identities. For longer sessions the application must implement an independently reviewed durable checkpoint and event replay fence.

## Integration points
- Connect upstream to game inventory and crafting UI through typed event adapters.
- Connect downstream to world marketplace or item crafting only after confirming a durable completion receipt.
- A completed lot is terminal; a new lot requires a new state instance with a unique world-lot identifier.
- A cancelled lot cannot be resumed without an explicit reviewed recovery/migration policy.

## Focused validation
Run `python -m pytest -q skeleton/testing/production_pipelines_v1/test_arcane_ward_plate.py` and compile the associated Python source. Parse both JSON files, verify synthetic replay receipts, then execute the repository's exact-head security, ownership, quality and integration gates.

## Qualification limits
These fixtures do not prove real-time behavior, mechanical safety, game balance, external supply authorization, on-device inference capability, or consumer release readiness. Do not promote draft status solely on the basis of generated source inventory.
