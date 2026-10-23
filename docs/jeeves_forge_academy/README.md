# Jeeves Forge Academy — operational curriculum and real book manifestation

The Forge Academy lives inside the existing authenticated Jeeves Game Frontier authoring cockpit. This is not a separate LLM trainer or a forked studio.

## Implemented now

Seven real, sequential source-book families (**Worldline, Phase, Campaign, Chronicle, Epoch, Saga, Epic**) address **9,999,999,000 exact indexed manuals**. The separate original-world baseline books account for the remaining total of **10 billion addressable books**. Each source reference is reversible, its actual Markdown can be rendered on demand, and selected books can be downloaded in a deterministic, SHA-verified ZIP (one to four selected books).

New `skeleton/jeeves/game_frontier_curriculum_path.py` constructs a complete 1–7-level prerequisite chain from any exact reference, signs each unit with source-derived SHA-256, and generates 1–16-session bounded study programs without inventing GPU execution, issued jobs or trainer state. Existing `skeleton/jeeves/game_frontier_book_curriculum.py` provides the source registry, lessons, exact-axis assessments and real manuscript renderer. Both modules call only original Forge owners.

Host-authenticated routes:
- `GET /api/game-frontier-authoring/curriculum`
- `GET /api/game-frontier-authoring/curriculum/book/{generation}/{index}`
- `GET /api/game-frontier-authoring/curriculum/path/{generation}/{index}`
- `GET /api/game-frontier-authoring/curriculum/worklist?generation=epic&index=0&sessions=8`
- `GET /api/game-frontier-authoring/curriculum/lesson/{generation}/{index}`
- `POST /api/game-frontier-authoring/curriculum/assess/{generation}/{index}`
- `GET /api/game-frontier-authoring/curriculum/manifest/{generation}/{index}`
- `GET /api/game-frontier-authoring/curriculum/download/{generation}/{index}`
- `POST /api/game-frontier-authoring/curriculum/download` (1..4 exact books as a ZIP)

Jeeves' actual agent tool surface already contains the exact Studio operations and routes through the current game's project authority: `game.studio.curriculum.catalog/reference/lesson/path/worklist/assess/practice`, `game.studio.book.manifest`, and the separate `game.studio.curriculum.automation.plan/preview/commit` chain. The approval hash, source revision and ownership checks prevent silent model-driven saves.

**In-app:** `GameFrontierCurriculumPanel`, embedded inside `GameFrontierAuthoringPanel`. Browse levels, load genuine book references, resolve prerequisites, manifest full Markdown, study a controlled eight-session worklist, answer theory questions, plan an exact registered source operation, preview its actual changes, and approve one exact current candidate hash before committing. Refresh the parent project after commit.

## Seven physical curriculum volumes

1. [Orientation to original-world authoring](volumes/01_worldline.md) — Foundational world and spatial source provenance.
2. [Seasonal, temporal and physical phase composition](volumes/02_phase.md) — Worldline prerequisite plus time-dependent real source effects.
3. [Multiact scene and faction campaign construction](volumes/03_campaign.md) — Worldline and phase prerequisite plus composition through regional campaigns.
4. [Longform 100-chapter/act/scenes continuity control](volumes/04_chronicle.md) — All earlier prerequisites plus signed source-linked narrative arc.
5. [Century-spanning ecological and historical change](volumes/05_epoch.md) — Chronicle prerequisite plus temporal world evolution.
6. [Epic storytelling, cast staging and branching aftermath](volumes/06_saga.md) — Epoch prerequisite plus narrative choice-sensitive regions.
7. [Cross-region high-scale layered world orchestration](volumes/07_epic.md) — Saga prerequisite plus epic multidisciplinary production.

## What it means to train Jeeves

Source-book comprehension and host-authorized source practice are **implemented**. There is no claim that the model has ingested the entire virtual catalogue or undergone gradient updates: materialize requested volumes only as needed. A true weight-training workflow must run via an already authorized model-training plane with corpus rights checks, checkpoints, independent evaluation, accepted promotion and actual persisted evidence. Reading or generating a worklist cannot substitute for that. Persistent certification of student mastery also requires host-owned evidence storage and independent assessment, rather than manufactured in-memory flags.

## Real verification and limits

`skeleton/testing/test_game_frontier_book_curriculum_operational.py` probes stable reference indexing at all seven levels, source exercises, true manuscript/ZIP hashes, bounded study sessions, prerequisites, source edits, canonical owner/CAS approval and failure cases. Follow exact-head CI for results; native playthrough, stable long-duration automation, licenses and neural training remain distinct release qualifications.
