# Authentic material recovery: NPC witness quests without destructive grinding
**Date:** 2026-10-12, Europe/Oslo. **Stack:** source-verified eyewitness navigation #3687, episodic physical NPC worlds #3685, source-indexed Physics/Godot original engines.

## Why this is real gameplay work
The original causal quest director uses authored `consequence_depth` (default **5**) to demand multiple concrete material actions after firsthand testimony and a committed support/exploit choice. A typical original physical impact damages a site by 1–3 integrity points, but the first repair action restores **3**. The site then becomes fully repaired, making four further `repair` actions illegal. This inadvertently encouraged repeatedly damaging a newly restored site to meet the five-action requirement.

## Implemented player-friendly solution
A genuine **help/relief** action is now also a valid material follow-up for a source-verified harm-triggered support quest. It still uses the *original* game-world `help:<site>` command and requires the player to be within one actually walkable tile of the original authored site. The operation spends finite stamina and, if configured, a real quantity of player supplies. It may improve site integrity while damage remains, and after the landmark is structurally restored it can deliver tangible community relief. A new finite `relief_deliveries` state ledger records the original site, event tick, supplies actually distributed, actual structural integrity restored and real player source.

Recovery progress is counted **only through actually executed original material actions** after an evidence-backed quest choice. Neither proximity, an NPC rumor nor a client-submitted `material_actions` value earns progress. The first structural repair may count as one recovery action, with up to four further source-backed supply deliveries required for default depth=5. An intact site with zero `help_supplies` is no longer a free success/exploit path: an action that spends no real supplies and restores no damage is explicitly rejected before mutating world state.

## Playable authored route
The existing forensic navigator now supports **Deliver finite relief supplies** as a fourth real objective, alongside firsthand testimony, actual structural repair and earned quest resolution. It walks through actual authored obstacles, spends real movement and action stamina, checks finite supplies, advances NPC time and records the source-funded delivery. The Studio can append a successful, source-verified relief action to the latest episodic source campaign, replay the whole multi-episode world, and display the actual material distributions beside world sites and causal quests.

## End-to-end test
The default source rules are deliberately tested, not weakened: the player receives an authentic harmed site and real eyewitness quest, physically travels to an actual NPC, interviews it, commits support, moves adjacent to the damaged landmark, repairs it, delivers four finite source-funded relief shipments, and earns exactly one restored original-quest ending. Crucially, the player need not cause new damage or falsify testimony. Other tests check finite supplies, audited donation totals, tampered source receipts, no-cost/no-effect help rejection, navigated aid and no free source damage or reputation.

## Scope and custody
This is a substantive original Python game-engine improvement inside the existing source-authored quest director, not a decoration or provider LLM-generated response. It modifies only opt-in gameplay source state and local replay; previous game saves, original source files, permanent learning weights, remote releases and user projects are not automatically changed. Native Godot's authenticated one-body Physics reference does not imply native full-quest runtime parity.

### Chronology of improvements (2026-10-12)
- Verified physical impact and cause (improved: real original objects have physical consequences).
- NPC sight and evidence (improved: direct witnesses differ from secondhand rumor).
- Persistent multi-episode campaigns (improved: original world quest context survives sessions).
- Physically navigated eyewitness route (improved: believable player position, stamina and source-approved interview).
- **Finite relief/aid recovery** (improved: default recovery quest can be completed constructively after structural repair, with real donated resources and independent custody).