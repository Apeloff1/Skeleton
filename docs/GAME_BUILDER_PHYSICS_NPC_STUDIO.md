# Studio: original physical NPC witnesses and investigations
**Authored:** 2026-10-12 (Europe/Oslo). Depends on original-game physics NPC bridge #3676 and per-fixture source identity #3678.

## Consumer-facing gameplay
The original local game Studio now includes an opt-in **NPC-witnessed original physics and quests** panel, rather than requiring developer-only Python APIs. It appears for authored original platformer, racing and sandbox sessions and uses the already authenticated local Studio transport.

The Studio first requests the independently replayed original physical encounter and displays authentic fixture IDs, types and whether each source layer is solid/passable. It preferentially selects a source object with a real recorded hit. The user supplies a **signed author mapping** from the original source object to one of four original-world quest locations, then optionally records up to 24 concrete world follow-up actions.

The local server independently creates and validates a signed 49-cell NPC world and uses the canonical source-to-physics-to-NPC causality bridge to reproduce every impact and eyewitness event. It never accepts client-authored NPC memory, damage totals, quest IDs or achievement status.

The resulting interactive evidence view shows exact per-source collider impacts, the physical incident and world site, firsthand witnesses separately from rumor, original causal quests, performed investigative actions, NPC memory contents and final signed source digests. If the authored original obstacle was avoided, no contact event, NPC witness or quest is minted. If the NPC was behind a solid wall or outside its perception radius, it does not become an omniscient eyewitness.

## Release and assurance
The original saved game and project files are not modified. Evidence is reconstructed server-side with the original signed source game session, typed editor settings and reviewed world scene. Public publishing, native hardware certification, remote write privileges, automatic quest rewards in the source genre and AI weight promotions are all explicitly disallowed.

## Tests
Three additional original Studio regressions cover actual source/site authoring UI, bounded follow-up workflow, separate eyewitness and rumor display, source digest safety, no unearned certification claims and server-side independent replay reconstruction. These run with the entire Windows and Ubuntu reference engine matrix.

## Chronology of improvements
- 2026-10-12: real original physics encounters (improved: source obstacles produce actual collisions).
- 2026-10-12: witnessed physical quests (improved: contact may generate NPC eyewitness events only after sight checks).
- 2026-10-12: fixture index custody (improved: multiple source objects do not cause guessed evidence).
- 2026-10-12: playable local NPC investigation panel (improved: authored game creators can inspect and continue physical quests without writing code).

Next: in-studio map visualization of signed NPC movement and sight occlusion, per-quest branching editors, original gameplay-save continuation, and real fixture-specific multi-incident chains.