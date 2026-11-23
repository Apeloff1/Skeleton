/** View model for the fictional frontier cockpit (GF-P0-58, 98, 118, 131).
 *
 * The server is the authority. This module only checks that a payload is a
 * fictional world and shapes event actions for the existing approval gate.
 * It never reads device location.
 */

export const FICTIONAL_DATUM = 'planet_local_enu_not_earth_wgs84';

export type CockpitLayer = {
  layer_id: string;
  kind: 'underground' | 'surface' | 'sky-island';
  width: number;
  height: number;
  elevation_m: number;
};

export type CockpitPortalExit = {
  portal_id: string;
  label: string;
  dest_layer: string;
  dest_x: number;
  dest_y: number;
};

export type CockpitCamera = {
  layer_id: string;
  zoom: number;
  center_x: number;
  center_y: number;
};

export type CockpitViewport = {
  x0: number; y0: number; x1: number; y1: number; width: number; height: number;
};

export type CockpitSighting = {
  sighting_id: string;
  baseline_id: string;
  control_id: string;
  bearing_deg: number;
  distance_m: number;
  uncertainty_m: number;
  state: 'draft' | 'approved' | 'consumed';
  approved_by: string | null;
};

export type CockpitBaseline = {
  baseline_id: string;
  datum: string;
  epoch: string;
  instrument: string;
  surveyor: string;
  notes: string;
  status: 'draft' | 'approved';
  approved_by: string | null;
  stations: { control_id: string; x: number; y: number; z: number }[];
};

export type CockpitProposal = {
  proposal_id: string;
  page_id: string;
  priority: number;
  cooldown_ms: number;
  canon_digest: string;
  proposed_by: string;
  status: 'proposed' | 'committed';
  mutated: boolean;
  actions: { kind: string; channel: string; target: string; value: string }[];
};

export type CockpitFix = {
  entity_id: string;
  x: number;
  y: number;
  z: number;
  region: string;
  datum: string;
  measured_earth_position: false;
  consumed_ids: string[];
};

export type CockpitWorld = {
  schema: 'skeleton.frontier.cockpit.v1';
  world_id: string;
  fictional_only: true;
  datum: typeof FICTIONAL_DATUM;
  device_geolocation: false;
  map: {
    layers: CockpitLayer[];
    exits: CockpitPortalExit[];
    camera: CockpitCamera;
    viewport: CockpitViewport;
    zoom_levels: number[];
    can_zoom_in: boolean;
    can_zoom_out: boolean;
  };
  baseline: CockpitBaseline | null;
  sightings: CockpitSighting[];
  fix: CockpitFix | null;
  events: {
    canon_digest: string;
    era_engine: string;
    revision: number;
    quest_stage: Record<string, number>;
    quests: { quest_id: string; stages: string[] }[];
    completed_quests: string[];
    proposals: CockpitProposal[];
  };
  viewer?: { actor: string; role: string | null; can_commit: boolean };
};

export type FrontierEventAction = {
  id: string;
  label: string;
  editor: string;
  action: string;
  parameters: Record<string, unknown>;
};

const SHA = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9_.:-]{1,64}$/;
const PROPOSAL = /^evt-[a-f0-9]{24}$/;

function rejectEarth(value: unknown): void {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    value.forEach(rejectEarth);
    return;
  }
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const name = key.toLowerCase();
    if (name === 'latitude' || name === 'longitude' || name === 'lat' || name === 'lon' || name === 'wgs84') {
      throw new Error('Fictional navigation cannot display Earth coordinates.');
    }
    if (name === 'datum' && typeof child === 'string' && child.toUpperCase() === 'WGS84') {
      throw new Error('Fictional navigation cannot display Earth coordinates.');
    }
    if (name === 'device_geolocation' && child !== false) {
      throw new Error('This cockpit does not use device geolocation.');
    }
    rejectEarth(child);
  }
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(label + ' was missing from the fictional world.');
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error(label + ' is missing.');
  return value;
}

function finite(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(label + ' is not a finite fictional number.');
  return value;
}

export function parseCockpitWorld(value: unknown): CockpitWorld {
  rejectEarth(value);
  const data = asRecord(value, 'World');
  if (data.schema !== 'skeleton.frontier.cockpit.v1' || data.fictional_only !== true
      || data.datum !== FICTIONAL_DATUM || data.device_geolocation !== false) {
    throw new Error('The server did not return a fictional cockpit world.');
  }
  const map = asRecord(data.map, 'Map');
  const layers = Array.isArray(map.layers) ? map.layers.map(layer => {
    const row = asRecord(layer, 'Layer');
    const kind = row.kind;
    if (kind !== 'underground' && kind !== 'surface' && kind !== 'sky-island') {
      throw new Error('A map layer is not underground, surface, or sky-island.');
    }
    return {
      layer_id: text(row.layer_id, 'Layer'),
      kind,
      width: finite(row.width, 'Layer width'),
      height: finite(row.height, 'Layer height'),
      elevation_m: finite(row.elevation_m, 'Layer elevation'),
    };
  }) : [];
  const cameraRow = asRecord(map.camera, 'Camera');
  const viewport = asRecord(map.viewport, 'Viewport');
  const events = asRecord(data.events, 'Events');
  const digest = text(events.canon_digest, 'Canon digest');
  if (!SHA.test(digest)) throw new Error('Canon digest is not a SHA-256 hex string.');
  const world: CockpitWorld = {
    schema: 'skeleton.frontier.cockpit.v1',
    world_id: text(data.world_id, 'World'),
    fictional_only: true,
    datum: FICTIONAL_DATUM,
    device_geolocation: false,
    map: {
      layers,
      exits: Array.isArray(map.exits) ? map.exits.map(exit => {
        const row = asRecord(exit, 'Portal');
        return {
          portal_id: text(row.portal_id, 'Portal'),
          label: text(row.label, 'Portal label'),
          dest_layer: text(row.dest_layer, 'Portal destination'),
          dest_x: finite(row.dest_x, 'Portal x'),
          dest_y: finite(row.dest_y, 'Portal y'),
        };
      }) : [],
      camera: {
        layer_id: text(cameraRow.layer_id, 'Camera layer'),
        zoom: finite(cameraRow.zoom, 'Zoom'),
        center_x: finite(cameraRow.center_x, 'Camera x'),
        center_y: finite(cameraRow.center_y, 'Camera y'),
      },
      viewport: {
        x0: finite(viewport.x0, 'Viewport'),
        y0: finite(viewport.y0, 'Viewport'),
        x1: finite(viewport.x1, 'Viewport'),
        y1: finite(viewport.y1, 'Viewport'),
        width: finite(viewport.width, 'Viewport'),
        height: finite(viewport.height, 'Viewport'),
      },
      zoom_levels: Array.isArray(map.zoom_levels) ? map.zoom_levels.map(level => finite(level, 'Zoom level')) : [],
      can_zoom_in: map.can_zoom_in === true,
      can_zoom_out: map.can_zoom_out === true,
    },
    baseline: data.baseline == null ? null : parseBaseline(data.baseline),
    sightings: Array.isArray(data.sightings) ? data.sightings.map(parseSighting) : [],
    fix: data.fix == null ? null : parseFix(data.fix),
    events: {
      canon_digest: digest,
      era_engine: text(events.era_engine, 'Era'),
      revision: finite(events.revision, 'Revision'),
      quest_stage: asNumberMap(events.quest_stage),
      quests: Array.isArray(events.quests) ? events.quests.map(quest => {
        const row = asRecord(quest, 'Quest');
        return {
          quest_id: text(row.quest_id, 'Quest'),
          stages: Array.isArray(row.stages) ? row.stages.filter((item): item is string => typeof item === 'string') : [],
        };
      }) : [],
      completed_quests: Array.isArray(events.completed_quests)
        ? events.completed_quests.filter((item): item is string => typeof item === 'string') : [],
      proposals: Array.isArray(events.proposals) ? events.proposals.map(parseProposal) : [],
    },
  };
  if (data.viewer && typeof data.viewer === 'object') {
    const viewer = data.viewer as Record<string, unknown>;
    world.viewer = {
      actor: typeof viewer.actor === 'string' ? viewer.actor : '',
      role: typeof viewer.role === 'string' ? viewer.role : null,
      can_commit: viewer.can_commit === true,
    };
  }
  return world;
}

function parseBaseline(value: unknown): CockpitBaseline {
  const row = asRecord(value, 'Baseline');
  if (row.datum !== FICTIONAL_DATUM) throw new Error('Baseline datum must stay in the fictional planet frame.');
  const status = row.status;
  if (status !== 'draft' && status !== 'approved') throw new Error('Baseline status is not draft or approved.');
  return {
    baseline_id: text(row.baseline_id, 'Baseline'),
    datum: FICTIONAL_DATUM,
    epoch: text(row.epoch, 'Epoch'),
    instrument: text(row.instrument, 'Instrument'),
    surveyor: text(row.surveyor, 'Surveyor'),
    notes: typeof row.notes === 'string' ? row.notes : '',
    status,
    approved_by: typeof row.approved_by === 'string' ? row.approved_by : null,
    stations: Array.isArray(row.stations) ? row.stations.map(station => {
      const point = asRecord(station, 'Station');
      return {
        control_id: text(point.control_id, 'Station'),
        x: finite(point.x, 'Station x'),
        y: finite(point.y, 'Station y'),
        z: finite(point.z, 'Station z'),
      };
    }) : [],
  };
}

function parseSighting(value: unknown): CockpitSighting {
  const row = asRecord(value, 'Sighting');
  const state = row.state;
  if (state !== 'draft' && state !== 'approved' && state !== 'consumed') {
    throw new Error('Sighting state must be draft, approved, or consumed.');
  }
  const sighting_id = text(row.sighting_id, 'Sighting');
  if (!ID.test(sighting_id)) throw new Error('Sighting id is not usable.');
  return {
    sighting_id,
    baseline_id: text(row.baseline_id, 'Baseline'),
    control_id: text(row.control_id, 'Control'),
    bearing_deg: finite(row.bearing_deg, 'Bearing'),
    distance_m: finite(row.distance_m, 'Distance'),
    uncertainty_m: finite(row.uncertainty_m, 'Uncertainty'),
    state,
    approved_by: typeof row.approved_by === 'string' ? row.approved_by : null,
  };
}

function parseProposal(value: unknown): CockpitProposal {
  const row = asRecord(value, 'Proposal');
  const proposal_id = text(row.proposal_id, 'Proposal');
  if (!PROPOSAL.test(proposal_id)) throw new Error('Proposal id is not a server proposal.');
  const status = row.status === 'committed' ? 'committed' : 'proposed';
  return {
    proposal_id,
    page_id: text(row.page_id, 'Page'),
    priority: finite(row.priority, 'Priority'),
    cooldown_ms: finite(row.cooldown_ms, 'Cooldown'),
    canon_digest: text(row.canon_digest, 'Proposal digest'),
    proposed_by: text(row.proposed_by, 'Proposer'),
    status,
    mutated: row.mutated === true,
    actions: Array.isArray(row.actions) ? row.actions.map(action => {
      const item = asRecord(action, 'Action');
      return {
        kind: text(item.kind, 'Action'),
        channel: text(item.channel, 'Channel'),
        target: text(item.target, 'Target'),
        value: typeof item.value === 'string' ? item.value : '',
      };
    }) : [],
  };
}

function parseFix(value: unknown): CockpitFix {
  const row = asRecord(value, 'Fix');
  if (row.measured_earth_position !== false || row.datum !== FICTIONAL_DATUM) {
    throw new Error('A navigation fix must stay in fictional game metres.');
  }
  return {
    entity_id: text(row.entity_id, 'Fix entity'),
    x: finite(row.x, 'Fix x'),
    y: finite(row.y, 'Fix y'),
    z: finite(row.z, 'Fix z'),
    region: text(row.region, 'Fix region'),
    datum: FICTIONAL_DATUM,
    measured_earth_position: false,
    consumed_ids: Array.isArray(row.consumed_ids) ? row.consumed_ids.filter((item): item is string => typeof item === 'string') : [],
  };
}

function asNumberMap(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out: Record<string, number> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (typeof item === 'number' && Number.isFinite(item)) out[key] = item;
  }
  return out;
}

/** Proposed events become approval-gate actions. Committed events are not replayed. */
export function proposalActions(world: CockpitWorld): FrontierEventAction[] {
  return world.events.proposals.filter(item => item.status === 'proposed' && item.mutated === false).map(item => ({
    id: item.proposal_id,
    label: 'Commit ' + item.page_id.replace(/-/g, ' '),
    editor: 'authoring',
    action: 'commit_environmental_event',
    parameters: {
      proposal_id: item.proposal_id,
      canon_digest: item.canon_digest,
      page_id: item.page_id,
    },
  }));
}

/** Rows run west to east. The first row is the northern edge (+Y is north). */
export function northUpRows(viewport: CockpitViewport, limit = 12): { x: number; y: number }[][] {
  const cells = visibleCells(viewport, limit);
  const cols = Math.max(1, Math.min(limit, Math.floor(viewport.width)));
  const rows: { x: number; y: number }[][] = [];
  for (let index = 0; index < cells.length; index += cols) rows.push(cells.slice(index, index + cols));
  return rows.reverse();
}

export function visibleCells(viewport: CockpitViewport, limit = 12): { x: number; y: number }[] {
  const cols = Math.max(1, Math.min(limit, Math.floor(viewport.width)));
  const rows = Math.max(1, Math.min(limit, Math.floor(viewport.height)));
  const cells: { x: number; y: number }[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      cells.push({
        x: viewport.x0 + Math.floor(col * viewport.width / cols),
        y: viewport.y0 + Math.floor(row * viewport.height / rows),
      });
    }
  }
  return cells;
}

export function layerTitle(kind: CockpitLayer['kind']): string {
  if (kind === 'underground') return 'Underground';
  if (kind === 'sky-island') return 'Sky island';
  return 'Surface';
}
