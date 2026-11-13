# Galaxy Studio → GameForge: complete design profile handoff (2026-11-13)

## Scope and lineage

This is a stacked follow-on to recovery PR #5296. The historical source is
the existing production \`frontend/src/features/GalaxyStudioFactory/
GalaxyStudioFactoryModal.tsx\` and 14 \`QuestionnaireMatrices.tsx\` matrices,
the narrative phase sliders, \`extraParams.ts\`, \`styleSliders.ts\`, 29 classic
sliders, era selectors, multi-genre fusion and Production Studio.

Prior to this branch, the advanced Galaxy Studio question/slider values were
sent to \`/api/galaxy-studio/create\`, whereas GameForge's modern
\`/api/skeleton/run\` understood only a five-step brief plus 10 tensor axes.
This patch **does not replace** either existing build engine.

## User-facing connected creation journey

1. Open \`/galaxy\`, set game title, primary genre, optional multi-genre fusion,
   story/visual preferences and as many phase sliders as desired.
2. The new explicit **Continue full questionnaire in GameForge** action, shown
   in both Quick and Advanced modes, captures the *same* payload object used
   for the original Galaxy build. There is no duplicated hand-coded subset.
3. The captured, versioned profile is validated, bounded and cloned. One
   handoff is stored only in JS memory with a 10-minute expiry and single-use
   ID; only that short ID is passed in the route. URL does not contain text,
   model instructions, identities, project data or secrets.
4. \`/skeleton-forge?tab=build&handoff=<opaque-id>\` consumes the profile.
   The GameForge questionnaire receives the title, vision, Galaxy genre
   specialization, mapped supported broad genre and explicit observable
   tensor axes for tempo, difficulty-risk, narrative agency and visual
   spectacle. The remaining 6 instrument axes remain automatic and can be
   edited in the recovered panel. The user reviews before building.
5. On \`POST /api/skeleton/run\`, the entire inert profile is validated in
   \`skeleton.context.galaxy_profile\`, hashed into ingest/emit custody and
   included at \`design/galaxy_studio_profile.json\` in the emitted Godot
   project source. The normal source manifest hashes this file, and the
   HTTP result returns the profile SHA-256 and whether it was actually
   emitted. No server-global cross-project cockpit state is introduced.

## Preservation and safety

The complete Galaxy source payload preserves:
- 14 matrices: mechanics, world, art, audio, tech, monetisation, QA, agent,
  vector DB, plagiarism, RDBMS, styles, mutation, unique flair.
- Narrative phase-by-axis values; 100+ extra parameters and production
  multi-selects; nine style pickers and both era controls.
- Standard gameplay, production, animation, world and audience selectors,
  title/genre fusion, user-authored description, system and world notes.

The handoff schema is \`skeleton.gameforge.galaxy_profile.v1\`, is bounded to
450k JavaScript characters / 600k ASCII canonical bytes, rejects unsupported
depth/types, object prototype keys, nonfinite slider values, invalid phases
and matrix-axis values. Failure cannot turn the handoff into arbitrary code
execution or project writes; the existing current output path validator,
GDScript static checker and source manifest still govern publication.

There is **no account-wide project sync** yet; a per-device transient
handoff is not an authenticated cross-device project store. Profiles are
saved in the **emitted project output**, not automatically in an
authoritative tenant-scoped draft database.

## Functional depth and explicit limitations

The full profile reaches the actual canonical build artifact and source
manifest. Four semantically direct controls enter the working GameForge
tensor. An explicit positive `mechanics_matrix.ranged.count` or
`mechanics_matrix.gunplay.count` also enables `spawn_weapon` in the
real `BuilderBrain` plan used by the Godot emitter; this affects the
starting-weapon flag in emitted GameState and `data/build_plan.json`.
A deterministic `galaxy_mechanics` response receipt reports the applied
field, source keys and count of **unmapped** active matrix dials. The title,
specialized genre, visual tone/style and user-authored vision also reach
the vision-based composer.

The original 14 matrices are **preserved as first-class inputs**, but every
individual matrix axis does not yet independently mutate generated Godot
gameplay. Connecting all axes to dedicated mechanics, assets, stories,
simulation, evaluation and native playable outputs requires separate
per-domain adapters and acceptance tests. Do not represent a safely
preserved design as already fully generated gameplay.

## Qualification

After creating the complete candidate branch:
- \`cd frontend && node --test scripts/skeleton-forge/galaxy-handoff.test.cjs\`
- \`cd frontend && yarn test:skeleton-forge && yarn typecheck\`
- \`python -m pytest -q skeleton/testing/test_galaxy_profile.py
  skeleton/testing/test_gameforge_instrument_overrides.py\`
- Exact-head Merge Readiness, Backend Quality, App E2E, source/mirror parity,
  secrets, dependency, malware, artifact, hygiene and workflow-input guards
- Native Godot/Windows 11/WSL2/device input and real local model acceptance
  tracked independently; skipped or queued gates are not passes.

No launch or first-install qualification claimed.
