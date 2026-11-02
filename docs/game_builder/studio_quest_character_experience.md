# Canonical original quest character experience

This Studio A integration compiles an **already authored and reviewed** branch,
NPC trust ledger, original dialogue script, localization, achievements, pacing,
and content advisories into a single deterministic playable-adapter handoff.
It does not create a new ending, accept external evidence, or claim native
gameplay, audio, player consent outside the supplied receipt, or release proof.

## Operator flow

1. Compile the branch, NPC relationship, and dialogue receipts on one canonical
   original quest source and action history. Complete independent localization,
   achievement, pacing, advisory review and explicit player topic consent.
2. Save each receipt in private 0600 JSON. Run
   `python -m scripts.studio_quest_character_experience_cli --project PROJECT
   --branch-file /private/branch.json --npc-file /private/npc.json
   --dialogue-file /private/dialogue.json
   --localization-file /private/localization.json
   --achievements-file /private/achievements.json
   --pacing-file /private/pacing.json --advisories-file /private/advisories.json
   --accept-topic loud_audio --handoff`.
3. The compiler independently replays all four handoffs and rejects any source,
   session, ending, choice, review, consent or eligibility divergence.
4. `--walkthrough-html` emits an offline, CSP-protected interactive authored
   replay viewer. Previous/next buttons display only the verified chosen route,
   dialogue and applied NPC trust changes; this is not native engine testing.
5. `--publish /private/empty-dir` exclusively persists the canonical receipt.
   `--restore /private/dir` verifies it against fresh replay.

## Adapter contract

The handoff includes canonical stage-choice events with reviewed original NPC
dialogue, earned trust effects, pacing, localized display rows, advisories,
sandbox achievements, final trust and content-addressed source/session/receipt
digests. Downstream builders must independently implement playable input,
scene animation, physics, audio, accessibility, device testing and rights
qualification. This module never marks those as passed.

Source and output sizes are bounded; inputs are private JSON files checked
with the shared nofollow reader. Publication is descriptor-anchored, exclusive,
0600 and fsync-backed. Every input receipt is recomputed rather than trusting
client flags. Skipped, failed, cancelled or stale CI cannot qualify a release.
