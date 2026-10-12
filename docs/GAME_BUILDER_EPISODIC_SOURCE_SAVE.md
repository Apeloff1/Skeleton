# Persistent original NPC and physics campaign: portable source-verified saves
**Authored:** 2026-10-12, Europe/Oslo. Stacked on material recovery PR #3688 and original episodic NPC worlds #3685.

## Gameplay and storage
An authored original platformer/racing/sandbox game can have multiple real source-driven Physics encounters and a continuing NPC world: firsthand memories, suspicion, rumor propagation, resource relief, quest status and world time. The new portable save format preserves **the complete original source inputs** rather than trusting a serialized mutable NPC state. It includes typed world scene/settings, all episodes with independent original session and source mechanics, reviewed physical actions, original-object/site binding and performed canonical world actions.

On export the server independently reconstructs the campaign and records its source scene/settings digest, chained episode head, original campaign digest, independently recomputed final world-state digest, full original episode/action counts, fixed negative release/weight-promotion flags and canonical SHA-256 checksum. There is no snapshot bypass. Saves have an explicit UTF-8 canonical JSON budget of two million bytes and a fixed schema with zero accepted client extension fields.

On import, a valid outer hash is **not sufficient**. The loader independently replays every original genre action, every source fixture collision and every NPC-world action; it then compares the new campaign digest, episode chain and final world hash. Forged client HP, gold, reward, site strength, witness testimony, scene settings, altered source object/site bindings or even a recomputed outer hash are rejected if they do not produce exactly the original verified campaign.

## Continuation
Continuation imports and verifies the existing complete save before appending additional original-world actions (maximum 24 per episode and 64 per campaign), or at most six total source episodes. The prior source replay, shared world chronology, per-source append-only action transcript and Physics receipt uniqueness remain independently checked. No client-supplied mutable memory can override the reconstructed prefix.

## Studio
The authenticated local Studio has **Export verified campaign save** (portable JSON download), **Import authored campaign save** (bounded JSON file input), and a source/result receipt panel. Import rebuilds the original source episodes, validated source scene and NPC world, restores real quest options and renders the existing playable 7×7 original map. The user can continue the original game using the existing world route, aid and quest controls after a successful import. No browser-local unsafe script is executed from save content.

## Adversarial validation
Seven engine regressions cover deterministic full round-trip, immutable append-only world continuation, authenticated second source episode, forgery with an outer checksum recomputed, invalid release flags, unknown fields/large save rejection, repeated source attacks, illegitimate world commands and scene/settings substitution. Three Studio tests cover actual download/file import controls, independent server reconstruction, strict identity/negative release flags and bound document size. All are added to full exact-head Windows and Ubuntu advanced-engine CI.

## Safety, limits and release
Local operator save/restore only. Serialized data is never interpreted as executable Python or GDScript. The complete source log is required; no standalone compressed/optimized native game state or electronic signature/private key is implied. A SHA-256 digest gives reproducibility and tamper detection against accidental or uncoordinated edits, **not cryptographic proof of author identity**. No original user project files are overwritten; public publication, external hardware certification or learning-weight promotion are explicitly false.

## Dated changes
- 2026-10-12 (improved: separate episodes now share one actual NPC world).
- 2026-10-12 (improved: original eyewitness routes, finite relief and earned quest recovery).
- 2026-10-12 (improved: complete source-reconstructed portable input-log save and anti-fraud import).
- 2026-10-12 (improved: bounded append-only continuation and readable Studio import/export receipts).