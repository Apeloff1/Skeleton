# Oriented and rotating SAT: exact original fixture source custody
**Authored:** 2026-10-12, Europe/Oslo. Depends on the original Multi-Incident NPC World PR #3681.

## Actual physics engine implementation
The signed original-game Physics reference now uses a shared pure contact-custody writer across three already-executable collision implementations: axis-aligned Minkowski sweep/static penetration, discrete orientation-sensitive SAT, and bounded temporal SAT sampling along a rotating rigid body's intermediate trajectory. Every successful static-fixture contact records the exact original fixture index and body ID, event kind, physics tick/frame and bounded integer position.

The history owns **96 most recent individual contact records**, while a complete per-fixture count vector persists through the signed session. This means the engine can measure contact frequency without unbounded state growth, but it cannot claim an exact chronological replay for incidents older than the retained window. Such chronological reconstructions explicitly fail closed in the separately authored multi-incident NPC compiler.

Source collision admission still respects original physical masks/layers and actual authored geometry. Static SAT contacts must intersect the original rotated shapes; swept SAT attribution occurs only when a tested intermediate oriented manifold actually collides. World-boundary hits, dynamic pair-to-pair collisions, invisible/unmasked objects and guessed near misses cannot create source-fixture IDs.

## Defense and gameplay limits
All original results are reconstructed by the canonical source replay verifier, including the contact-count vector and event list. Edited fixture indices, nonexistent physics bodies, forged contact kinds, altered positions or phantom hit counts cause verification mismatch. Typed source layout and game settings remain authoritative; external UI state never signs the fixture identity.

### Current profile
- Existing source Physics engine remains a finite integer-turn, 2D/limited-extruded-3D reference, not a certified general rigid-body solver.
- Discrete oriented SAT and temporal swept SAT now emit source fixture identity through a common evidence contract.
- The platformer/racing/sandbox interoperable NPC exporter **still uses the reviewed AABB physical rehearsal profile**. Extending it to fully oriented authored source assets requires an explicit, separately tested geometry authoring adapter, not just these receipts.
- Native Godot independently certifies only the supported signed 2D AABB one-body and static obstacle profile at existing tested heads; no automatic native parity is claimed for rotating SAT contacts or new metadata.

## Adversarial evidence
Eight new tests cover discrete rotated fixture overlap with an untouched neighboring object, masked/non-colliding geometry, rotation-only temporal contact, actual broadphase layer exclusion, 96-event bounded ledger, invalid source ID/kind, full signed authored scene trajectory and detection of tampered oriented fixture receipts.

## Timestamped improvement chronology
- 2026-10-12: independent physical source movement (improved: bounded gameplay contacts and energy transfer).
- 2026-10-12: authored fixture IDs for AABB (improved: exact original obstacle ownership).
- 2026-10-12: persistent multi-incident NPC worlds (improved: multiple original object histories influence eyewitness quests).
- 2026-10-12: **shared discrete SAT and rotating SAT custody** (improved: genuinely rotated obstacles can be identified by source, not by approximate bounding-box proximity).

Next engineering step: geometry-aware direct source authoring for rotated hazard objects, independent Godot rotated-collider parity, and cross-genre event causality with the same original source ledger.