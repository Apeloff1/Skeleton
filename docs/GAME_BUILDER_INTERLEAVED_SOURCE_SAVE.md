# Source-replayed portable save for independently scheduled original game worlds
**Authored:** 2026-10-12, Europe/Oslo. Stacked on event-level original world clock #3699, source-only unified game save #3698 and the original Game Builder engine chain.

## Authored original cross-engine game preservation
This deliverable makes the new interleaved 49-cell NPC world portable. The saved document includes complete original platformer/racing/sandbox physical source episodes, reviewed farming/sailing/flight source sessions, a signed source-authored NPC scene and typed settings, **the exact interleaved source event schedule** and canonical source identity receipts. No client-supplied NPC-world state, witness memories, gold, site stock, quest progress or physical results are trusted.

Every import independently replays the entire original genre sessions, actual physical collisions and original NPC actions on the world clock. The replay's source counts, event counts, world time, campaign hash, chained original-source head, final world state digest and scene/settings digest must all match the saved claimed metadata. An adversary who recomputes the outer SHA-256 cannot forge meaningful NPC events, source health, physics collision history or approved rewards without also constructing a legitimately replayable different source campaign. JSON hashes establish deterministic content identity, not private-key signature authenticity.

## Chronologically safe continuation
Source game authors may append additional reviewed physical episodes, distinct genre sessions and/or actual original-world actions, bounded by six physical episodes, four genre sessions, eight actual genre events, 64 world actions and 96 total event clock entries. Continuation requires **independent reimport of the previous complete document first** and preserves its previous source input and event-clock prefix. New authored `at` ticks cannot retroactively enter the past, and source events cannot be double-used. The entire updated campaign is then independently reconstructed from the beginning; there is no snapshot-based shortcut.

## Local Studio
The original Studio offers an operator-controlled JSON export named by the source digest and a strict maximum 4 MB original game-clock file import. On import, the authenticated local server reconstructs the entire interleaved source game and returns the real new NPC world, ordered source event chain, final clock and finite remaining event budget. The Studio restores its previously authored source lists and schedule and renders the genuine existing world map. Critically, it clears its separate physical-only and sequential unified-world proof slots rather than mistakenly treating an interleaved result as evidence for those distinct modes.

## Regressions
Nine executable source tests exercise exact interleaved roundtrip; append-only world followups; later independently earned maritime cargo; impossible source-time inversion and backdating; attacker-recomputed outer SHA with modified physical/genre source state or NPC world; false hardware/release claims; oversized and malformed structures; duplicate original events and invalid continuation; and forged world source counts. Three Studio tests cover export/import controls, original source restore, separate proof modes and same-origin server replay.

## Explicit limits
Source replay is CPU work bounded by finite original game action matrices and reviewed source sizes; maximum encoded save is 4 MB. This is event-level interleaving, **not** true per-frame simultaneous Physics, farm and aviation simulation, native full-world Godot parity, or commercial console certification. It does not auto-overwrite original game files, create remote workflows or promote AI model weights. Future long-running and per-frame worlds require an explicit batched checkpoint/versioned migration design without bypassing signed source replay.

### Dated improvement history (2026-10-12)
- Full source-driven physical and genre effects (improved: authentic achievements produce eyewitness and quest consequences).
- One authenticated interleaved world clock (improved: arbitrary reviewed genre-event order can change real world rumors, time, sites and quests).
- Portable complete source action-log saves (improved: the exact cross-engine order survives export and import, with no client-authored snapshot bypass).
- Append-only continuation (improved: new events can extend an authored history without retroactively rewriting previous NPC testimony).