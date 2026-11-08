/** GF-P0-58: surfaces the Game Frontier RPG-style editors in the Galaxy
 * Studio / Jeeves cockpit and routes their event actions through the
 * operator approval gate before the authorized game runtime is called.
 *
 * The runtime call goes through the public Forge Studio client
 * (inspectForge + editForge, commit mode), which uses the app's single
 * apiClient transport and gameforge auth headers.
 */
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import theme from '../../theme/tokens';
import { editForge, inspectForge } from '../../product/gameFrontierAuthoringClient';
import GameFrontierOperatorApprovalPanel, { type RuntimeRunner } from './GameFrontierOperatorApprovalPanel';
import type { FrontierEventAction } from './GameFrontierApprovalState';

export type FrontierEditor = Readonly<{ id: string; title: string; summary: string }>;

/** RPG-style editors shipped by the Game Frontier lanes. */
export const FRONTIER_EDITORS: ReadonlyArray<FrontierEditor> = [
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

export default function GameFrontierCockpitPanel({ projectId, actions = [], runAction, disabled = false }: {
  projectId?: string;
  actions?: ReadonlyArray<FrontierEventAction>;
  runAction?: RuntimeRunner;
  disabled?: boolean;
}) {
  const [selected, setSelected] = useState<string>(FRONTIER_EDITORS[0].id);
  const runner = useMemo<RuntimeRunner | null>(
    () => runAction ?? (projectId ? forgeRuntimeRunner(projectId) : null), [runAction, projectId]);
  const visible = useMemo(() => actions.filter(a => a.editor === selected).slice(0, 64), [actions, selected]);
  const select = useCallback((id: string) => setSelected(id), []);

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
      <Text style={styles.muted}>{FRONTIER_EDITORS.find(e => e.id === selected)?.summary}</Text>
      {runner
        ? <GameFrontierOperatorApprovalPanel key={selected} actions={visible} runAction={runner} disabled={disabled} />
        : <Text style={styles.muted} accessibilityRole="alert">
            Open a Forge Studio project to connect event actions to the game runtime.
          </Text>}
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
});
