# Original game multi-incident physics and NPC investigation system
**Authored:** 2026-10-12, Europe/Oslo.

## Concrete gameplay
One independently authenticated platformer/racing/sandbox scene creates a bounded physical contact transcript. The NPC controller binds up to eight **distinct original source objects** to up to four distinct, author-selected world sites, then independently replays the actual physics scene. Every genuine collider hit retains its trusted original index, game-source object identity, tick and frame, and contact count.

Source incidents are ordered by the **first actually recorded impact tick/frame and original fixture index**, regardless of which order the user listed author mappings. Multiple impacts from one source object create one severity-capped world incident; different impacted objects may create separate incidents, local NPC eyewitness memories, suspicion changes and distinct causal quests. An unhit source object creates no incident. Every incident acts on one persistently simulated 49-cell NPC world rather than resetting the world between objects.

Night/day perception, obstruction, rumor vs direct observation, finite NPC memories, quest-site durability and event budgets remain governed by the original quest director. External physical incidents are attributed to the collision source, **not** to the player; they cannot reward a player merely by existing. Additional authored world actions can continue the NPC simulation and gather real witnesses for branch choices and quest outcomes.

## Performance and determinism
At most eight source-to-site bindings are accepted; each site may have one binding per replay. Original followups are limited to 24 commands. Complete per-fixture physical contact counts must match the bounded chronological log. If more events were emitted than the retained contact history can prove, the transaction refuses attribution instead of inventing an order. Both source game and physics session are independently replayed, and the combined result contains a canonical SHA-256 digest and the final complete original NPC world state.

## Studio
The original Studio has a **Run multi-object collision investigation** workflow. It fetches approved source obstacles from the independently verified physical source proof, displays their identities and passability, authors a one-to-one original site mapping, signs a new NPC world scene and submits a bounded action transcript. A dedicated evidence display shows impact order, source fixture counts, eyewitness vs rumor records, generated causal quests and the live original-world timeline. The server independently reconstructs the result; no client-provided NPC health, reward or witness field is trusted.

## Independent tests
Nine adversarial regressions cover real attributable racing impacts, genuine evasive steering, many authored platformer hazards with only actually contacted objects attributed, canonical incident time/order regardless of mapping order, persistent world followups, identity uniqueness, malformed bindings, action budgets, tampered source/physics/witness/quest history, and external source substitution.

## Limits and next
This is still original Python-reference gameplay, not a newly certified native Godot multi-NPC world. The physics receipt holds a bounded 96-event recent window; historical overflow fails closed. Oriented SAT geometry still requires fixture-specific custody instrumentation before it may participate in trusted NPC attribution. No automatic publication, no original save overwrite and no model-weight promotion.

### Change history (2026-10-12)
- Original source-driven physical encounters (improved: game objects influence actual physical motion).
- Individual source fixture custody (improved: physical hit IDs rather than estimated collisions).
- NPC eyewitness incident bridge (improved: physical impacts change real world site/quest state).
- Multi-incident authored quests (improved: independent objects create independently evidenced quests in one persistent world).
- Studio original object-to-site authoring (improved: multiple encounters can be tested without writing bespoke Python).