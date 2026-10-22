/**
 * Jeeves native-first cross-forge production flows.
 * The flow catalog is a navigable set of real production intents; the
 * authenticated studio goal runner (never this module) owns execution.
 */
export type StudioFlow = {
  id: string;
  title: string;
  purpose: string;
  stages: readonly string[];
  finish: string;
};
export const JEEVES_STUDIO_FLOWS: readonly StudioFlow[] = [
  { id: 'full-production', title: 'Original game · complete production',
    purpose: 'Take an original brief through source authoring, a playable game and evidence-backed packaging.',
    stages: ['vision','scope','platform','engine','canon','world','map','pathing','story','cast','dialogue','npc','quests','movement','combat','physics','weather','economy','inventory','progression','puzzles','scene_forge','sprite_forge','asset_forge','animation_forge','audio_forge','lighting_forge','cinematics','ui','ux','accessibility','localization','multiplayer','playtest','qa','release'],
    finish: 'Playable complete-loop game, measured reviews, source/export manifests and real runtime evidence' },
  { id: 'narrative', title: 'Narrative · canon to endings',
    purpose: 'Write a connected playable story instead of isolated prose.',
    stages: ['vision','canon','world','cast','story','dialogue','npc','quests','cinematics','qa'],
    finish: 'All choices and endings connected to consistent canon, dialogue, quest state and scenes' },
  { id: 'world', title: 'World · routes and systems',
    purpose: 'Build contiguous explorable regions with credible routes, terrain and societies.',
    stages: ['canon','world','map','pathing','weather','economy','npc','scene_forge','physics','playtest'],
    finish: 'Traversable world with witnessed route/portal connectivity and spatial continuity' },
  { id: 'combat', title: 'Gameplay · controls to tuning',
    purpose: 'Create and tune coherent movement, combat and progression loops.',
    stages: ['scope','movement','physics','combat','inventory','progression','puzzles','ux','playtest','qa'],
    finish: 'Actual playable input-to-outcome loops and reproducible gameplay evidence' },
  { id: 'asset-descriptors', title: 'Asset descriptors · authored & measured',
    purpose: 'Create and review semantic descriptors for actual sprites, sounds and 3D game assets; verify revisions, alt text, roles, rights and source hashes.',
    stages: ['canon','asset_forge','sprite_forge','audio_forge','accessibility','localization','qa'],
    finish: 'Indexed revision-pinned asset catalog with real bytes, reviewed semantics and independently replayed receipts' },
  { id: 'original-3d', title: 'Original 3D · mesh & materials',
    purpose: 'Compile true original parametric geometry with GLB 2.0 meshes, correct normals and authored metallic-roughness materials.',
    stages: ['asset_forge','lighting_forge','scene_forge','physics','accessibility','playtest','qa','release'],
    finish: 'Actual replayed indexed GLB meshes in a source-bound Godot package; native import/rendering separately observed' },
  { id: 'assets', title: 'Asset pipeline · original art',
    purpose: 'Produce consistent owned assets and apply them to working scenes.',
    stages: ['canon','sprite_forge','asset_forge','animation_forge','lighting_forge','scene_forge','ui','playtest','qa'],
    finish: 'Versioned asset manifests, integrated scenes and observed rendering rather than placeholder names' },
  { id: 'sound', title: 'Sound · music to synchronized scenes',
    purpose: 'Make adaptive original sound fit gameplay, spatial effects and cinematic cues.',
    stages: ['audio_forge','cinematics','animation_forge','scene_forge','accessibility','playtest','qa'],
    finish: 'Rendered mixes, timing and accessibility observations backed by actual assets' },
  { id: 'physics', title: 'Physics · environment and vehicles',
    purpose: 'Author and review weight, traction, forces, gravity and traversal behavior.',
    stages: ['physics','movement','weather','map','pathing','scene_forge','playtest','qa'],
    finish: 'Measured physical behavior in the selected real engine across representative cases' },
  { id: 'platforms', title: 'Portability · era and target SDK',
    purpose: 'Prepare actual runtime variants according to approved target environments.',
    stages: ['platform','engine','scope','ui','accessibility','asset_forge','playtest','release'],
    finish: 'Target-specific original builds with independently observed native execution where available' },
  { id: 'simulation', title: 'NPCs · factions and persistent worlds',
    purpose: 'Create autonomous schedules and consequential society/game state.',
    stages: ['canon','cast','npc','progression','economy','quests','dialogue','multiplayer','playtest','qa'],
    finish: 'Persistent NPC/quest/faction outcomes with simulated and authored continuity evidence' },
  { id: 'multiplayer', title: 'Multiplayer · state and recovery',
    purpose: 'Build and validate synchronized multi-peer flows.',
    stages: ['engine','multiplayer','movement','combat','inventory','ui','qa','release'],
    finish: 'Reproducible state sync, recovery and authority observations from actual peers' },
  { id: 'accessibility', title: 'Accessibility · interaction and language',
    purpose: 'Make complete game interaction available across supported needs and languages.',
    stages: ['accessibility','localization','ui','ux','audio_forge','playtest','qa'],
    finish: 'Reviewed controls, localized text and measured accessibility acceptance' },
  { id: 'ai-learning', title: 'Jeeves · books, weights and delegation',
    purpose: 'Use only rights-approved complete source texts and independently assessed model candidates.',
    stages: ['training','delegation','canon','qa','playtest'],
    finish: 'SHA-pinned full-book coverage, candidate checkpoint, independent held-out results and no automatic promotion' },
  { id: 'release', title: 'Release · audit and delivery',
    purpose: 'Close open gameplay, code, source and package gaps before shipping.',
    stages: ['scope','qa','playtest','accessibility','localization','platform','release'],
    finish: 'Exact-head build, native gameplay proof, provenance, rollback and verified export receipt' },
] as const;

export function composeStudioFlow(
  flow: StudioFlow, answers: Readonly<Record<string, string>>,
  sourceReference: string, selectedFacet: string,
  stageStart = 0, stageCount = 6, previousReceipt?: string,
): string {
  if (!Number.isSafeInteger(stageStart) || stageStart < 0 ||
      stageStart >= flow.stages.length || !Number.isSafeInteger(stageCount) ||
      stageCount < 1 || stageCount > 8) {
    throw new Error('The production flow chunk is outside the bounded stage window.');
  }
  const activeStages = flow.stages.slice(stageStart, stageStart + stageCount);
  if (!activeStages.includes(selectedFacet)) {
    throw new Error('The selected capability is outside the current production slice.');
  }
  const sections = [
    'Jeeves standalone game-production flow: ' + flow.title,
    'Flow identity: ' + flow.id,
    'Production purpose: ' + flow.purpose,
    'Requested acceptance: ' + flow.finish,
    'This slice: stages ' + (stageStart + 1) + ' through ' +
      (stageStart + activeStages.length) + ' of ' + flow.stages.length,
    'Previous slice receipt (reference only; verify server-side): ' +
      (previousReceipt || 'first slice; no prior verified execution'),
    'Project canon and source revisions override any inferred detail.',
    'The following are authored production STAGES, not executed actions:',
  ];
  activeStages.forEach((facet, index) => {
    const value = answers[facet]?.trim();
    sections.push(String(stageStart + index + 1) + '. ' + facet + ': ' +
      (value ? value : 'Propose choices or request the missing user decision'));
  });
  if (sourceReference.trim()) {
    sections.push('User-provided reference, pending media and rights verification: ' +
      sourceReference.trim());
  }
  sections.push('Current editing focus: ' + selectedFacet);
  sections.push('Do not claim the remaining ' +
    (flow.stages.length - stageStart - activeStages.length) +
    ' downstream stages were executed. Preserve them as outstanding work.');
  sections.push('Use the installed local Jeeves model. Partition execution into bounded, ' +
    'dependency-ordered existing creator runbooks and saved studio goals. Preserve ' +
    'canon, project revision, identity, scope and the complete outstanding backlog.');
  sections.push('For every actual effect obtain explicit host authorization, observe ' +
    'the existing editor/forge mutation, persist source and result digests, and ' +
    'verify postconditions. Never claim training, model promotion or gameplay without proof.');
  return sections.join('\n');
}
