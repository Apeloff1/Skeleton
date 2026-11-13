# delegation world event

## Event purpose
The `diplomacy_delegation` world director implements a bounded regional incident cycle for the diplomacy simulation plane. Its triggering sensor is `activity`. The event can be activated, resolved, aborted or cooled down through a deterministic, version-fenced command ledger.

## Parameters
- Region namespace: north, south, east, west, central.
- Activation threshold: pressure plus requested intensity must be at least 40.
- Severity: 2 units of added pressure at activation.
- Resource cost: 8 plus resolution intensity.
- Recovery benefit: 15 plus resolution intensity, capped at resilience 100.
- Cooldown duration: 5 logical ticks.
- In-memory receipt identity capacity: 4,096.

## Transition contract
1. **Idle → Active:** requires enough pressure and sufficient resources for the base response cost; records an incident identity.
2. **Active → Cooldown (resolve):** requires externally verified world evidence, available resources, and a unique event ID; consumes resources, improves resilience, reduces pressure and starts cooldown.
3. **Active → Cooldown (abort):** terminates an unresolved incident and increases pressure; never issues a success claim.
4. **Cooldown → Idle:** requires a logical tick meeting the cooldown boundary.
5. **Observe:** read-only; use `snapshot` for current values without advancing the clock.

## Data and replay safety
All commands have an exact expected version and a strictly increasing logical tick. Every accepted event stores its identity in an immutable ledger. A duplicate, stale version, invalid event shape, unsupported action or resource shortage yields a rejection without changing state. The host must serialize state and receipts atomically; the pure module does not persist anything.

## Producer boundary
Only a trusted world-event producer may authorize resolution evidence. A nonempty string in `evidence` is insufficient to prove provenance, ownership or policy compliance. Keep region namespace and game-instance identity in the durable journal to avoid cross-world replay.

## Region simulation integration
Use `transition` only after verifying the identity and authority of the upstream producer. Consumers may call `snapshot` for bounded state telemetry. The director does not change neighboring regions, execute transactions, grant user privileges or issue real-world emergency instructions. Cross-region propagation requires a separately reviewed deterministic policy with full rollback evidence.

## Operational checks
- Run `python -m pytest -q skeleton/testing/world_events_v1/test_diplomacy_delegation.py`.
- Compile the associated Python source.
- Parse the JSON Schema and the synthetic scenario as JSON.
- Run repository security, ownership, merge-readiness and E2E gates on the final Git SHA.
- Keep synthetic scenario success separate from real playability, device tests, live event fidelity, load qualification and release approval.

## Failure response
On rejected commands, preserve the preexisting state, record reason and version, and provide the caller a retryable stale-version error only after refreshing its snapshot. At event-ledger capacity, stop new transitions pending a verified durable checkpoint. Never discard identity history merely to improve throughput.

## Balance and design extensions
The threshold, severity, resource cost, recovery gain and cooldown are deterministic profile constants. Balancing against player difficulty, biome progression, faction pressure and multi-region world state requires original gameplay data and dedicated playtest evidence. Modifying this contract requires a versioned migration and replay-fixture update.
