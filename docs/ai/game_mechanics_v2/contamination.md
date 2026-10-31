# contamination — deterministic world mechanic

## Purpose
The contamination state represents a bounded intensity signal used by authored game-world simulation. It is not a privileged account balance, authorization decision, or untrusted remote state.

## State contract
- Domain: `world`
- Initial: `30`
- Inclusive range: `0..100`
- Low-watermark: `19`
- Basic gain: `4`; basic spend: `6`
- Decay coefficient: `1`
- Clock: nonnegative strictly increasing logical ticks for accepted events
- Receipt identity: unique nonempty IDs, bounded to 128 characters

## Supported transitions
1. `gain`: adds the fixed gain plus an explicitly bounded amount.
2. `spend`: subtracts fixed loss plus an explicitly bounded amount.
3. `recover`: applies half of gain plus amount, with minimum one.
4. `decay`: subtracts the domain decay plus amount.
5. `observe`: records a logical event without changing the numeric value.

All numeric results clamp to the inclusive range and preserve the event identity ledger. Duplicate IDs and stale logical ticks return non-authorizing rejection receipts. Invalid shapes raise before state mutation.

## Integration boundary
Call `apply(State(), command)` for one state transition; `replay(commands)` for deterministic bounded batches; and `assess(state)` to render the low and saturation signals. Persist the state and the event identity ledger atomically in the hosting engine. Never infer durable persistence from this pure module.

## Failure and safety notes
- Treat unknown command fields and invalid amounts as invalid requests.
- Never convert a rejected receipt into an accepted game action.
- Never reuse event IDs across independently persisted world instances without namespace separation.
- At 10,000 unique IDs the in-memory state fails closed; use a durable checkpoint protocol before continuing.
- Synthetic fixtures do not prove release readiness, balance quality, network convergence, or consumer-device performance.

## Validation
Run `python -m pytest -q skeleton/testing/game_mechanics_v2/test_contamination.py`.
Inspect `skeleton/forge/game_mechanics_v2/contracts/contamination.schema.json` and `skeleton/forge/game_mechanics_v2/scenarios/contamination.json` before wiring the mechanic to a producer.
