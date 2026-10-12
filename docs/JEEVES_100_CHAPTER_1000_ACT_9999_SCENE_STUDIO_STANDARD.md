# Jeeves game-story production baseline — 100 chapters / 1,000 acts / 9,999 scenes

**Baseline declared:** 2026-10-13 (Europe/Oslo). **Status:** draft production contract implemented on PR #3718, pending exact-head CI and merge review. This supersedes the 100-act-only draft baseline.

## Canonical structure and semantics

The production target is **100 chapters**, containing **10 consecutive global acts per chapter**, and **9,999 scenes altogether**. An act ID does not restart within the next chapter: chapter 1 contains acts 1–10, chapter 2 contains acts 11–20, and chapter 100 contains acts 991–1000. Each act's scene numbering begins at 1 and increments without gaps; a chapter/act transition must be explicitly authored. The scene count is not 9,999 per chapter or act.

The strict source filename is `story/chapters/chapter_001/acts/act_0001/scene_000001.json`; the final scene ends in chapter 100/act 1000. Each scene has an independently verifiable confirmation receipt and a hash-linked predecessor. The original reviewed story, world, cast, region color/style and consented voice-master identity remain bound at all times.

## Industry-style story forms and pacing

Every scene has typed storytelling direction with `prologue`, `prelude`, `main`, `interlude` or `epilogue`; a pacing tier; numerical suspense entering and leaving the scene; stakes, the dramatic question, and an authored hook; a chapter ending status; highlighter bookmarks; and a cinematic editor record (camera, cutting, performance, soundscape and continuity notes). A prologue/prelude is valid at chapter opening; interludes occupy supporting moments inside a chapter; an epilogue must resolve an earlier plot question. The story ending—and every completed chapter ending—must be either a **cliffhanger** or a **resolution**. A resolution must cite a previously opened highlighter. An ending with no actual rise in narrative tension is rejected.

This is a **structural dramatic-quality gate**. Subjective suspense, actual professional-level screenwriting, natural facial acting, timing of shot transitions, cinematography, voice acoustics and cinematic visual quality still require expert and rendered-media review. Numeric suspense alone cannot establish engaging writing.

## Plot highlighter system

A plot marker has a globally unique ID, authored category/color, importance 1–5, review note, and a direct pointer to an actual scene event, dialogue line, interaction or beat. Categories include foreshadowing, revelation, conflict, motivation, relationship, prop, suspense, payoff. Markers have canonical editor colors, not guesses from the generative model.

When Jeeves opens a chapter, the chapter-scoped context includes (1) all verified current-chapter scene text if the context remains within a **1.5 MB** byte budget; (2) the current chapter's precise source/receipt references and plot highlighter ledger; (3) unresolved highlighters from earlier chapters; (4) a bounded list of previous chapter-ending receipts; and (5) canonical character/world state. Oversize chapter texts remain accessible by source ID and are marked explicitly as not fully embedded. No false claim of infinite context, silent omission or globally perfect model memory is permitted.

A dedicated highlight lookup returns the exact original event/beat/line, source digest, stage receipt, chapter/act/scene location, open/closed status and provenance. Model-generated recollections must be grounded in these records.

## Quality-control enforcement

Each scene is submitted **one at a time**. Before a new scene's receipt, the full historical story is reparsed. Its source schema, scene coordinates, chronology, canonical world state, voice-master fingerprint, face identity, expression per spoken line, clothing variations, item custody, rights attestation, original region color/style, plotting, suspense, closure and highlight references must match. The confirmation receipt binds the new source, all previous receipts, and independent state projections; review and exact-file authorization are still needed before storing the scene.

For studio tools, source stage templates, Jeeves work orders and the conversational creative instruction API, unapproved canon or a missing active chapter is a hard stop. For chat, the `active_chapter_context` is attached to the source-bound Jeeves work order. For Studio, a chapter selector, chapter highlighter panel, exact source lookup and stage-reparse control expose continuity evidence visibly.

## Change control and migration

The strict contract and receipt signatures are **version 2**, not a silent relabeling of the earlier v1 100-act ledger. Existing v1 signed receipts must not be edited in place or claimed as valid v2 receipts; any migration of real accepted v1 projects must preserve archived source evidence, reassign chapter/act identities under an explicitly reviewed plan, and issue new author-approved evidence receipts. This PR is still draft and does **not** implement such a migration tool. The legacy scene schema remains separately verifiable, and strict v2 projects require explicit adoption before production.

## What has and has not been delivered

Implemented here: 100/1,000/9,999 chapter structure; scene-by-scene append-only source, full reparse, deterministic evidence receipts, original character and item/voice/color locks, chapter context, exact plot-highlighter lookup, suspense/closure rules, prologue/prelude/interlude/epilogue typing, and Studio/Jeeves APIs and editor controls.

Not proven or implemented as part of this milestone: live Jeeves model authoring; a complete 9,999-scene playable game; automatic voice-similarity checks on rendered speech; generated frame/lip-sync or movie-quality certification; a standalone consumer chat UI integration outside Game Studio; professional narrative enjoyment proof; an actual finished legal/IP review; and automatic migration of v1 accepted projects.

## Subsequent mandatory milestone lanes

1. Production provider bridge for governed original model drafts, source staging, retrieval-augmented chapter chat, story editor approval and deterministic dialogue analysis.
2. Cross-media identity verification: speaker embeddings/spectrograms, lip-sync and facial consistency, costume/item image continuity, per-shot lighting/material/palette/style, original-animation temporal consistency.
3. Studio cinematic timeline: shot graph, camera grammar, continuity between angles, editable VO tracks, ambience, soundscape, music cues, scene-to-game interactions, render reviews and artifact audit trails.
4. Scale: sharded per-chapter indexes, source deduplication, bounded context assembly, incremental proof checkpoints with mandatory full reparse, timed deterministic replay, adversarial negative tests and graceful failure.
5. Playtest and scene-signoff gates: thematic cohesion, pacing, NPC behavior, player agency, non-linear ending alternatives, original-work scrutiny, accessibility/localization, hardware targets and release-grade validations.

**Continuity objective:** no *known source-level* inconsistency may pass certification. Claims of literally guaranteed 100% story, audio or visual quality would exceed what deterministic validation can prove.
