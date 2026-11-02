# Original quest NPC dialogue — Studio A

This vertical adds authored, reviewed NPC dialogue to a **canonical played
quest session** and a separately replay-verified NPC relationship receipt.
It is not machine translation, generated voice, inferred character behavior,
or external evidence.

## End-to-end workflow

1. Create an original quest and a reviewed NPC relationship receipt.
2. Save the relationship receipt in a private 0600 JSON file. Run
   `python -m scripts.studio_quest_dialogue_cli --project PROJECT
   --npc-file /private/npc.json` to obtain a typed draft with one unreviewed,
   empty dialogue beat per played quest action.
3. Save the `dialogue.authoring` plan in a private file. Write original lines,
   select speakers from the exact NPC roster, and mark each beat reviewed.
   Up to four sequential beats may be authored for each action; every played
   action requires at least one beat.
4. Use `--plan /private/dialogue-plan.json --editor-html` to edit/export
   existing beats offline. The browser is not trusted as a compiler.
5. Use `--plan /private/dialogue-plan.json --handoff`. The canonical quest
   session, original NPC relationship digest, target ending and every reviewed
   dialogue line must all agree. Unreviewed or empty lines fail closed.
6. `--publish /private/empty-dir` writes an exclusive private receipt;
   `--restore /private/dir` replays it against current authoritative source.

## Runtime boundary

The handoff carries ordered original dialogue text, speaker IDs, delivery
hints, canonical quest actions and source/session/relationship digests. The
game engine must implement its own speech bubbles, timing, localization,
NPC animation, audio, user consent and device qualification. This module
claims none of those.

The plan is bounded to 128 lines, 64 canonical actions, four lines per
action, 192 KiB typed plan, and 256 KiB receipt. A strict CSP-hashed offline
editor escapes text and does not contact the network. Duplicate, skipped,
out-of-order, forged-speaker, stale-session and unreviewed inputs are rejected.

## Jeeves typed capability integration

The trusted app assembler may opt into
`register_quest_dialogue_tools(registry, trusted_documents, verified_npc_receipt)`.
The `studio_quest_dialogue_propose`, `studio_quest_dialogue_compile`, and
`studio_quest_dialogue_handoff` adapters are read-only, source-leased, and
require explicit registry authorization and non-dry-run execution. They cannot
write a file, create NPC facts, or bypass the canonical quest/relationship
replay. The NPC receipt and source are pinned at registration.
