# Original NPC dialogue localization

This Studio A vertical translates **already authored and reviewed** NPC
dialogue without altering canonical quest actions, speaker identities,
NPC relationship effects, earned outcomes or original text. The compiler
does not invent translations or certify external translation provenance.

## End-to-end operator flow

1. Create a source-bound original quest, reviewed NPC relationship receipt,
   and reviewed original dialogue receipt on one canonical session.
2. Save both receipts as private 0600 JSON. Propose an editable localization
   with `python -m scripts.studio_quest_dialogue_localization_cli
   --project PROJECT --npc-file /private/npc.json
   --dialogue-file /private/dialogue.json --locale fr-FR`.
3. Save `localization.authoring` as private JSON. Replace each
   `translation` with an operator-reviewed translation, mark `reviewed`
   true, and preserve every immutable source field. `--editor-html` emits
   an offline CSP-hashed editor for existing rows.
4. Run `--plan /private/translation-plan.json --handoff` to recompile.
   The handoff includes exact source/session/dialogue digests, canonical
   choices, target ending and display-only translated lines. Missing reviews,
   reordered rows, changed source text or speakers, stale receipts, and
   unsupported locale fail closed.
5. `--publish /private/empty-dir` exclusively stores the canonical receipt;
   `--restore /private/dir` verifies it against fresh canonical replay.

At most 128 translated lines, 2048 characters per line, 256 KiB plan and
384 KiB receipt. The browser cannot contact the network or write directly
to the game source. Translation review does not establish rights, voice
audio, native gameplay, or release qualification.

## Jeeves typed integration

Trusted app assembly may register read-only capabilities with
`register_dialogue_localization_tools(registry, trusted_documents,
verified_npc_receipt, verified_dialogue_receipt)`. The proposal, compile and
handoff capability IDs are `studio_dialogue_locale_propose`,
`studio_dialogue_locale_compile`, and `studio_dialogue_locale_handoff`.
Every call requires registry authorization and exact source leases; no model
may write files or mark unreviewed translations as playable.
