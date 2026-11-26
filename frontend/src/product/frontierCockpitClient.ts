/** Authenticated client for the fictional frontier cockpit. */
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders } from '../auth/gameforgeAuth';
import { chatApiError, ChatClientError } from './chatErrors';
import { parseCockpitWorld, type CockpitWorld } from './frontierCockpitView';

const ROOT = '/api/game-frontier-cockpit';
const WORLD = /^[a-z][a-z0-9-]{0,63}$/;

function options() {
  return { headers: authHeaders(), retries: 0, timeoutMs: 20000 };
}

async function call(response: Promise<ApiResult<unknown>>, message: string): Promise<unknown> {
  const result = await response;
  if (!result.ok || result.data == null) throw chatApiError(result, message);
  return result.data;
}

function worldPath(worldId: string, suffix = ''): string {
  if (!WORLD.test(worldId)) {
    throw new ChatClientError('Choose a fictional world id such as meadow-realm.', { kind: 'validation', retryable: false });
  }
  return ROOT + '/worlds/' + encodeURIComponent(worldId) + suffix;
}

async function read(worldId: string, suffix: string, body: Record<string, unknown> | undefined, message: string): Promise<CockpitWorld> {
  const path = worldPath(worldId, suffix);
  const data = body
    ? await call(api.post(path, body, options()), message)
    : await call(api.get(path, options()), message);
  return parseCockpitWorld(data);
}

export function loadCockpitWorld(worldId: string): Promise<CockpitWorld> {
  return read(worldId, '', undefined, 'The fictional realm could not be loaded.');
}

export function panCockpit(worldId: string, dx: -1 | 0 | 1, dy: -1 | 0 | 1, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/camera/pan', { dx, dy, actor }, 'The minimap could not pan.');
}

export function zoomCockpit(worldId: string, direction: 1 | -1, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/camera/zoom', { direction, actor }, 'The minimap could not zoom.');
}

export function jumpCockpitLayer(worldId: string, layerId: string, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/camera/layer', { layer_id: layerId, actor }, 'That fictional layer could not be opened.');
}

export function travelCockpitPortal(worldId: string, portalId: string, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/camera/portal', { portal_id: portalId, actor }, 'That world portal could not be followed.');
}

export function approveCockpitBaseline(worldId: string, baselineId: string, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/baselines/' + encodeURIComponent(baselineId) + '/approve', { actor }, 'The baseline could not be approved.');
}

export function saveCockpitSighting(worldId: string, body: {
  sighting_id: string; baseline_id: string; control_id: string;
  bearing_deg: number; distance_m: number; uncertainty_m: number; actor: string;
}): Promise<CockpitWorld> {
  return read(worldId, '/sightings', body, 'The sighting draft could not be saved.');
}

export function approveCockpitSighting(worldId: string, sightingId: string, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/sightings/' + encodeURIComponent(sightingId) + '/approve', { actor }, 'The sighting could not be approved.');
}

export function solveCockpitFix(worldId: string, sightingIds: string[], actor: string): Promise<CockpitWorld> {
  return read(worldId, '/fixes', { sighting_ids: sightingIds, actor }, 'The navigation fix was refused.');
}

export function proposeCockpitEvent(worldId: string, preset: 'start-lantern' | 'advance-lantern', rain: number, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/events/propose', {
    preset, signal: 'rain_mm_h', current_value: rain, actor,
  }, 'The environmental event could not be proposed.');
}

export function commitCockpitEvent(worldId: string, proposalId: string, expectedCanonDigest: string, actor: string): Promise<CockpitWorld> {
  return read(worldId, '/events/' + encodeURIComponent(proposalId) + '/commit', {
    expected_canon_digest: expectedCanonDigest, actor,
  }, 'The event commit was refused.');
}
