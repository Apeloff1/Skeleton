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
): string {
  if (!flow.stages.includes(selectedFacet)) {
    throw new Error('The selected capability is outside this production flow.');
  }
  const sections = [
    'Jeeves standalone game-production flow: ' + flow.title,
    'Flow identity: ' + flow.id,
    'Production purpose: ' + flow.purpose,
    'Requested acceptance: ' + flow.finish,
    'Project canon and source revisions override any inferred detail.',
    'The following are authored production STAGES, not executed actions:',
  ];
  flow.stages.forEach((facet, index) => {
    const value = answers[facet]?.trim();
    sections.push(String(index + 1) + '. ' + facet + ': ' +
      (value ? value : 'Propose choices or request the missing user decision'));
  });
  if (sourceReference.trim()) {
    sections.push('User-provided reference, pending media and rights verification: ' +
      sourceReference.trim());
  }
  sections.push('Current editing focus: ' + selectedFacet);
  sections.push('Use the installed local Jeeves model. Partition execution into bounded, ' +
    'dependency-ordered existing creator runbooks and saved studio goals. Preserve ' +
    'canon, project revision, identity, scope and the complete outstanding backlog.');
  sections.push('For every actual effect obtain explicit host authorization, observe ' +
    'the existing editor/forge mutation, persist source and result digests, and ' +
    'verify postconditions. Never claim training, model promotion or gameplay without proof.');
  return sections.join('\n');
}
