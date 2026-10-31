# Forge Studio — 500 billion indexed source compositions, 100 million addressable manuals

This is a **tenfold compositional extension** of the 50-billion-operation Forge Studio implementation on PR #4200. The new `epoch_` generation introduces **450 billion distinct registered composition identities**, each resolving to one of ten *implemented* temporal editing patterns over an existing authenticated StudioProject and the preceding chronicle writer.

- Existing 50B action identities remain stable at their original indexes.
- Epoch actions: ten concrete geometric variants for daybreak, nightfall, thaw, drought, trade, winter shelters, flood recovery, post-siege repair, regrowth and future convergence.
- Source changes: execute the registered parent chronicle edit, mutate canonical map cells within bounds, append an independently identified typed observed RPG event, and refine only actors/quests newly created within this transaction. Atomic preview/commit use the existing host-owned workspace CAS and receipts.
- Query: authenticated `GET /api/game-frontier-authoring/recipes?generation=epoch`, using exact domain/system/director/finish/worldline/phase/campaign/chronicle/epoch filters and O(page size) arithmetic rank/unrank.
- Manuals: **90 million new on-demand epoch manuscripts**, extending 10 million prior addressable source manuals to 100 million total. They are virtual identities, not 90 million files committed to Git.
- Manuscript paths: `/api/game-frontier-authoring/epoch-handbooks/{domain}/{treatment}/{director}/{worldline}/{phase}/{campaign}/{chronicle}/{epoch}`; the `rank` endpoint renders ten variants of one source context and ranks by measured word count and objective structural completeness.
- Bounded physical export: `python -m scripts.export_game_studio_epoch_handbooks --out build/epoch-manuals --offset 0 --limit 10`. The materializer uses exclusive creation, checks UTF-8 byte SHA-256, and emits a manifest plus two actual-batch rankings.
- Product: the existing Jeeves Forge editor browses, previews, saves and renders epoch manuals, without a second persistence or external model-provider boundary.

## Qualification boundary

A virtual source combination is **not** a separately authored game, a new game engine, a native binary, an AI checkpoint, a completed playthrough, a legal clearance, or commercial-quality artwork. Structural manuscript grades must never be presented as measured gameplay quality.

Before production signoff, verify exact-head Python and TypeScript compilation, focused tests, real Godot map loading and controller playthrough, savegame roundtrip, authorization/CAS concurrency, performance profiling, source-IP review, and two independent reviewers. Do not merge on unverified CI.
