# Authored eyewitness navigation and original 7×7 NPC game-world map
**Authored:** 2026-10-12, Europe/Oslo. **Dependent:** episodic original Physics/NPC campaign PR #3685; parent physics/native source identity PRs remain separate.

## Executable investigation mechanics
A persistent authored world now supports deterministic, source-verified investigation routes to **physically present firsthand witnesses, damaged source sites, and earned quest-resolution locations**. The navigator verifies the entire original episodic campaign before touching the route model, then simulates finite canonical `quest_director.step` actions on a separate copy of the current world state.

The pathfinder uses shortest paths on the original 49 real cells, cannot walk through signed obstacles, cannot teleport diagonally, and produces stable directions with a canonical north/west/east/south tie-break. It replans each step from the *current* world state to account for mobile NPCs and time-varying evidence. It spends actual original movement stamina, waits by actually resting when finite stamina is insufficient, advances the actual world clock and its NPC autonomy/rumor propagation, and enforces a 24-action route budget.

### Original investigative objectives
- **Testimony:** choose the nearest genuinely reachable NPC with a direct memory of the incident and adequate trust/suspicion. Rumor-only speakers and NPCs who forgot the event cannot be passed off as eyewitnesses. When adjacent, issue a real `speak:<id>` action to the canonical quest runtime, then verify the quest's actual testimony list before declaring success.
- **Material repair:** traverse an original authored route to a damaged site, spend actual finite supplies and stamina using the canonical `repair:<site>` action, and prove that source site integrity improved rather than claiming a decorative fix.
- **Earned resolution:** only offer a quest conclusion if an original commitment, firsthand evidence count and actual material follow-up count meet the real quest rules. Walk to the source site, issue the canonical `resolve:<quest>` action and check the resulting ending, reputation and finite gold effects. Missing prerequisites cause an explicit status with zero manufactured progress.

The returned receipt includes the original campaign digest, signed quest event, actual witness target (or an explicit reason why none exists), every executed move/rest/interview/repair/resolve action, updated player/NPC positions, real stamina and site state, canonical events, chained SHA-256 action receipts, observed quest outcome and full independently reconstructed preview state. Neither original saves nor published assets are modified until the user opts to append the approved action sequence to a future campaign replay.

## Studio experience
The local authenticated Studio now renders the **actual 7×7 original NPC map** from the verified campaign: impassable terrain, intact/damaged site identities, original NPC positions, people with genuine firsthand memories, distinct rumor-only people, player location, original world day/tick. Users can click a real source quest site to select its active causal quest, choose testimony/repair/resolution, compute a source-authorized investigative path and see the exact original moves before applying them.

`Add verified route actions to campaign and replay` checks the route's source campaign digest, proof outcome, original finite world-action budget (24 per episode, 64 total), then appends the actual commands to the user's queued last episode and requests fresh server-side independent replay. A stale route or unearned objective cannot be applied. No client invents a witness, quest resolution or reward.

## Anti-adversarial validation
Nine engine tests cover real testimony after actual movement, obstacle/stamina budgets, finite physical repairs, denial of unearned quest resolution, a genuine fully earned support/repair/resolve success, memory decay and rumor-only denial, forged position/testimony/action history, nonexistent quest targets and only registered original-world commands. Four Studio tests verify real map source fields, clicked site selection, playable action-appending workflow, stale-source denial, server-side independent reconstruction and explicit no-hardware/no-publication flags.

## Explicit limitations
This is advanced deterministic original gameplay and UI, not a general autonomous NPC model, a commercial-ready map system or live cloud multiplayer. A visible NPC marker is its **current** verified cell, not historical proof of where it stood when it saw an old event; historical proof remains in the original incident ledger. Native Godot's source-bound 2D AABB physical profile does not imply native parity for the entire Python quest world. No automatic AI-weight promotion or app release.

### Dated improvement history (2026-10-12)
- Source-authored physical obstacle games (improved: measurable impacts and real original-body mechanics).
- Single and multi-event witnessed worlds (improved: real NPC perceptions cause or decline quests).
- Persistent source episodic campaigns (improved: original incidents, quests and rumors survive across game sessions).
- Real eyewitness route navigator (improved: actual player movement, credible interrogation and finite repair/resolution actions).
- Interactive signed game-world Studio map (improved: user can inspect and safely enact original investigative progress).