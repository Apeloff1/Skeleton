# Episodic original-game physics, NPC memories and continuing quests
**Authored 2026-10-12, Europe/Oslo.** Based on source-custodied Godot parity PR #3683, multi-incident physics #3681, authored NPC world #3676, and the Game Builder editor families.

## Mechanics
This system moves beyond a one-shot source-derived hazard: **up to six independently replayed original game sessions** can influence one persistent 49-cell NPC world in a deterministic campaign. Each episode authenticates the typed source genre, authored scene and original transcript, then independently replays its source-derived real physical collisions. Exact source fixture IDs, timestamps, event kinds and world-site bindings drive actual impacts. All NPC positions, site integrity, stored eyewitness memories, rumors, energy, quests, suspicion, day/night phase and quest resolution history persist into the next episode.

Each physical incident is emitted through the original quest director, never through a client-supplied reward or NPC memory. Genuine evasions create no incidents. First-hand witnesses must physically see the impact; rumors remain a separate transmissible authority. Authored player movement, site support/repair, eyewitness interviewing, evidence-based choices and consequence-bearing quest resolution run through the same original NPC world as before; no source game save or user project file is mutated.

## Anti-exploit and temporal custody
For each original authored game-scene/settings identity, later sessions must strictly **extend the preceding original action transcript**; reusing a source receipt, resetting/reordering earlier source moves or replaying the same episode with an alternate physical action list cannot generate new quest rewards. A global set of accepted physics-interoperability digests prevents source replays across different episode slots. Every episode records original session and scene digests, true ordered contact histories, applied world incident IDs, distinct NPC witnesses, actionable quest IDs, persistent site strength and quest progression, chained SHA-256 ledger head and a final full-world digest. The verifier independently reruns every original source, physics encounter and NPC action and compares the full result.

Boundaries: at most 6 episodes, 24 authored-world actions per episode, and 64 total. One episode admits up to four original world site bindings while maintaining the existing eight-object physics source inspection cap; source objects and sites must be unique inside that episode. An exhausted quest, event, memory or physical proof budget causes validation failure rather than fabrication. A terminal campaign cannot accept post-victory/defeat actions.

## Studio gameplay
New original-game Studio panel offers Capture signed original game episode, Run persistent living-world campaign and Reset unpublished episodes. It snapshots an independently authenticated platformer, racing or sandbox session, captures reviewed source impacts and author-selected world site, and permits physical maneuvers with optional NPC-world followups. The full campaign is created by an authenticated local API, independently reverified and displayed with source chronology, NPC positions, real site health, separate eyewitness memories and rumor records, quest states, time/day and the immutable campaign receipt.

## Regression
Nine full-engine tests cover multi-episode damage, quest continuity, actual avoided obstacles, append-only original game transcript, repeated-receipt attacks, mixing independent source game families, time-preserving rumors, forged event ordering and unearned rewards, bounded actions and source identity modification. Three Studio tests verify working controls, source-digest custody, release flags and server-side independent replay. These join the complete exact-head Windows and Ubuntu advanced-engine suite.

## Security / production boundary
This is executable original reference gameplay, not a full commercial NPC engine, online MMO service, production network save manager or native certified multi-genre app. No external publication, mutation of user source files, automatic AI learning-weight promotion or fabricated success. The independently native Godot collision profile remains restricted to its explicitly tested scope.

### 2026-10-12 chronology
- Actual source-bound physics contacts (improved: original obstacles have physical consequences).
- NPC line-of-sight causal quests (improved: genuine witnesses and rumors carry different authority).
- Multi-object physical incidents (improved: multiple distinct original source objects share a world).
- Episodic persistent original game campaign (improved: new source progression changes NPC world over multiple sessions instead of resetting).
- Interactive authoring and strict replay ledger (improved: test an authored long-running game world without unsafe source writes).