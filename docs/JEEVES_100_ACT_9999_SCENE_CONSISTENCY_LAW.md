# Jeeves — 100 Acts / 9,999 Scenes: Canon and Continuity Law

**Created 2026-10-13 (Europe/Oslo).** Change sequence: original source bible → characters → regional art and assets → strict identity contract → one accepted scene at a time. The deliverable is **the AI game-production environment**, not a pre-authored game.

## Hard operational rules

1. The authored source bible declares **100 acts**. The signed `game/continuity_contract.json` reserves **9,999 total scenes**, not 9,999 scenes per act. Act-scene coordinates must begin at act 1 scene 1, advance by one within an act, and begin at scene 1 in the immediately following act.
2. Each actor has an original, immutable voice ID and SHA-256 reference-audio/master fingerprint. The source cast contract binds the approved voice style, language and accent. Scene observations must reproduce the same identity/fingerprint; the voice may not silently change.
3. Every character has permanent facial geometry—eyes, nose, mouth shape, jaw and skin features—and an immutable face ID. Each spoken line needs an explicit intent-to-expression mapping; the source verifier rejects dialogue mismatches or swapped character faces.
4. Clothes require named variants, fabric/detail descriptions, canonical palettes and an event-backed outfit change in the historical narrative. An unexplained costume, recolor or location jump fails.
5. Each item has a persistent original identity, approved art asset, region style and initial owner. Every transfer must cite an actual event in the current scene, preserve ownership, and be visible in the scene's exact asset manifest. Double-presented or unrecorded equipment fails.
6. Regions carry locked style IDs, eras, palettes, architecture and material vocabularies. Every scene's observation must match the original region specification. Original PNG palette inspection is an additional visual-source check; checking hex palettes alone does not prove visual-semantic likeness.
7. Every new scene is a **separate source edit** requiring human review. Each has a cryptographically linked `assurance` receipt containing 15 independent QC gates and the immediately preceding confirmation receipt digest. Altering any previous source invalidates its source signature and all subsequent lineage.
8. A **full history reparse** is required for strict scenes, from act 1 scene 1 through the current stage, before issuing the next receipt. Cached previews, model memory, self-declared proof and summaries cannot override the reparse. The full historical index retains dialogue pair bookmarks, character states, wardrobe, item transfers and source digests.
9. The 9,999-stage synthetic stress test creates a complete 100-act sequence, then independently reparses the entire chain, comparing source head, receipt head, item/character state and the final act distribution.
10. No external inference, asset creation or training is represented as completed merely because a model-ready brief or signed source specification exists. Rights-review metadata is an attestation, not a legal ruling.

## Human studio operating path

- Create an original project and sign `game/story_bible.json` first as **foundation**, then **cast**, then **design**.
- Obtain `/api/story-continuity-template` and fill all source voice, face, wardrobe, asset and regional identities; sign and explicitly approve `game/continuity_contract.json` **before** authoring a scene.
- Request `/api/story-scene-template` for the **next** scene. Jeeves must reference the full historical source index and produce original beats, scene event chain, dialogue, interactions and a scene media/identity observation.
- Use `/api/story-sign` with the scene draft and its `observations`; the server independently validates history and seals a confirmation receipt. Review the diff and approve the exact-file commit.
- Use `/api/story-stage-confirmation` to reparse all accepted stages. Use `/api/story-detail-timeline` to retrieve the exact past cast appearance, voice source, clothing, facial expression, dialogue, item possession and region style without depending on ungrounded LLM recall.

## Independent evidence and boundaries

The tests reject mutated voice IDs/master fingerprints; substituted faces or geometry; unapproved clothes/colors; incorrect dialogue expression; out-of-era regional architecture; forged item transfers; missing observations; out-of-order scenes; and corrupted hash-linked receipts.

**Important:** The verifier locks source specifications and declared audio master fingerprints. It does **not** yet perform acoustic speaker verification of new voice recordings, facial recognition in generated video, automatic lip-sync, actual image identity beyond the bounded PNG and pixel equality checks, or comprehensive copyright clearance. Those need separate model/media render verification before asserting finished production quality.

The exact-head workflow validates source replay on Windows and Ubuntu. Only actual CI success for the latest SHA counts as validated; successful testing of an earlier commit is not release qualification. Draft PR #3718 is stacked on upstream draft Game Builder #3642.
