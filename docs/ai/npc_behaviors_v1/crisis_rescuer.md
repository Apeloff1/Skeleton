# NPC behavior: rescuer

## Simulation responsibility
The `crisis_rescuer` director implements a deterministic and bounded crisis NPC behavior cycle. It receives already authenticated world events, evaluates resource costs, and emits immutable receipts. It is not a security principal, account authorization service, persistence engine, or live dialogue model.

## Profile identity
- NPC role: `rescuer`
- Simulation domain: `crisis`
- Preferred activity site: `camp`
- Alternate activity site: `home`
- Initial energy: `55` of 100
- Initial trust: `35` of 100
- Work energy cost: `9` + requested effort
- Rest energy recovery: `8` + requested effort
- Social trust gain: `3` + requested effort
- Work stress coefficient: `7`

## Supported behavior decisions
1. **Observe:** ledger a non-mutating resource observation with a new identity and version.
2. **Work:** consume bounded energy while increasing physical stress.
3. **Rest:** replenish bounded energy and reduce stress.
4. **Socialize:** expend one energy point and improve trust.
5. **Travel:** move to an approved location if energy covers the cost.
6. **Retreat:** reduce stress, slightly reduce trust, and return home.
7. **Negotiate:** require an upstream authenticated witness and available energy.
8. **Guard:** consume energy under a watch duty and increment stress.

## Deterministic transition protocol
Load the persisted state with its event ledger, call `transition(state, event)`, and commit the new version and identity ledger atomically. An event must include a unique ID, exact expected version, strictly larger logical tick, action name, bounded effort, allowlisted destination, and witness field. Rejection receipts must never be interpreted as permission to proceed.

## Trust and data custody
World-event producers are responsible for validating witness provenance. A nonempty witness string alone is **not** cryptographic proof. The module only checks that the witness field is present for negotiation. Bind receipts to the NPC/world identifier at the storage boundary and isolate cross-world identities. Do not expose mutable state objects to untrusted scripts.

## Failure and recovery handling
- Unknown fields, invalid actions and malformed numeric inputs fail before state mutation.
- Duplicate event identities reject replay, even with a different logical tick.
- A stale version or nonmonotonic tick rejects optimistic concurrency races.
- Insufficient energy rejects resource-consuming actions rather than overdrawing.
- Once the in-memory ledger contains 4,096 event identities, progression must pause for a verified durable snapshot and replay fence.
- For crash recovery, atomically persist a new state and its receipt before publishing the action to subscribers.

## Gameplay acceptance checks
Run `python -m pytest -q skeleton/testing/npc_behaviors_v1/test_crisis_rescuer.py`, compile the source, inspect the JSON Schema, and replay the synthetic scenario. Test agent interactions under an actual event origin before claiming safety, performance, accessibility, or consumer-device qualification.

## Observability
Record the identity namespace, action class, accepted/rejected decision, rejection reason, version, logical tick, and bounded resource fields. Avoid logging secrets, private dialogue text, or personally identifiable user data.

## Extension plan
Add capability profiles and world-state predicates through separately reviewed typed contracts. Future changes to the action set require a schema revision, explicit migration, deterministic scenario fixtures, and full fail-closed regression coverage. This policy intentionally grants no privileged capability on its own.
