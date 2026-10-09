/**
 * Project-scoped navigation and read-only evidence for the world workbench.
 *
 * Only canonical game APIs may assert whether an artifact was forged,
 * a system mounted or an operation finished. These helpers never infer
 * completion from opening a screen or from the existence of a local draft.
 */
export type WorldStageKey = 'world' | 'narrative' | 'mechanics' | 'assets';
export type WorldStage = {
  id: WorldStageKey;
  title: string;
  purpose: string;
  evidence: readonly string[];
};
export const WORLD_STAGES: readonly WorldStage[] = [
  { id: 'world', title: 'World structure', purpose: 'Terrain, regions, travel and world rules.', evidence: ['world graph', 'world map', 'terrain'] },
  { id: 'narrative', title: 'Story and quests', purpose: 'Lore, characters, quests and story beats.', evidence: ['lore graph', 'narrative', 'quest'] },
  { id: 'mechanics', title: 'Playable mechanics', purpose: 'Interaction rules, game loops and gameplay systems.', evidence: ['mechanics', 'gameplay', 'system'] },
  { id: 'assets', title: 'Visual assets', purpose: 'Styles, characters, environments and reusable art.', evidence: ['asset manifest', 'image', 'sprites'] },
] as const;

export type WorldEvidence = {
  id: WorldStageKey;
  title: string;
  present: boolean;
  available: number;
  total: number;
  summaries: readonly string[];
  rawNames: readonly string[];
};
export type MountedSystem = { key: string; label: string };

export function validProjectId(raw: unknown): string {
  return typeof raw === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(raw) ? raw : '';
}

function record(x: unknown): Record<string, unknown> | null {
  return x && typeof x === 'object' && !Array.isArray(x) ? x as Record<string, unknown> : null;
}
export function mapWorldEvidence(raw: unknown): readonly WorldEvidence[] {
  const value = record(raw);
  const artifacts = Array.isArray(value?.artifacts) ? value.artifacts : [];
  return WORLD_STAGES.map(stage => {
    const items = artifacts.map(record).filter((item): item is Record<string, unknown> => !!item)
      .filter(item => item.stage === stage.id);
    const names = items.filter(item => item.present === true)
      .map(item => typeof item.name === 'string' ? item.name : '')
      .filter(Boolean).slice(0, 20);
    const summaries = items.filter(item => item.present === true)
      .map(item => typeof item.summary === 'string' ? item.summary.trim().slice(0, 190) : '')
      .filter(Boolean).slice(0, 4);
    return {
      id: stage.id,
      title: stage.title,
      present: items.some(item => item.present === true),
      available: items.filter(item => item.present === true).length,
      total: items.length,
      summaries, rawNames: names,
    };
  });
}
export function readArtifactPreview(kb: unknown, artifactName: string): string | null {
  const data = record(record(kb)?.data);
  if (!data || !Object.prototype.hasOwnProperty.call(data, artifactName)) return null;
  const value = data[artifactName];
  try {
    const serialized = JSON.stringify(value, null, 2);
    return typeof serialized === 'string' ? serialized.slice(0, 1_600) : null;
  } catch { return null; }
}
export function mountedWorldSystems(raw: unknown): readonly MountedSystem[] {
  const response = record(raw);
  const systems = Array.isArray(response?.systems) ? response.systems : [];
  const seen = new Set<string>();
  const result: MountedSystem[] = [];
  for (const candidate of systems) {
    const entry = record(candidate);
    const key = typeof entry?.system === 'string' ? entry.system
      : typeof entry?.key === 'string' ? entry.key : '';
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push({
      key: key.slice(0, 96),
      label: typeof entry?.label === 'string' && entry.label.trim()
        ? entry.label.trim().slice(0, 90) : key.slice(0, 96),
    });
    if (result.length === 32) break;
  }
  return result;
}

export type ProjectLink = { id: string; title: string; description: string; href: string };
export function projectHref(route: string, projectId: unknown): string | null {
  const id = validProjectId(projectId);
  if (!id) return null;
  const key = encodeURIComponent(id);
  const param = route === '/compose-scene' || route === '/systems-forge' || route === '/zip-export' ? 'build'
    : route === '/physics-studio' ? 'pid' : 'game';
  return `${route}?${param}=${key}`;
}
export function worldProjectLinks(id: unknown): readonly ProjectLink[] {
  const project = validProjectId(id);
  if (!project) return [];
  const links = [
    ['worldforge','Worldforge','Create and save world geometry from the selected game.','/worldforge'],
    ['scene','Scene Composer','Compose playable scenes and asset families.','/compose-scene'],
    ['systems','Systems Forge','Mount real game systems and tweak gameplay rules.','/systems-forge'],
    ['art','Asset Genesis','Forge art grounded in your game.','/asset-genesis'],
    ['physics','Physics Studio','Compose the game physics configuration.','/physics-studio'],
    ['review','Design Review','Review a game design with the canonical compiler.','/design-review'],
    ['knowledge','Knowledge Base','Edit, review and approve canonical game artifacts.','/game-kb'],
    ['studio','Galaxy Studio','Rebuild, refine and package the selected game.','/studio'],
  ] as const;
  return links.map(([key,title,description,route]) => ({ id:key,title,description,href:projectHref(route,project)! }));
}
