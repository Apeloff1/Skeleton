import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  parseCockpitWorld, proposalActions, visibleCells, northUpRows, layerTitle,
} from '../src/product/frontierCockpitView.ts';

const digest = 'a'.repeat(64);
const proposal = 'evt-' + 'b'.repeat(24);

function world(extra = {}) {
  return {
    schema: 'skeleton.frontier.cockpit.v1',
    world_id: 'meadow-realm',
    fictional_only: true,
    datum: 'planet_local_enu_not_earth_wgs84',
    device_geolocation: false,
    map: {
      layers: [
        { layer_id: 'crypt', kind: 'underground', width: 24, height: 24, elevation_m: -18 },
        { layer_id: 'meadow', kind: 'surface', width: 32, height: 32, elevation_m: 12 },
        { layer_id: 'aether-isle', kind: 'sky-island', width: 16, height: 16, elevation_m: 240 },
      ],
      exits: [{ portal_id: 'spire', label: 'spire', dest_layer: 'aether-isle', dest_x: 3, dest_y: 3 }],
      camera: { layer_id: 'meadow', zoom: 1, center_x: 15, center_y: 15 },
      viewport: { x0: 0, y0: 0, x1: 31, y1: 31, width: 32, height: 32 },
      zoom_levels: [1, 2, 4, 8, 16],
      can_zoom_in: true,
      can_zoom_out: false,
    },
    baseline: {
      baseline_id: 'meadow-baseline', datum: 'planet_local_enu_not_earth_wgs84',
      epoch: 'Third Lantern Era', instrument: 'fictional bubble sextant', surveyor: 'Mara Quill',
      notes: 'game metres', status: 'draft', approved_by: null,
      stations: [{ control_id: 'station-oak', x: 0, y: 0, z: 12 }],
    },
    sightings: [{
      sighting_id: 'sight-oak', baseline_id: 'meadow-baseline', control_id: 'station-oak',
      bearing_deg: 90, distance_m: 10, uncertainty_m: 0.4, state: 'draft', approved_by: null,
    }],
    fix: null,
    events: {
      canon_digest: digest, era_engine: 'meadow', revision: 0,
      quest_stage: {}, completed_quests: [],
      proposals: [{
        proposal_id: proposal, page_id: 'meadow-rain-lantern', priority: 5, cooldown_ms: 60000,
        canon_digest: digest, proposed_by: 'meadow-keeper', status: 'proposed', mutated: false,
        actions: [{ kind: 'start_quest', channel: 'quest', target: 'lantern-watch', value: '' }],
      }],
    },
    viewer: { actor: '', role: 'editor', can_commit: true },
    ...extra,
  };
}

test('parses a fictional cockpit and builds a commit action without mutating', () => {
  const parsed = parseCockpitWorld(world());
  assert.equal(parsed.device_geolocation, false);
  assert.equal(parsed.map.layers.map(layer => layer.kind).join(','), 'underground,surface,sky-island');
  assert.equal(layerTitle('sky-island'), 'Sky island');
  const actions = proposalActions(parsed);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].action, 'commit_environmental_event');
  assert.equal(actions[0].parameters.canon_digest, digest);
  assert.equal(parsed.events.revision, 0);
  assert.equal(parsed.events.proposals[0].mutated, false);
});

test('refuses Earth coordinates and device geolocation', () => {
  assert.throws(() => parseCockpitWorld(world({ latitude: 1 })), /Earth coordinates/);
  assert.throws(() => parseCockpitWorld(world({ device_geolocation: true })), /geolocation/);
  const poisoned = world();
  poisoned.baseline.datum = 'WGS84';
  assert.throws(() => parseCockpitWorld(poisoned), /fictional planet frame|Earth coordinates/);
});

test('committed proposals are not offered for another commit', () => {
  const parsed = parseCockpitWorld(world());
  parsed.events.proposals[0].status = 'committed';
  parsed.events.proposals[0].mutated = true;
  assert.equal(proposalActions(parsed).length, 0);
});

test('minimap cells stay inside the viewport and are deterministic', () => {
  const cells = visibleCells({ x0: 0, y0: 0, x1: 31, y1: 31, width: 32, height: 32 }, 4);
  assert.equal(cells.length, 16);
  assert.deepEqual(cells[0], { x: 0, y: 0 });
  assert.ok(cells.every(cell => cell.x >= 0 && cell.x <= 31 && cell.y >= 0 && cell.y <= 31));
  assert.deepEqual(visibleCells({ x0: 0, y0: 0, x1: 31, y1: 31, width: 32, height: 32 }, 4), cells);
  const rows = northUpRows({ x0: 0, y0: 0, x1: 31, y1: 31, width: 32, height: 32 }, 4);
  assert.equal(rows.length, 4);
  assert.ok(rows[0][0].y > rows[rows.length - 1][0].y);
  assert.equal(rows[0][0].x, 0);
});

test('the cockpit screen does not call device geolocation', () => {
  const source = readFileSync(new URL('../src/features/Jeeves/GameFrontierStudioDeck.tsx', import.meta.url), 'utf8');
  assert.equal(source.includes('geolocation'), false);
  assert.equal(source.includes('getCurrentPosition'), false);
  assert.equal(source.includes('startForegroundGPS'), false);
  assert.equal(source.includes('latitude'), false);
});
