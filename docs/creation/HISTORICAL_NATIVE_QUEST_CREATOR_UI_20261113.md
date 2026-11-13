# Recovered native quests in the guided GameForge questionnaire

The archived B028/B030/B037 quest recovery is not only an API-level prototype.
This branch makes its opt-in \`quest_content\` and bounded \`quest_length\`
controls available in the existing five-step \`/skeleton-forge\` creator flow.

The Forge Options step exposes an explicit **Room-entry quest** mode, disabled
on JSON-only output, and choices for 1–8 native objectives. Review & Forge
shows the exact proposed gameplay contract. The serialized \`RunRequest\`
includes \`quest_content: true\` and \`quest_length\` **only** for opted-in Godot
projects. Legacy calls remain byte-for-byte unchanged.

The existing \`useForgeRun → runForge → POST /api/skeleton/run\` transport
forwards the new optional fields without a bespoke runner, project override,
backend global state or intermediate fake generator. Native quest GDScript,
source manifest, quest HUD, runtime receipts and replay checks are attached
by the normal backend GameForge pipeline.

This UI is intentionally separate from PR #5296's larger Galaxy Studio
questionnaire recovery. The final reconciliation must combine both option
groups and shared types without dropping either. A genre name or quest choice
does not establish that a full RPG, NPC system or native device is qualified.

Focused tests:
\`cd frontend && node --test scripts/skeleton-forge/native-quest.test.cjs\`,
then \`yarn test:skeleton-forge && yarn typecheck\`. Check backend quest tests
and exact-head required CI before main merge.
