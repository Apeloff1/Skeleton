/** Bounded presentation of source-generated gameplay evidence; never device qualification. */
import type { RunPayload } from './types';

const MODES = new Set(['extraction', 'combat_loop', 'pipeline', 'puzzle', 'racing', 'survival', 'stealth', 'crafting']);
const AXES = new Set(['risk', 'tempo', 'lethality', 'opacity', 'scarcity', 'agency', 'spectacle', 'intimacy', 'grind', 'authorial']);
const EFFECTS: Record<string, string> = {
  'player.speed': 'Movement / top speed',
  'extraction.caches_required': 'Required caches',
  'extraction.heat_per_second': 'Base heat per second',
  'extraction.heat_limit': 'Heat limit',
  'extraction.pickup_radius': 'Pickup radius',
  'combat_loop.contact_damage': 'Contact damage',
  'combat_loop.waves': 'Enemy waves',
  'combat_loop.attack_range': 'Attack range',
  'pipeline.cargo_capacity': 'Cargo units per batch',
  'pipeline.shipment_quota': 'Shipment quota',
  'pipeline.interaction_radius': 'Station radius',
  'pipeline.frame_budget': 'Frame budget',
  'puzzle.interaction_radius': 'Switch radius',
  'puzzle.switches_required': 'Required switches',
  'puzzle.active_switch_hint_visible': 'Persistent switch hints',
  'racing.interaction_radius': 'Checkpoint radius',
  'racing.time_limit_seconds': 'Race deadline (seconds)',
  'racing.goal_laps': 'Required laps',
  'racing.boost_recharge_per_second': 'Boost recharge per second',
  'survival.interaction_radius': 'Gather radius',
  'survival.supplies_required': 'Required supplies',
  'survival.hydration_drain_per_second': 'Hydration drain per second',
  'survival.exposure_drain_per_second': 'Exposure drain per second',
  'stealth.interaction_radius': 'Intel range',
  'stealth.alert_rise_per_second': 'Detection pressure per second',
  'stealth.detection_radius': 'Guard detection radius',
  'stealth.guard_zones_visible': 'Guard zones visible',
  'stealth.objectives_required': 'Intel objectives',
  'crafting.interaction_radius': 'Workshop radius',
  'crafting.materials_required': 'Required materials',
  'crafting.assembly_seconds': 'Assembly duration (seconds)',
};
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const unit = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const sha = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v);
function axisList(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 10 && new Set(value).size === value.length
    && value.every(x => typeof x === 'string' && AXES.has(x));
}
function axisMap(value: unknown): value is Record<string, number> {
  return record(value) && Object.keys(value).length <= 10
    && Object.entries(value).every(([k, v]) => AXES.has(k) && unit(v));
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= 100000;
}
export interface NativeControlView {
  state: 'verified' | 'unavailable';
  effects: { key: string; label: string; value: string }[];
  unmapped: string[];
  galaxy: null | { active: number; mapped: number; remaining: number;
    overrides: { axis: string; requested: number; effective: number }[] };
}

export function nativeControlView(payload: RunPayload | null): NativeControlView | null {
  const tuning = payload?.playable_tuning;
  const galaxy = payload?.galaxy_playable_controls;
  if (tuning == null && galaxy == null) return null;
  const denied: NativeControlView = { state: 'unavailable', effects: [], unmapped: [], galaxy: null };
  const mode = payload?.forge?.playable_archetype;
  if (payload?.succeeded !== true || typeof mode !== 'string' || !MODES.has(mode)
      || payload.playable_mechanics?.source_verified !== true
      || payload.playable_mechanics?.archetype !== mode) return denied;
  const effects: NativeControlView['effects'] = [];
  let unmapped: string[] = [];
  if (tuning != null) {
    if (!record(tuning) || tuning.schema !== 'skeleton.gameforge.playable_tuning.v1' || tuning.mode !== mode
        || !axisMap(tuning.axes) || !axisList(tuning.mapped_axes) || !axisList(tuning.unmapped_axes)
        || !record(tuning.applied) || Object.keys(tuning.applied).length > 10) return denied;
    const grouped = [...tuning.mapped_axes, ...tuning.unmapped_axes];
    if (new Set(grouped).size !== grouped.length || grouped.length !== Object.keys(tuning.axes).length
        || grouped.some(k => !own(tuning.axes, k))) return denied;
    const mechanics = payload.playable_mechanics.applied_axes;
    if (!axisMap(mechanics) || Object.keys(mechanics).length !== tuning.mapped_axes.length
        || tuning.mapped_axes.some(k => mechanics[k] !== tuning.axes[k])) return denied;
    for (const [key, value] of Object.entries(tuning.applied).sort(([a], [b]) => a.localeCompare(b))) {
      if (!own(EFFECTS, key) || (key !== 'player.speed' && !key.startsWith(mode + '.'))
          || typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 12000) return denied;
      const flag = key.endsWith('_visible');
      if (flag && value !== 0 && value !== 1) return denied;
      effects.push({ key, label: EFFECTS[key], value: flag ? (value === 1 ? 'On' : 'Off') : String(value) });
    }
    unmapped = tuning.unmapped_axes.slice();
  }
  let mapped: NativeControlView['galaxy'] = null;
  if (galaxy != null) {
    if (!record(galaxy) || galaxy.schema !== 'skeleton.gameforge.galaxy_playable_controls.v1'
        || galaxy.mode !== mode || galaxy.source_verified !== true || galaxy.native_execution_qualified !== false
        || !sha(galaxy.profile_sha256) || !count(galaxy.active_matrix_dials)
        || !count(galaxy.mapped_matrix_dials) || !count(galaxy.unmapped_matrix_dials)
        || galaxy.mapped_matrix_dials + galaxy.unmapped_matrix_dials !== galaxy.active_matrix_dials
        || !axisMap(galaxy.effective_axes) || !Array.isArray(galaxy.axes) || galaxy.axes.length > 10
        || !record(galaxy.native_sources)) return denied;
    const nativePaths = ['scenes/archetypes/' + mode + '/main.tscn',
      'scripts/archetypes/' + mode + '/player_controller.gd', 'scripts/archetypes/' + mode + '/core_loop.gd'];
    const manifest = payload.source_manifest?.files;
    if (!record(manifest) || Object.keys(galaxy.native_sources).length !== 3
        || nativePaths.some(path => !sha(galaxy.native_sources[path]) || manifest[path] !== galaxy.native_sources[path])) return denied;
    if (tuning != null) {
      if (!sha(galaxy.tuning_receipt_sha256) || manifest['data/playable_tuning.json'] !== galaxy.tuning_receipt_sha256
          || Object.keys(galaxy.effective_axes).length !== Object.keys(tuning.axes).length
          || Object.entries(galaxy.effective_axes).some(([key, value]) => Math.round(value * 100) / 100 !== Math.round(tuning.axes[key] * 100) / 100)) return denied;
    } else if (Object.keys(galaxy.effective_axes).length || galaxy.tuning_receipt_sha256 != null) return denied;
    const seen = new Set<string>();
    const paths = new Set<string>();
    const overrides: NonNullable<NativeControlView['galaxy']>['overrides'] = [];
    for (const row of galaxy.axes) {
      if (!record(row) || typeof row.axis !== 'string' || !AXES.has(row.axis) || seen.has(row.axis)
          || !unit(row.requested) || !unit(row.effective) || galaxy.effective_axes[row.axis] !== row.effective
          || (row.authority !== 'forge_override' && row.authority !== 'galaxy_matrix')
          || (row.authority === 'galaxy_matrix' && row.requested !== row.effective)
          || !Array.isArray(row.sources) || row.sources.length < 1 || row.sources.length > 16) return denied;
      seen.add(row.axis);
      for (const vote of row.sources) {
        if (!record(vote) || typeof vote.path !== 'string'
            || !/^(mechanics|world)_matrix\.[a-z0-9_]{1,64}\.[a-z0-9_]{1,32}$/.test(vote.path)
            || typeof vote.value !== 'number' || !Number.isFinite(vote.value) || vote.value <= 0 || vote.value > 1000) return denied;
        paths.add(vote.path);
      }
      if (row.authority === 'forge_override') overrides.push({ axis: row.axis, requested: row.requested, effective: row.effective });
    }
    if (paths.size !== galaxy.mapped_matrix_dials) return denied;
    mapped = { active: galaxy.active_matrix_dials, mapped: galaxy.mapped_matrix_dials,
      remaining: galaxy.unmapped_matrix_dials, overrides };
  }
  return { state: 'verified', effects, unmapped, galaxy: mapped };
}
