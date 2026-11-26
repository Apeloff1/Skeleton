/** GF-P0-58: surfaces the Game Frontier RPG-style editors in the Galaxy
 * Studio / Jeeves cockpit and routes their event actions through the
 * operator approval gate before the authorized game runtime is called.
 *
 * The runtime call goes through the public Forge Studio client
 * (inspectForge + editForge, commit mode), which uses the app's single
 * apiClient transport and gameforge auth headers.
 */
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import theme from '../../theme/tokens';
import { editForge, inspectForge, type ForgeDocument } from '../../product/gameFrontierAuthoringClient';
import { type LearningProject } from '../../product/gameLearningClient';
import GameFrontierAuthoringPanel from './GameFrontierAuthoringPanel';
import GameFrontierCurriculumPanel from './GameFrontierCurriculumPanel';
import GameFrontierEpicRoutePanel from './GameFrontierEpicRoutePanel';
import GameFrontierOperatorApprovalPanel, { type RuntimeRunner } from './GameFrontierOperatorApprovalPanel';
import type { FrontierEventAction } from './GameFrontierApprovalState';

export type FrontierEditor = Readonly<{ id: string; title: string; summary: string }>;

/** RPG-style editors shipped by the Game Frontier lanes. */
export const FRONTIER_EDITORS: readonly FrontierEditor[] = [
  { id: 'authoring', title: 'World & quest authoring', summary: 'Layers, actors, prefabs and quests' },
  { id: 'curriculum', title: 'Curriculum', summary: 'Learning progression for the authored game' },
  { id: 'epic-route', title: 'Epic route', summary: 'Campaign / chronicle / saga route planning' },
  { id: 'handbook', title: 'Handbook', summary: 'Measured game manual and completeness' },
];

export function forgeRuntimeRunner(projectId: string): RuntimeRunner {
  return async action => {
    const doc = await inspectForge(projectId);
    const result = await editForge(projectId, doc, [{ action: action.action, parameters: action.parameters }], false);
    if (!result || result.persisted !== true || result.project_id !== projectId
        || typeof result.source_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(result.source_sha256)) {
      throw new Error('Forge did not return an authenticated persisted commit receipt');
    }
    return { receipt: result.source_sha256 };
  };
}

export default function GameFrontierCockpitPanel({ projectId, actions = [], runAction, disabled = false, project = null, document = null, projectLoading = false, projectError = null, showQueue = true }: {
  projectId?: string;
  actions?: readonly FrontierEventAction[];
  runAction?: RuntimeRunner;
  disabled?: boolean;
  project?: LearningProject | null;
  document?: ForgeDocument | null;
  projectLoading?: boolean;
  projectError?: string | null;
  showQueue?: boolean;
}) {
  const [selected, setSelected] = useState<string>(FRONTIER_EDITORS[0].id);
  const [opened, setOpened] = useState(false);
  const runner = useMemo<RuntimeRunner | null>(
    () => runAction ?? (projectId ? forgeRuntimeRunner(projectId) : null), [runAction, projectId]);
  const visible = useMemo(() => actions.filter(a => a.editor === selected).slice(0, 64), [actions, selected]);
  const select = useCallback((id: string) => { setSelected(id); setOpened(false); }, []);
  const editor = FRONTIER_EDITORS.find(item => item.id === selected);

  return (
    <View style={styles.root} accessibilityLabel="Game Frontier cockpit">
      <Text style={styles.heading} accessibilityRole="header">Game Frontier cockpit</Text>
      <View style={styles.tabs} accessibilityRole="tablist">
        {FRONTIER_EDITORS.map(editor => {
          const active = editor.id === selected;
          return (
            <TouchableOpacity key={editor.id} accessibilityRole="tab"
              accessibilityLabel={editor.title + ' editor'} accessibilityState={{ selected: active }}
              onPress={() => select(editor.id)} style={[styles.tab, active && styles.tabActive]}>
              <Text style={styles.tabText}>{editor.title}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text style={styles.muted}>{editor?.summary}</Text>
      <TouchableOpacity accessibilityRole="button" accessibilityLabel={'Open ' + (editor?.title || 'editor')}
        onPress={() => setOpened(true)} style={styles.tab}>
        <Text style={styles.tabText}>Open {editor?.title}</Text>
      </TouchableOpacity>
      {opened && selected === 'authoring' && !project && !projectLoading && !projectError &&
        <Text style={styles.muted}>Open a Jeeves game-learning project, or add ?project= to this address, to edit tiles, actors, quests, curriculum, routes, and handbooks.</Text>}
      {opened && projectLoading && <View style={styles.row}><ActivityIndicator color={c.primary} /><Text style={styles.muted}>Opening the project…</Text></View>}
      {opened && !!projectError && <Text style={styles.err} accessibilityRole="alert">{projectError}</Text>}
      {opened && selected === 'authoring' && project &&
        <GameFrontierAuthoringPanel project={project} disabled={disabled} onSaved={() => undefined} />}
      {opened && selected === 'curriculum' &&
        <GameFrontierCurriculumPanel projectId={project?.project_id || projectId || 'studio'} document={document} disabled={disabled} />}
      {opened && selected === 'epic-route' &&
        <GameFrontierEpicRoutePanel projectId={project?.project_id || projectId || 'studio'} document={document}
          selectedLayer={document?.layers[0]?.id || 'ground'} siblingLayers={document?.layers.map(layer => layer.id) || []} disabled={disabled} />}
      {opened && selected === 'handbook' &&
        <View style={styles.gap}>
          <Text style={styles.muted}>Handbooks open from a recipe inside World and quest authoring. Search recipes there and the measured handbook for the selected recipe is shown with the editor.</Text>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel="Open world and quest authoring"
            onPress={() => { setSelected('authoring'); setOpened(true); }} style={styles.tab}>
            <Text style={styles.tabText}>Open world and quest authoring</Text>
          </TouchableOpacity>
        </View>}
      {showQueue && (runner
        ? <GameFrontierOperatorApprovalPanel key={projectId ?? 'custom-runtime'} actions={visible} runAction={runner} disabled={disabled} />
        : <Text style={styles.muted} accessibilityRole="alert">
            Open a Forge Studio project to connect event actions to the game runtime.
          </Text>)}
    </View>
  );
}

const c = theme.colors;
const styles = StyleSheet.create({
  root: { gap: theme.spacing.md, padding: theme.spacing.base, borderRadius: theme.radii.lg,
    backgroundColor: c.bgElevated, borderWidth: 1, borderColor: c.border },
  heading: { ...theme.typography.label, color: c.text },
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  tab: { paddingHorizontal: theme.spacing.md, paddingVertical: theme.spacing.sm, minHeight: 44,
    justifyContent: 'center', borderRadius: theme.radii.pill, backgroundColor: c.surface },
  tabActive: { backgroundColor: c.surfaceHover, borderWidth: 1, borderColor: c.borderFocus },
  tabText: { ...theme.typography.caption, color: c.text },
  muted: { ...theme.typography.caption, color: c.textMuted },
  err: { ...theme.typography.caption, color: c.danger },
  row: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  gap: { gap: theme.spacing.sm },
});
