# Portable original mixed-source NPC game save: physics plus farming, sailing and flight
**Dated:** 2026-10-12, Europe/Oslo. Stacked on unified persistent genre world #3697, source-to-NPC genre bridge #3696, typed conditional events #3693 and original replay-verified Physics/NPC campaign #3691.

## Concrete authored-game persistence
The Game Builder now has a separate portable, deterministic input-log save format for an original campaign containing physical platformer/racing/sandbox episodes **and** authenticated farming/sailing/flight achievements. The save retains original physical source episodes, genre source sessions, authored scene and reviewed rules, exact original action-to-NPC-site bindings, and source-authored NPC follow-up actions. The independently verified world chain includes finite site inventory, sight-bound NPC memories, rumor histories, active and completed quests, current player resources and story consequences.

Unlike a mutable snapshot import, a three-megabyte bounded canonical JSON document only carries the **inputs required to reconstruct** those outcomes. It includes a digest of the independently replayed physical prefix, full mixed-source campaign receipt, chained world-event head, final independently computed NPC-world-state hash, exact episode/event counts and explicit false release/model-promotion flags. On import, the server independently reruns all original source engines, original physical collisions, genre achievement traces and actual NPC quests, then compares the reconstructed full world to every claimed checksum and count.

## Resume and temporal order
After independent import, authors may append up to four distinct original genre sessions in total, provided no previously executed NPC-world follow-up actions would have to be chronologically rewritten. Once real world actions have been played, inserting a new genre achievement **ahead of those actions** is rejected; creators may still append additional actual original-world commands up to the 24-action mixed-campaign limit. Duplicate sessions, malformed bindings, noncanonical source actions, fabricated reward/health changes, impossible source scenes and forged world event IDs are rejected by complete replay.

The canonical SHA-256 input-log hash provides reproducibility and accidental edit detection, not private-key author identity. A technically capable author may construct a *different valid* campaign with independently replayable inputs; the input log is not a signature-based permission system. This distinction prevents overstating provenance security.

## Studio user experience
**Export replay-verified unified campaign** writes a compact JSON document with an original source hash in its filename. **Import source-verified unified save** checks a strict three-megabyte file budget and asks the authenticated local server to reconstruct the entire multi-engine source history. The Studio then separately verifies its original *physical-only prefix* using the saved typed rules, restoring genuine NPC investigation and episodic controls without granting a mixed-source proof false physical-only authority. Finally, the actual unified world map, genre chronology, site stock, witnessed quests, and remaining finite action/genre budgets are displayed. Source data remains in reviewed local memory until another explicit operator action.

## Adversarial tests
Seven full-engine tests cover authentic complete cross-source roundtrip, immutable action continuation, independently sourced later genre achievement, denial of preexisting chronological action inversion, forged physical/genre source state with an attacker-recomputed outer hash, typed negative release flags and unknown/oversized saves, budget violations, duplicate original source and invalid world actions. Three Studio regressions verify the real file controls, exact original physical prefix restoration and same-origin server endpoints.

## Explicit limitations
Original local reference game logic and source-replayed NPC world only. These inputs are not automatically uploaded to game consoles, certified for hardware, merged into production `main`, converted into native Godot multiplayer or persisted in user cloud storage. The combined campaign currently supports an original physical campaign followed by up to four original genre sessions and 24 later NPC actions, not an arbitrary globally interleaved simulation or unrestricted long-lived MMO. Any future more general event scheduler needs a separate temporal proof contract.

### Chronology of dated improvements (2026-10-12)
- Source-bound original physical world (improved: authentic NPC witnesses, rumors and quests).
- Reviewed cross-genre original harvest/cargo/flight events (improved: source achievements cause real world consequences).
- Unified living-world engine (improved: those consequences persist in the actual physical campaign).
- Mixed-source portable game save (improved: fully replayable original multi-genre state, real continuation, and no trusted client-snapshot bypass).