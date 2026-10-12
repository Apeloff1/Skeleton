# Original Game Studio — Chunked NPC Streaming and Active Detail

Date: 2026-10-12 (Europe/Oslo). Status: draft pending exact-head CI.
Stacked on verified original unified NPC authority PR #3686, Social Quest
Fusion #3684, and prior native Dialogue and Game Studio milestones.

## Concrete executable capability

Original source scene geometry is expanded beyond the first 7x7 game into
3x3 or 5x5 connected chunks of 7 tiles each: actual 21x21 and 35x35 worlds.
The new independent simulation maintains 8-32 stable individually embodied
citizens, while reserving a separate finite detailed schedule budget of
4-16 actors per turn. Inactive residents retain their exact positions and
source identities instead of being teleported or fictitiously simulated.

The four initial authored NPC source roles come from source-verified original
Quest Director scenes; additional citizens are deterministic, entirely
original characters based on the source seed, not hidden imports from third
party games. Each identity has a persistent position, home, workplace, trust,
finite conversational patience, social memories and explicit detailed/deferred
tick counters. A source-origin field distinguishes reviewed authored roles
from generated original expansion roles.

Obstacles are derived from the authored 7x7 geometry. The world preserves
continuous connections between neighboring chunk edges while keeping
original interior obstacles. Player movement and active NPC movement are
always one actual adjacent nonblocked tile. No coordinate wrap or shortcuts.

## Fidelity-preserving NPC detail budgets

The detailed cohort is selected deterministically using a configurable
player-centered chunk radius, actual physical distance and stable actor ID.
Only that cohort receives one legal obstacle-aware, occupancy-safe schedule
step per turn, whether heading to actual home or work. All other residents
retain real last physical locations, accumulate explicit deferred ticks and
produce no phantom movement or source witness events.

A 32-citizen world with an eight-citizen detail budget therefore does not
claim to have simulated 32 complex individuals on every step. Original
visual detail is preserved near the player and bookkeeping exposes precisely
how much detailed simulation was deferred.

Offscreen residents never receive fabricated firsthand memories, quests,
rewards or unseen conversations. Personal social memory expires according
to actual shared time while factual source event provenance remains separately
replayable.

## Gameplay and real consequences

A player can move between chunks, inspect, wait and recover bounded stamina.
Real site harvesting consumes finite original stocks and stamina, records
the factual cell and time, and can originate a causal quest only with
actually present, unobstructed detailed eyewitness citizens. Line of sight
uses true expanded-world width rather than the inherited 7x7 indexing.

Direct speech requires actual spatial presence and an active detailed NPC.
A firsthand testimony binds to a real witnessed event. Public support needs
that exact statement, spends finite influence and supplies, and changes the
same actor's trust, bond and remaining patience. Site restoration requires
all configured paid material followups, followed by an explicit claim.
Unfinished worlds remain playable and retirement is only voluntary after
a real earned milestone. A conversation with no witnessed event cannot mint
quest evidence by guessing or probabilistic inference.

## Replay evidence and tamper defense

Run and verification are independent. Every source execution starts from
typed settings, source-verified original scenes, explicit seed, bounded
chunk/detail options and player action list. Its receipt holds each action,
before/after full-state digests, physical actor movements with both chunk
coordinates, factual witnessed events, ordered phases and chained proof head.

The full game state and every receipt are reconstructed from original inputs,
not accepted from a client-provided state. Tampering with actor positions,
clock, source identity, source stock, reward, witness, detail limits, deferred
counts, event heads or completion claims is rejected.

Content digests detect mutations but are not cryptographic identity signatures.

## Integration and quality

Source module: skeleton/ai/game_builder/advanced_chunked_npc_world.py
Tests: tests/test_game_builder_chunked_npc_world.py
CI: .github/workflows/game-builder-chunked-npc-world.yml

Offline CLI: chunked-npc-world and verify-chunked-npc-world. Both operate on
bounded local JSON inputs.

Authenticated Studio local routes: /api/chunked-npc-world and
/api/chunked-npc-world-verify. Original Dialogue Studio includes actual world
size, citizen count, physical action entry, loaded chunks, active actors,
detail/deferred update metrics, witness receipts and replay status.

A dedicated GitHub Actions matrix verifies source identity, Python syntax,
source-backed real gameplay, adversarial evidence and eight independently
replayed seeded worlds on Ubuntu and Windows. PR-head source identity is
enforced, and stored checkout credentials are disabled.

## Time-stamped improvements

2026-10-12 — Added 21x21 and 35x35 physically joined original worlds
(improves 7x7 geographic coverage without claiming universal game engines).

2026-10-12 — Added 8-32 uniquely embodied source-tagged citizens
(preserves identity and provenance under bounded original expansion).

2026-10-12 — Added deterministic near-player detailed budgets and precise
offscreen deferral (reduces CPU work without fabricating NPC behavior).

2026-10-12 — Added correct world-scale eyewitness geometry, source-linked
conversation and finite material narrative progression
(prevents fake testimony and free milestones).

2026-10-12 — Added cross-platform source replay, tamper tests and
Studio/CLI source custody (improves historical scrutiny and reliability).

## Honest remaining scope

This is a separate reference CPU runtime, not a native Godot 4 execution
certification for chunked worlds. It does not simulate all 32 citizens in
high fidelity while inactive, perform real incremental persistent snapshots,
or provide million-NPC production-scale worlds. Further milestones cover
chunk-resident indexes, coarse simulation with conservation proofs, real
savegame migration, native implementation, more engine families and hardware.

No changes to AI weights, no silent writes to users' source projects and no
merge to the main branch are implied. Keep draft status until exact-head
test gates pass and all stacked parent PRs can be safely integrated.
