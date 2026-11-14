# Historical game-creation convergence: Galaxy cockpit + native quest

This review-only branch stacks on the complete Galaxy → GameForge handoff
(PR #5306, itself stacked on #5296) and incorporates the source-preserving
quest objective/pack/synthesis modules from PR #5304 plus the native Godot
quest bridge and guided creator controls from PR #5310.

## One actual creator workflow
- Existing \`/galaxy\` sends the **entire** full-production design profile:
  14 matrices, 100 extended controls, narrative and style selectors.
- The same \`/skeleton-forge\` Options step can select any historic
  67-genre specialty, set 10 authoritative tensor axes, and opt into
  a 1–8 objective room-entry quest.
- A single \`RunRequest\` can carry \`operator_axes\`, \`galaxy_profile\`,
  \`quest_content\` and \`quest_length\` through the existing Forge client.
- The canonical ten-stage backend validates inputs independently, builds
  the ordinary Godot project, compiles supported matrix decisions into its
  build plan, emits both \`design/galaxy_studio_profile.json\` and the exact
  room-seeded \`data/quest_slice.json\` + autoloaded GDScript quest runtime.
- The standard static checker, source manifest, project custody and
  completion ledger now cover both authoring provenance and quest gameplay
  source. The response shows both independent SHA-256 receipts.

## Source reconciliation
The branch copies original archived B028/B030/B037 modules unchanged from
their repaired exact heads, then adapts only overlapping UI/frontend types,
\`backend/routes/skeleton_gameforge.py\`, and
\`skeleton/context/pipeline.py\` to avoid clobbering the recovered sliders,
Galaxy profile or existing build pipeline. Both single-feature PRs remain
intact for review and focused CI. The convergence branch is not an
alternative Git history rewrite.

## Limits and qualifications
A real native room-entry quest is implemented. Neither the 67 named genres
nor the 14 matrices imply all specialized gameplay systems are implemented.
Offline save provenance is local replay consistency, **not anti-cheat
authentication**. Independent physical device, Godot headless runtime,
Windows, user-mode local AI and recovery acceptance remains mandatory.

Run focused \`python -m pytest -q skeleton/testing/test_historical_gameforge_convergence.py skeleton/testing/test_native_godot_quest.py skeleton/testing/test_original_quest_slice.py skeleton/testing/test_galaxy_profile.py\` and
\`cd frontend && node --test scripts/skeleton-forge/historical-convergence.test.cjs scripts/skeleton-forge/native-quest.test.cjs scripts/skeleton-forge/galaxy-handoff.test.cjs\`.
Then full exact-head frontend/backend/security/source-parity/E2E/device gates.
No merge or release before successful final SHA qualification.
