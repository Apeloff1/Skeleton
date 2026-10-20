/** Interactive 50-operation Forge Studio editor over live authenticated project revisions. */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  buildForge, copyForgeTiles, editForge, exportForge, inspectForge,
  type ForgeDocument, type ForgeStep, type ForgeBuild,
} from '../../product/gameFrontierAuthoringClient';
import { getLearningProject, type LearningProject } from '../../product/gameLearningClient';

type Props = {
  project: LearningProject;
  disabled?: boolean;
  onSaved: (project: LearningProject) => void;
  onDirtyChange?: (dirty: boolean) => void;
};

const GROUPS: { title: string; actions: string[] }[] = [
  { title: 'Tiles & geometry', actions: ['tile_set','rect_fill','line_draw','ellipse_fill','flood_fill',
    'replace_tile','checker_fill','stamp','region_paste','shift_layer','flip_horizontal','flip_vertical','rotate_90'] },
  { title: 'Layers & palettes', actions: ['layer_add','layer_remove','layer_duplicate','layer_reorder',
    'layer_elevation','palette_add','palette_replace','palette_swap','palette_remove','layer_resize',
    'layer_crop','layer_clear'] },
  { title: 'Prefabs & actors', actions: ['prefab_add','prefab_remove','prefab_clone','prefab_retarget',
    'prefab_interaction','placement_add','placement_remove','placement_move','placement_rotate',
    'placement_duplicate','placement_mirror','placement_grid'] },
  { title: 'Events & quests', actions: ['event_add','event_remove','event_condition','event_action',
    'event_trigger','quest_add','quest_remove','quest_stage_append','quest_objective','quest_title'] },
  { title: 'Soundtracks', actions: ['soundtrack_add','soundtrack_remove','soundtrack_reorder'] },
];
const SAMPLE: Record<string, Record<string, unknown>> = {
  tile_set: { x: 0, y: 0, tile: 1 }, rect_fill: { x: 0, y: 0, width: 3, height: 3, tile: 1 },
  line_draw: { x: 0, y: 0, x2: 3, y2: 3, tile: 1 },
  ellipse_fill: { x: 0, y: 0, width: 4, height: 4, tile: 1 },
  flood_fill: { x: 0, y: 0, tile: 1 }, replace_tile: { before: 0, after: 1 },
  checker_fill: { x: 0, y: 0, width: 4, height: 4, a: 1, b: 2 },
  stamp: { x: 0, y: 0, width: 2, height: 2, tiles: [1, -1, 1, 1] },
  region_paste: { x: 0, y: 0, width: 2, height: 2, tiles: [1, 1, 1, 1] },
  shift_layer: { dx: 1, dy: 0, wrap: false }, rotate_90: { clockwise: true },
  layer_add: { layer: 'decoration', width: 16, height: 16, palette: ['foliage'], fill: -1 },
  layer_duplicate: { new_layer: 'ground_copy' }, layer_reorder: { position: 0 },
  layer_elevation: { elevation_m: 4 }, palette_add: { value: 'newtile' },
  palette_replace: { index: 0, value: 'newground' }, palette_swap: { a: 0, b: 1 },
  palette_remove: { index: 2 }, layer_resize: { width: 20, height: 20, fill: -1 },
  layer_crop: { x: 0, y: 0, width: 8, height: 8 },
  prefab_add: { prefab_id: 'hero', kind: 'character', era: 'tile', asset_digest: '' },
  prefab_remove: { prefab_id: 'hero' }, prefab_clone: { prefab_id: 'hero', new_prefab_id: 'hero_alt' },
  prefab_retarget: { prefab_id: 'hero', asset_digest: '' },
  prefab_interaction: { prefab_id: 'hero', interaction_type: 'dialogue' },
  placement_add: { prefab_id: 'hero', x: 0, y: 0, z: 0 },
  placement_remove: { index: 0 }, placement_move: { index: 0, x: 1, y: 0, z: 0 },
  placement_rotate: { index: 0, degrees: 90 },
  placement_duplicate: { index: 0, dx: 1, dy: 0, dz: 0 },
  placement_mirror: { index: 0, axis: 'x', pivot: 0 },
  placement_grid: { prefab_id: 'hero', x: 0, y: 0, z: 0,
    columns: 3, rows: 3, dx: 2, dy: 2 },
  event_add: { event_id: 'entrance', trigger: 'enter', action: 'show_dialogue',
    target: 'hero', value: 'Welcome' },
  event_remove: { event_id: 'entrance' },
  event_condition: { event_id: 'entrance', condition_flag: 'door_open', condition_value: true },
  event_action: { event_id: 'entrance', action: 'show_dialogue', target: 'hero', value: 'Hello' },
  event_trigger: { event_id: 'entrance', trigger: 'interact' },
  quest_add: { quest_id: 'first_quest', stage_id: 'begin', title: 'A new beginning',
    objective: 'Reach the harbor' },
  quest_remove: { quest_id: 'first_quest' },
  quest_stage_append: { quest_id: 'first_quest', from_stage_id: 'begin',
    stage_id: 'second', objective: 'Chart the sky islands' },
  quest_objective: { quest_id: 'first_quest', stage_id: 'begin', objective: 'Talk to the captain' },
  quest_title: { quest_id: 'first_quest', title: 'The First Journey' },
  soundtrack_add: { soundtrack_id: 'exploration_theme' },
  soundtrack_remove: { soundtrack_id: 'exploration_theme' },
  soundtrack_reorder: { soundtrack_id: 'exploration_theme', position: 0 },
};
function label(name: string) { return name.replace(/_/g, ' '); }
const palette = ['#1b4230','#62727f','#406c99','#7d704c','#8b5b83','#777c3e','#5e6274'];
function Button({ title, press, disabled }: { title: string; press: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={title}
    accessibilityState={{ disabled: !!disabled }} onPress={press} disabled={disabled}
    style={{ paddingVertical: 10, paddingHorizontal: 13, borderRadius: 8, borderWidth: 1,
      borderColor: '#4d6780', backgroundColor: disabled ? '#232933' : '#293c4d', margin: 3 }}>
    <Text style={{ color: disabled ? '#8792a0' : '#e8eff6', fontWeight: '600' }}>{title}</Text>
  </TouchableOpacity>;
}
export default function GameFrontierAuthoringPanel({ project, disabled = false, onSaved, onDirtyChange }: Props) {
  const [doc, setDoc] = useState<ForgeDocument | null>(null);
  const [action, setAction] = useState('tile_set');
  const [search, setSearch] = useState('');
  const [parameters, setParameters] = useState('{"layer":"ground","x":0,"y":0,"tile":1}');
  const [steps, setSteps] = useState<ForgeStep[]>([]);
  const [selectedLayer, setSelectedLayer] = useState('ground');
  const [tilePixels, setTilePixels] = useState<number[]>([]);
  const [gridSize, setGridSize] = useState<[number,number]>([0, 0]);
  const [seed, setSeed] = useState('42');
  const [islands, setIslands] = useState('12');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ForgeBuild | null>(null);
  const pending = disabled || busy;
  useEffect(() => { onDirtyChange?.(steps.length > 0); }, [steps.length, onDirtyChange]);
  const load = useCallback(async () => {
    const current = await inspectForge(project.project_id);
    setDoc(current);
    setSelectedLayer(value => current.layers.some(layer => layer.id === value) ?
      value : current.layers[0]?.id || 'ground');
  }, [project.project_id]);
  useEffect(() => {
    let live = true;
    inspectForge(project.project_id).then(value => {
      if (!live) return;
      setDoc(value);
      setSelectedLayer(old => value.layers.some(layer => layer.id === old) ?
        old : value.layers[0]?.id || 'ground');
    }).catch(reason => { if (live) setError(String(reason?.message || reason)); });
    return () => { live = false; };
  }, [project.project_id, project.version]);
  useEffect(() => {
    if (!doc) return;
    const layer = doc.layers.find(row => row.id === selectedLayer);
    if (!layer) return;
    const width = Math.min(12, layer.size[0]), height = Math.min(12, layer.size[1]);
    let live = true;
    copyForgeTiles(project.project_id, selectedLayer, 0, 0, width, height).then(value => {
      if (live) { setTilePixels(value.tiles); setGridSize([width, height]); }
    }).catch(() => { if (live) setTilePixels([]); });
    return () => { live = false; };
  }, [doc?.source_sha256, selectedLayer, project.project_id]);
  const listed = useMemo(() => GROUPS.map(group => ({
    ...group, actions: group.actions.filter(item => (!doc || doc.action_catalog.includes(item))
      && item.includes(search.trim().toLowerCase())),
  })).filter(group => group.actions.length), [doc, search]);
  const choose = (name: string) => {
    setAction(name);
    const args = { ...(SAMPLE[name] || {}) };
    if (['tile_set','rect_fill','line_draw','ellipse_fill','flood_fill','replace_tile',
      'checker_fill','stamp','region_paste','shift_layer','flip_horizontal','flip_vertical',
      'rotate_90','layer_remove','layer_duplicate','layer_reorder','layer_elevation',
      'palette_add','palette_replace','palette_swap','palette_remove','layer_resize',
      'layer_crop','layer_clear'].includes(name)) args.layer = selectedLayer;
    setParameters(JSON.stringify(args, null, 2));
  };
  const enqueue = () => {
    try {
      if (steps.length >= 64) throw Error('One transaction supports at most 64 editor actions.');
      const args: unknown = JSON.parse(parameters);
      if (!args || Array.isArray(args) || typeof args !== 'object') throw Error(
        'Action parameters must be a JSON object.');
      setSteps(existing => [...existing, { action, parameters: args as Record<string, unknown> }]);
      setError('');
    } catch (reason: any) { setError(String(reason?.message || reason)); }
  };
  const transact = async (preview: boolean) => {
    if (!doc || steps.length === 0) return;
    setBusy(true); setError('');
    try {
      const result = await editForge(project.project_id, doc, steps, preview);
      if (!preview && result.persisted) {
        setSteps([]);
        await load();
        onSaved(await getLearningProject(project.project_id));
        setNotice('Real game source committed to the project revision history.');
      } else setNotice('Preview compiled: ' + result.candidate_sha256.slice(0, 16) +
        ' · no source changes persisted.');
    } catch (reason: any) { setError(String(reason?.message || reason)); }
    finally { setBusy(false); }
  };
  const build = async (publish: boolean) => {
    if (!doc) return;
    const numberSeed = Number(seed), numberIslands = Number(islands);
    if (!Number.isSafeInteger(numberSeed) || numberSeed < 0 ||
        !Number.isSafeInteger(numberIslands) || numberIslands < 3 || numberIslands > 64) {
      setError('Choose an integer seed and between 3 and 64 sky islands.'); return;
    }
    setBusy(true); setError('');
    try {
      const result = publish ? await exportForge(project.project_id, doc, numberSeed, numberIslands)
        : await buildForge(project.project_id, numberSeed, numberIslands);
      setReport(result);
      setNotice(publish ? 'Actual Godot project files added to your saved project.' :
        'Playable expedition compiled and route-playtested from current Forge source.');
      if (publish) { await load(); onSaved(await getLearningProject(project.project_id)); }
    } catch (reason: any) { setError(String(reason?.message || reason)); }
    finally { setBusy(false); }
  };
  return <View style={{ gap: 12, paddingVertical: 10 }}>
    <Text style={{ color: '#eef3fa', fontSize: 20, fontWeight: '700' }}>Forge Studio · Real Game Authoring</Text>
    <Text style={{ color: '#a7bacf' }}>50 editable tools for maps, characters, quests, events and soundtracks.
      Every saved edit changes the project source and is consumed by the real game compiler.</Text>
    {!doc ? <ActivityIndicator color="#8bd5e8" /> : <View>
      <Text style={{ color: '#bdcddd' }}>Revision {doc.expected_version} · {doc.layers.length} layers
        · {doc.placed_actor_count} actors · {doc.quest_count} quests · {doc.music_cue_count} audio cues</Text>
      <Text selectable style={{ color: '#829db0', fontSize: 11 }}>{doc.source_sha256}</Text>
    </View>}
    {!!error && <Text accessibilityRole="alert" style={{ color: '#ffb1a9' }}>{error}</Text>}
    {!!notice && <Text style={{ color: '#b2e3c7' }}>{notice}</Text>}
    <Text style={{ color: '#d5e2f0', fontWeight: '700' }}>Tile viewport (press a tile to queue its paint coordinates)</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator>
      <View style={{ gap: 2 }}>{Array.from({ length: gridSize[1] }, (_, y) =>
        <View key={y} style={{ flexDirection: 'row', gap: 2 }}>{Array.from({ length: gridSize[0] }, (_, x) => {
          const v = tilePixels[y * gridSize[0] + x] ?? -1;
          return <TouchableOpacity key={x} accessibilityRole="button"
            accessibilityLabel={'Paint map coordinate ' + x + ',' + y}
            disabled={pending} onPress={() => {
              setAction('tile_set'); setParameters(JSON.stringify({
                layer: selectedLayer, x, y, tile: 1,
              }, null, 2));
            }} style={{ width: 26, height: 26, borderRadius: 2,
              borderWidth: 1, borderColor: '#536272',
              backgroundColor: v < 0 ? '#171b22' : palette[v % palette.length] }} />;
        })}</View>)}</View>
    </ScrollView>
    <Text style={{ color: '#c4d4e4' }}>Active layer</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator style={{ maxHeight: 51 }}>
      <View style={{ flexDirection: 'row' }}>{doc?.layers.map(layer =>
        <Button key={layer.id} title={(selectedLayer === layer.id ? '✓ ' : '') + layer.id}
          disabled={pending} press={() => setSelectedLayer(layer.id)} />)}</View>
    </ScrollView>
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Choose an executable editor tool</Text>
    <TextInput value={search} onChangeText={setSearch} accessibilityLabel="Search 50 game editor tools"
      placeholder="Search tiles, NPCs, quests, events…" placeholderTextColor="#75869a"
      style={{ color: '#f0f5fb', borderWidth: 1, borderColor: '#526478', borderRadius: 7, padding: 10 }} />
    {listed.map(group => <View key={group.title} style={{ gap: 4 }}>
      <Text style={{ color: '#a8c1d6', fontWeight: '600' }}>{group.title}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>{group.actions.map(name =>
        <Button key={name} title={(action === name ? '✓ ' : '') + label(name)}
          disabled={pending} press={() => choose(name)} />)}</View></View>)}
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Parameters for {label(action)}</Text>
    <TextInput accessibilityLabel="Authoring tool parameters JSON" value={parameters}
      onChangeText={setParameters} multiline autoCapitalize="none" autoCorrect={false}
      maxLength={120000} editable={!pending}
      style={{ color: '#edf4fc', backgroundColor: '#202936', borderRadius: 8,
        padding: 12, minHeight: 125, textAlignVertical: 'top', fontFamily: 'monospace' }} />
    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
      <Button title="Queue editor action" disabled={pending || !doc} press={enqueue} />
      <Button title="Undo last queued" disabled={pending || !steps.length}
        press={() => setSteps(current => current.slice(0, -1))} />
      <Button title="Preview changes" disabled={pending || !steps.length}
        press={() => { void transact(true); }} />
      <Button title="Save source changes" disabled={pending || !steps.length}
        press={() => { void transact(false); }} />
    </View>
    <Text style={{ color: '#bed1e4' }}>{steps.length} queued changes</Text>
    {steps.slice(-8).map((step, index) => <Text key={index} style={{ color: '#a5bdcc' }}>
      {steps.length - Math.min(steps.length, 8) + index + 1}. {label(step.action)}</Text>)}
    <Text style={{ color: '#dbe6f4', fontWeight: '700' }}>Compile & export real game</Text>
    <View style={{ flexDirection: 'row', gap: 10 }}>
      <TextInput value={seed} onChangeText={setSeed} keyboardType="numeric" accessibilityLabel="Procedural world seed"
        placeholder="Seed" placeholderTextColor="#8392a7" style={{ flex: 1, color: '#f4f8fc',
          borderWidth: 1, borderColor: '#526478', padding: 8, borderRadius: 7 }} />
      <TextInput value={islands} onChangeText={setIslands} keyboardType="numeric"
        accessibilityLabel="Sky island count" placeholder="Islands" placeholderTextColor="#8392a7"
        style={{ flex: 1, color: '#f4f8fc', borderWidth: 1, borderColor: '#526478', padding: 8, borderRadius: 7 }} />
    </View>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
      <Button title="Compile & playtest world" disabled={pending || !doc}
        press={() => { void build(false); }} />
      <Button title="Save real Godot project" disabled={pending || !doc}
        press={() => { void build(true); }} />
    </View>
    {report && <View style={{ gap: 4 }}>
      <Text selectable style={{ color: '#b6e3cc' }}>Game source: {report.source_sha256}</Text>
      <Text style={{ color: '#a6bdce' }}>Waypoints: {report.world_nodes ?? '—'}
        · Travel links: {report.travel_edges ?? '—'} · Godot source files: {report.file_count ?? 0}</Text>
      {!!report.file_paths?.length && <Text selectable style={{ color: '#abc4db' }}>
        {report.file_paths.slice(0, 8).join('\n')}</Text>}
      <Text style={{ color: '#b8c4d2' }}>Native hardware run and release certification remain separate.</Text>
    </View>}
  </View>;
}
