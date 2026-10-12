# Authoritative original-fixture collision identities
**Authored:** 2026-10-12 (Europe/Oslo). Depends on original-game NPC witness PR #3676.

## Physics capability
The deterministic AABB physics solver now logs each actual original fixture collision with the exact authored fixture index, source physical body ID, contact kind, position, tick and frame. It never infers fixture ownership from a bounding box after the fact. A complete per-fixture count vector survives the entire audited session and a 96-record contact window preserves recent ordering without unbounded replay growth. Original collision behavior, energy, momentum, masks and world-bound contacts are unchanged.

These authoritative records are reconstructed and compared during ordinary replay verification; edited source fixture indices, made-up bodies, forged counts and missing contacts cannot pass the canonical gameplay verifier.

## Cross-family gameplay
Source-derived platformer spikes, racing track obstacles and sandbox buildings/ridges now receive exact per-source-fixture impact counts. A source witness that the physics engine did not touch cannot be credited with damage. More than one solid fixture may be present because an external NPC event is attributed to a *specific actually collided source fixture*, not to an arbitrary visible object.

The physically witnessed quest director uses the unique original object ID in a signed author-site mapping and applies only that object's bounded contact severity. Neighboring unhit fixtures cannot mint quests, damage a world site or create false first-hand testimony. Existing rumor-vs-eyewitness and line-of-sight/terrain visibility rules remain under the original quest engine.

## Tests and limits
Six new focused physical custody tests check authored fixture index and source physical body, multi-object contact selection, masked pass-through, no-fixture history, tampering/replay rejection and source-indexed interoperability evidence. The earlier ten physical witnessed-world tests now include a multi-obstacle scenario where only the actually impacted object creates the physical origin event.

Only the trusted original AABB contact solver participates in per-fixture receipts. The oriented SAT solver retains its separately authored contact manifolds and does **not** gain source-indexed attribution without a future explicit oriented mapping. The one-body Godot native laboratory replays its documented original fields and still needs device certification and explicit native receipt parity for fixture-ID history.

## Timestamped improvements
- 2026-10-12: real physical scene encounters (improved: original source obstacles actually block motion).
- 2026-10-12: audited NPC witnessed incidents (improved: original physics events create conditional eyewitness quests).
- 2026-10-12: source-indexed fixture custody (improved: many authored hazards can coexist without guessing who caused a collision).
- 2026-10-12: replayed per-fixture evidence and source attribution (improved: misses never count as NPC causal incidents).

Next: signed event-to-NPC investigative quest progression for multiple simultaneous incidents, oriented SAT collider identity and cross-frame native source-ID parity. Previous PRs remain draft and unmerged pending full dependency reconciliation.