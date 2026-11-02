# Locale-consistent original character experience

This Studio A integration composes original authored NPC dialogue translations
with a source-replayed character experience. It rejects mixed stage/dialogue
locales, mismatched canonical choices, altered speaker identities, stale
source/session/ending digests, unreviewed lines and missing player consent.

## Operator workflow

1. Author and review a quest, branch, NPC relationship receipt, original NPC
   dialogue, stage localization, achievements, pacing and content advisories.
2. Translate the original dialogue into the **same locale** as the stage
   localization, with explicit review on every line.
3. Save all eight receipts in private 0600 JSON. Run
   `python -m scripts.studio_quest_character_locale_cli --project PROJECT
   --branch-file /private/branch.json --npc-file /private/npc.json
   --dialogue-file /private/dialogue.json
   --dialogue-locale-file /private/dialogue-locale.json
   --localization-file /private/localization.json
   --achievements-file /private/achievements.json
   --pacing-file /private/pacing.json --advisories-file /private/advisories.json
   --accept-topic loud_audio`.
4. The output contains ordered localized dialogue per canonical action,
   original dialogue for provenance, NPC trust effects, pacing, stage labels,
   advisory descriptors, sandbox achievements and exact digests.
5. `--review-html` produces a CSP-protected read-only offline walkthrough.
   `--publish /private/empty-dir` stores an exclusive source-bound handoff;
   `--restore /private/dir` verifies the stored receipt against fresh replay.

No output attests native gameplay, audio, translation rights, external evidence,
device acceptance, or release readiness. The downstream engine must implement
those independently. All source, receipt and HTML outputs are bounded, and
private file reads reject unsafe paths.

## Jeeves adapter

Trusted app assembly can register `studio_quest_character_locale` using
`register_quest_character_locale_tool(registry, trusted_documents, branch,
npc, dialogue, dialogue_locale, localization, achievements, pacing,
advisories, accepted_topics)`. This capability requires explicit registry
authorization, `dry_run=False`, the exact source digest and expected locale.
It has no filesystem write capability and rejects mutated inputs.
