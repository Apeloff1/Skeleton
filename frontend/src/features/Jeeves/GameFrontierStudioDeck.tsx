/** Fictional minimap, survey approval, and environmental event commit.

 * Galaxy Studio and the Jeeves cockpit mount this deck. Camera, sighting,
 * and quest changes go to the cockpit server. The screen never calls
 * device location and never treats a tile as a measured Earth position.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import theme from '../../theme/tokens';
import {
  approveCockpitBaseline, approveCockpitSighting, commitCockpitEvent, jumpCockpitLayer,
  loadCockpitWorld, panCockpit, proposeCockpitEvent, saveCockpitSighting, solveCockpitFix,
  travelCockpitPortal, zoomCockpit,
} from '../../product/frontierCockpitClient';
import {
  layerTitle, northUpRows, proposalActions, type CockpitWorld,
} from '../../product/frontierCockpitView';
import { getLearningProject, type LearningProject } from '../../product/gameLearningClient';
import GameFrontierCockpitPanel from './GameFrontierCockpitPanel';
import GameFrontierOperatorApprovalPanel from './GameFrontierOperatorApprovalPanel';

type Props = {
  worldId?: string;
  projectId?: string;
  project?: LearningProject | null;
  editorPlacement?: 'inline' | 'workspace';
};

const RAIN = '4';

export default function GameFrontierStudioDeck({
  worldId = 'meadow-realm', projectId, project = null, editorPlacement = 'inline',
}: Props) {
  const { width } = useWindowDimensions();
  const narrow = width < 760;
  const [world, setWorld] = useState<CockpitWorld | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [operator, setOperator] = useState('');
  const [armed, setArmed] = useState<string | null>(null);
  const [rain, setRain] = useState(RAIN);
  const [draftId, setDraftId] = useState('');
  const [loadedProject, setLoadedProject] = useState<LearningProject | null>(project);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = await loadCockpitWorld(worldId);
    setWorld(next);
    if (next.viewer?.actor) setOperator(current => current || next.viewer?.actor || '');
    return next;
  }, [worldId]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    refresh().catch(reason => {
      if (live) setError(reason instanceof Error ? reason.message : 'The fictional realm could not be loaded.');
    }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [refresh]);

  useEffect(() => { setLoadedProject(project); }, [project]);

  useEffect(() => {
    if (project || !projectId) return;
    let live = true;
    setProjectLoading(true);
    setProjectError(null);
    getLearningProject(projectId).then(value => { if (live) setLoadedProject(value); }).catch(reason => {
      if (live) setProjectError(reason instanceof Error ? reason.message : 'The Forge project could not be opened.');
    }).finally(() => { if (live) setProjectLoading(false); });
    return () => { live = false; };
  }, [project, projectId]);

  const run = useCallback(async (work: () => Promise<CockpitWorld>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      const next = await work();
      setWorld(next);
      setNotice(success);
      setArmed(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The cockpit refused that action.');
    }
  }, []);

  const actor = operator.trim();
  const actions = useMemo(() => world ? proposalActions(world) : [], [world]);
  const rows = world ? northUpRows(world.map.viewport, narrow ? 6 : 8) : [];
  const layer = world?.map.layers.find(item => item.layer_id === world.map.camera.layer_id);
  const quests = world ? Object.entries(world.events.quest_stage) : [];

  return (
    <View style={styles.root} accessibilityLabel="Fictional frontier cockpit">
      <Text style={styles.heading} accessibilityRole="header">Fictional realm cockpit</Text>
      <Text style={styles.body}>
        Meadow, crypt, and sky island are authored game layers. Tile numbers are fictional.
        This screen does not read this device’s location and does not show a measured Earth position.
      </Text>
      {loading && <View style={styles.row}><ActivityIndicator color={c.primary} /><Text style={styles.muted}>Loading the fictional realm…</Text></View>}
      {!loading && error && !world && <View style={styles.gap}>
        <Text style={styles.err} accessibilityRole="alert">{error}</Text>
        <Btn label="Try again" onPress={() => { setLoading(true); refresh().then(() => setError(null)).catch(reason => setError(reason instanceof Error ? reason.message : 'The fictional realm could not be loaded.')).finally(() => setLoading(false)); }} />
      </View>}
      {!loading && world && <>
        <Field label="Operator" value={operator} onChange={setOperator} editable={!world.viewer?.actor}
          hint={world.viewer?.actor ? 'Signed-in operator recorded on approvals.' : 'Type the name that will be stored with each approval.'} />
        {!!error && <Text style={styles.err} accessibilityRole="alert">{error}</Text>}
        {!!notice && <Text style={styles.ok} accessibilityLiveRegion="polite">{notice}</Text>}

        <View style={[styles.columns, narrow && styles.columnsNarrow]}>
          <View style={styles.mapCard}>
            <Text style={styles.sub} accessibilityRole="header">Minimap</Text>
            {!world.map.layers.length && <Text style={styles.muted}>This realm has no fictional layers yet.</Text>}
            {layer && <>
              <Text style={styles.body}>{layerTitle(layer.kind)} · {layer.layer_id} · {layer.elevation_m} fictional metres</Text>
              <Text style={styles.muted}>
                Camera tile {world.map.camera.center_x}, {world.map.camera.center_y} · zoom ×{world.map.camera.zoom}
                · window {world.map.viewport.x0}–{world.map.viewport.x1}, {world.map.viewport.y0}–{world.map.viewport.y1}.
                These are game tiles, not a GPS reading.
              </Text>
              <ScrollView horizontal style={styles.mapScroll} accessibilityLabel="Fictional minimap tiles, north at the top">
              <View style={styles.grid}>
                {rows.map(row => (
                  <View key={row[0].y + ':' + row[0].x} style={styles.gridRow}>
                    {row.map(cell => {
                      const here = cell.x === world.map.camera.center_x && cell.y === world.map.camera.center_y;
                      return <View key={cell.x + ':' + cell.y} style={[styles.cell, here && styles.cellHere]}>
                        <Text style={styles.cellText}>{here ? 'You ' : ''}{cell.x},{cell.y}</Text>
                      </View>;
                    })}
                  </View>
                ))}
              </View>
              </ScrollView>
              <Text style={styles.muted}>North is up. +Y is fictional north and +X is fictional east.</Text>
              <View style={styles.wrap}>
                <Btn label="Zoom out" disabled={!world.map.can_zoom_out} onPress={() => { void run(() => zoomCockpit(worldId, -1, actor), 'Zoomed out one fictional level.'); }} />
                <Btn label="Zoom in" disabled={!world.map.can_zoom_in} onPress={() => { void run(() => zoomCockpit(worldId, 1, actor), 'Zoomed in one fictional level.'); }} />
                <Btn label="West" onPress={() => { void run(() => panCockpit(worldId, -1, 0, actor), 'Panned west.'); }} />
                <Btn label="North" onPress={() => { void run(() => panCockpit(worldId, 0, 1, actor), 'Panned north.'); }} />
                <Btn label="South" onPress={() => { void run(() => panCockpit(worldId, 0, -1, actor), 'Panned south.'); }} />
                <Btn label="East" onPress={() => { void run(() => panCockpit(worldId, 1, 0, actor), 'Panned east.'); }} />
              </View>
              <Text style={styles.sub}>Layers</Text>
              <View style={styles.wrap}>
                {world.map.layers.map(item => (
                  <Btn key={item.layer_id} label={layerTitle(item.kind) + ' · ' + item.layer_id}
                    active={item.layer_id === world.map.camera.layer_id}
                    onPress={() => { void run(() => jumpCockpitLayer(worldId, item.layer_id, actor), 'Opened the ' + layerTitle(item.kind).toLowerCase() + ' layer.'); }} />
                ))}
              </View>
              <Text style={styles.sub}>World portals on this layer</Text>
              {world.map.exits.length ? world.map.exits.map(exit => (
                <Btn key={exit.portal_id} label={exit.portal_id + ' → ' + exit.dest_layer + ' tile ' + exit.dest_x + ', ' + exit.dest_y}
                  onPress={() => { void run(() => travelCockpitPortal(worldId, exit.portal_id, actor), 'Followed ' + exit.portal_id + ' to ' + exit.dest_layer + '.'); }} />
              )) : <Text style={styles.muted}>No declared portal leaves this layer.</Text>}
            </>}
          </View>

          <View style={styles.mapCard}>
            <Text style={styles.sub} accessibilityRole="header">Surveyed sightings</Text>
            <Text style={styles.muted}>A sighting stays a draft until you approve it. A fix refuses drafts and sightings already used.</Text>
            {!world.baseline && <Text style={styles.muted}>No baseline metadata has been drafted for this realm.</Text>}
            {world.baseline && <>
              <Text style={styles.body}>{world.baseline.baseline_id} · {world.baseline.status}{world.baseline.approved_by ? ' by ' + world.baseline.approved_by : ''}</Text>
              <Text style={styles.muted}>{world.baseline.epoch} · {world.baseline.instrument} · {world.baseline.surveyor}</Text>
              <Text style={styles.muted}>{world.baseline.notes}</Text>
              <Text style={styles.muted}>Datum {world.baseline.datum}. Stations are fictional metres.</Text>
              {world.baseline.stations.map(station => (
                <Text key={station.control_id} style={styles.muted}>{station.control_id}: {station.x}, {station.y}, {station.z}</Text>
              ))}
              {world.baseline.status === 'draft' && (
                <Btn label={armed === 'baseline' ? 'Confirm baseline approval' : 'Approve baseline metadata'}
                  onPress={() => {
                    if (armed !== 'baseline') { setArmed('baseline'); return; }
                    void run(() => approveCockpitBaseline(worldId, world.baseline!.baseline_id, actor), 'Baseline metadata approved.');
                  }} />
              )}
            </>}
            <Text style={styles.sub}>Sightings</Text>
            {!world.sightings.length && <Text style={styles.muted}>No sightings have been drafted.</Text>}
            {world.sightings.map(sighting => (
              <View key={sighting.sighting_id} style={styles.sighting}>
                <Text style={styles.body}>{sighting.sighting_id} · {sighting.state}{sighting.approved_by ? ' by ' + sighting.approved_by : ''}</Text>
                <Text style={styles.muted}>{sighting.control_id}: bearing {sighting.bearing_deg}°, {sighting.distance_m} fictional metres ±{sighting.uncertainty_m}</Text>
                {sighting.state === 'draft' && <Btn label={armed === sighting.sighting_id ? 'Confirm sighting approval' : 'Approve sighting'}
                  onPress={() => {
                    if (armed !== sighting.sighting_id) { setArmed(sighting.sighting_id); return; }
                    void run(() => approveCockpitSighting(worldId, sighting.sighting_id, actor), sighting.sighting_id + ' approved.');
                  }} />}
              </View>
            ))}
            <Field label="New sighting id" value={draftId} onChange={setDraftId}
              hint="Saves a draft from the first station: bearing 45 degrees, 12 fictional metres, uncertainty 1." />
            <Btn label="Save sighting draft" onPress={() => {
              const baseline = world.baseline;
              const station = baseline?.stations[0];
              if (!baseline || !station) { setError('Draft a baseline before adding a sighting.'); return; }
              if (!/^[A-Za-z0-9_.:-]{1,64}$/.test(draftId.trim())) { setError('Sighting id must use letters, digits, or . _ : -.'); return; }
              void run(() => saveCockpitSighting(worldId, {
                sighting_id: draftId.trim(), baseline_id: baseline.baseline_id, control_id: station.control_id,
                bearing_deg: 45, distance_m: 12, uncertainty_m: 1, actor,
              }), 'Saved ' + draftId.trim() + ' as a draft. It cannot enter a fix until you approve it.');
            }} />
            <Btn label="Compute fictional fix" onPress={() => {
              const ids = world.sightings.map(item => item.sighting_id);
              if (!ids.length) { setError('Add a sighting before asking for a fix.'); return; }
              void run(() => solveCockpitFix(worldId, ids, actor), 'Navigation fix accepted and the sightings were consumed.');
            }} />
            {world.fix && <Text style={styles.ok}>
              Fictional position {world.fix.x}, {world.fix.y}, {world.fix.z} metres in {world.fix.region}. Not a measured Earth coordinate.
            </Text>}
          </View>
        </View>

        <View style={styles.mapCard}>
          <Text style={styles.sub} accessibilityRole="header">Environmental events</Text>
          <Text style={styles.body}>
            Canon digest {world.events.canon_digest.slice(0, 12)}… · save revision {world.events.revision}
            · quests {quests.length ? quests.map(([id, stage]) => {
              const named = world.events.quests.find(quest => quest.quest_id === id)?.stages[stage];
              return named ? id + ' · ' + named : id + ' stage ' + stage;
            }).join(', ') : 'none started'}
            {world.events.completed_quests.length ? ' · completed ' + world.events.completed_quests.join(', ') : ''}
          </Text>
          {!world.events.proposals.length && <Text style={styles.muted}>No environmental event has been proposed.</Text>}
          {world.events.proposals.map(item => (
            <Text key={item.proposal_id} style={styles.muted}>
              {item.page_id} · {item.status} · priority {item.priority}
              {item.mutated ? ' · quest and save were updated' : ' · proposal only, quest and save are unchanged'}
              {' · '}{item.actions.map(action => action.kind + ' ' + action.target).join(', ')}
            </Text>
          ))}
          <Field label="Rain reading mm/h" value={rain} onChange={setRain} />
          <View style={styles.wrap}>
            <Btn label="Propose lantern quest" onPress={() => {
              const value = Number(rain);
              if (!Number.isFinite(value)) { setError('Enter a rain reading in millimetres per hour.'); return; }
              void run(() => proposeCockpitEvent(worldId, 'start-lantern', value, actor), 'Proposed the lantern quest. The save was not changed.');
            }} />
            <Btn label="Propose shelter advance" onPress={() => {
              const value = Number(rain);
              if (!Number.isFinite(value)) { setError('Enter a rain reading in millimetres per hour.'); return; }
              void run(() => proposeCockpitEvent(worldId, 'advance-lantern', value, actor), 'Proposed the shelter advance. The save was not changed.');
            }} />
          </View>
          {actions.length ? <GameFrontierOperatorApprovalPanel actions={actions} disabled={!actor} runAction={async action => {
            const proposalId = String(action.parameters.proposal_id || '');
            const digest = String(action.parameters.canon_digest || '');
            const next = await commitCockpitEvent(worldId, proposalId, digest, actor);
            setWorld(next);
            setNotice('Authorized commit applied the event to the quest and save.');
            const receipt = next.events.canon_digest;
            return { receipt };
          }} /> : <Text style={styles.muted}>No proposed event is waiting for an authorized commit.</Text>}
        </View>

        {editorPlacement === 'workspace' ? <View style={styles.mapCard}>
          <Text style={styles.sub} accessibilityRole="header">RPG editors</Text>
          <Text style={styles.muted}>World and quest authoring, curriculum, epic routes, and handbooks are open in the Forge Studio panel above. Event commits on this deck still go through the authorized runtime.</Text>
        </View> : <GameFrontierCockpitPanel projectId={projectId || loadedProject?.project_id} project={loadedProject}
          projectLoading={projectLoading} projectError={projectError} showQueue={false} actions={actions} />}
      </>}
    </View>
  );
}

function Field({ label, value, onChange, editable = true, hint }: {
  label: string; value: string; onChange: (value: string) => void; editable?: boolean; hint?: string;
}) {
  return (
    <View style={styles.gap}>
      <Text style={styles.muted}>{label}</Text>
      <TextInput accessibilityLabel={label} value={value} onChangeText={onChange} editable={editable}
        autoCapitalize="none" autoCorrect={false} placeholderTextColor={c.textDim} style={styles.input} />
      {!!hint && <Text style={styles.muted}>{hint}</Text>}
    </View>
  );
}

function Btn({ label, onPress, disabled = false, active = false }: {
  label: string; onPress: () => void; disabled?: boolean; active?: boolean;
}) {
  return (
    <TouchableOpacity accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled, selected: active }}
      disabled={disabled} onPress={onPress} style={[styles.btn, active && styles.btnActive, disabled && styles.btnDisabled]}>
      <Text style={styles.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

const c = theme.colors;
const styles = StyleSheet.create({
  root: { gap: theme.spacing.md, marginTop: theme.spacing.md },
  heading: { ...theme.typography.h3, color: c.text },
  sub: { ...theme.typography.label, color: c.text },
  body: { ...theme.typography.body, color: c.text },
  muted: { ...theme.typography.caption, color: c.textMuted },
  ok: { ...theme.typography.caption, color: c.success },
  err: { ...theme.typography.caption, color: c.danger },
  row: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  gap: { gap: theme.spacing.xs },
  columns: { flexDirection: 'row', gap: theme.spacing.md, alignItems: 'flex-start' },
  columnsNarrow: { flexDirection: 'column' },
  mapCard: { flex: 1, gap: theme.spacing.sm, padding: theme.spacing.md, borderRadius: theme.radii.lg,
    backgroundColor: c.bgElevated, borderWidth: 1, borderColor: c.border, minWidth: 0, maxWidth: '100%', overflow: 'hidden' },
  mapScroll: { alignSelf: 'stretch', maxWidth: '100%' },
  grid: { gap: 4, alignSelf: 'stretch' },
  gridRow: { flexDirection: 'row', flexWrap: 'nowrap', gap: 4 },
  cell: { width: 64, minHeight: 28, borderRadius: 4, backgroundColor: c.surface, alignItems: 'center', justifyContent: 'center' },
  cellHere: { backgroundColor: c.primarySoft, borderWidth: 1, borderColor: c.borderFocus },
  cellText: { ...theme.typography.caption, color: c.text },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  sighting: { gap: 4, paddingVertical: 4 },
  input: { color: c.text, borderColor: c.border, borderWidth: 1, borderRadius: theme.radii.sm,
    paddingHorizontal: theme.spacing.sm, paddingVertical: theme.spacing.sm, minHeight: 44 },
  btn: { minHeight: 44, justifyContent: 'center', paddingHorizontal: theme.spacing.md, paddingVertical: theme.spacing.sm,
    borderRadius: theme.radii.sm, backgroundColor: c.surfaceAlt },
  btnActive: { borderWidth: 1, borderColor: c.borderFocus },
  btnDisabled: { opacity: 0.45 },
  btnText: { ...theme.typography.button, color: c.text },
});
